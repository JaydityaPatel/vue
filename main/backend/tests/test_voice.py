import pytest
from pydantic import ValidationError

from app.voice.endpoint import Endpoint
from app.voice.protocol import Authenticate, Question, State, Transcript, controls
from tests.test_interviews_api import create, login


def test_endpoint_waits_full_threshold_and_resets_on_short_pause():
    vad = Endpoint()
    for _ in range(10):
        assert not vad.feed(.9)
    for _ in range(40):  # 1280 ms is a thinking pause, not an endpoint.
        assert not vad.feed(.1)
    assert not vad.feed(.9)
    for _ in range(56):
        assert not vad.feed(.1)
    assert vad.feed(.1)  # 1824 ms; threshold rounded to a PCM frame.
    vad.reset()
    for _ in range(100):
        assert not vad.feed(0)


def test_brief_noise_is_discarded():
    vad = Endpoint()
    vad.feed(.9)
    for _ in range(60):
        assert not vad.feed(0)
    assert not vad.started


@pytest.mark.parametrize("data", [
    '{"type":"mute","muted":true}', '{"type":"end"}',
    '{"type":"playback_done","turn_id":"t1"}',
])
def test_client_protocol(data):
    assert controls.validate_json(data).type


@pytest.mark.parametrize("data", ['{"type":"audio"}', '{"type":"mute"}', '{"type":"mute","muted":"false"}', '{"type":"end","text":"injected"}'])
def test_invalid_protocol(data):
    with pytest.raises(ValidationError):
        controls.validate_json(data)


def test_server_protocol():
    assert State(state="thinking", stt_active=True).model_dump() == {"type": "state", "state": "thinking", "stt_active": True}
    assert Transcript(turn_id="t", text="hello", final=False).type == "transcript"
    assert Question(type="question_end", turn_id="t").text == ""
    with pytest.raises(ValidationError):
        Authenticate(type="auth", token="")


class FakeRuntime:
    instances = []

    def __init__(self):
        self.calls = []
        self.instances.append(self)

    async def prepare(self):
        pass

    def probability(self, pcm):
        return 1 if pcm[0] else 0

    def reset(self):
        pass

    async def transcribe(self, pcm):
        self.calls.append(len(pcm))
        return "I test assumptions with Python."


@pytest.fixture
def voice_runtime(monkeypatch):
    FakeRuntime.instances.clear()
    monkeypatch.setattr("app.routers.voice.VoiceRuntime", FakeRuntime)
    return FakeRuntime


def until(ws, kind):
    messages = []
    for _ in range(100):
        message = ws.receive_json()
        messages.append(message)
        if message["type"] == kind:
            return messages
        assert message["type"] != "error", message
    raise AssertionError(f"Did not receive {kind}")


def authenticate(ws, headers):
    ws.send_json({"type": "auth", "token": headers["Authorization"].split()[1]})


def test_pcm_answer_runs_real_orchestrator_and_persists(client, interview_llm, voice_runtime):
    headers = login(client)
    created = create(client, headers)
    path = f"/interviews/{created['session_id']}"
    with client.websocket_connect(f"/ws/interview/{created['session_id']}") as ws:
        authenticate(ws, headers)
        opening = until(ws, "question_end")
        assert opening[0]["type"] == "snapshot"
        assert "".join(m.get("text", "") for m in opening if m["type"] == "question_chunk") == created["first_question"]
        ws.send_json({"type": "playback_done", "turn_id": created["turn_id"]})
        assert ws.receive_json()["state"] == "listening"
        for _ in range(130):
            ws.send_bytes(bytes([1, 0]) * 512)
        for _ in range(57):
            ws.send_bytes(bytes(1024))
        messages = until(ws, "question_end")
        transcripts = [m for m in messages if m["type"] == "transcript"]
        assert [m["final"] for m in transcripts] == [False, True]
        assert any(m.get("stt_active") for m in messages)
        persisted = client.get(path, headers=headers).json()
        assert persisted["turns"][0]["answer_text"] == "I test assumptions with Python."
        assert persisted["turns"][0]["score"] is not None
        assert len(persisted["turns"]) == 2
        ws.send_json({"type": "end"})
        ended = until(ws, "snapshot")[-1]["session"]
        assert ended["status"] == "completed"
        assert ended["completion_reason"] == "user_ended"
    assert len(voice_runtime.instances[0].calls) == 2


def test_mute_and_playback_gate_audio_and_empty_end(client, interview_llm, voice_runtime):
    headers = login(client)
    created = create(client, headers)
    with client.websocket_connect(f"/ws/interview/{created['session_id']}") as ws:
        authenticate(ws, headers)
        until(ws, "question_end")
        for _ in range(10):
            ws.send_bytes(bytes([1, 0]) * 512)
        ws.send_json({"type": "mute", "muted": True})
        until(ws, "state")
        ws.send_json({"type": "playback_done", "turn_id": created["turn_id"]})
        assert ws.receive_json()["state"] == "idle"
        for _ in range(60):
            ws.send_bytes(bytes(1024))
        ws.send_json({"type": "mute", "muted": False})
        assert until(ws, "state")[-1]["state"] == "listening"
        ws.send_json({"type": "end"})
        assert until(ws, "snapshot")[-1]["session"]["status"] == "abandoned"
    assert not voice_runtime.instances[0].calls


def test_voice_rejects_bad_token(client, voice_runtime):
    with client.websocket_connect('/ws/interview/missing') as ws:
        ws.send_json({"type": "auth", "token": "invalid"})
        assert ws.receive_json()["message"].startswith("Authentication failed")


def test_voice_rejects_other_owner(client, interview_llm, voice_runtime):
    owner = login(client)
    created = create(client, owner)
    other = login(client, "other@example.com")
    with client.websocket_connect(f"/ws/interview/{created['session_id']}") as ws:
        authenticate(ws, other)
        assert "another user" in ws.receive_json()["message"]


@pytest.mark.parametrize("invalid", ["pcm", "ack"])
def test_invalid_audio_or_stale_turn_rejected(client, interview_llm, voice_runtime, invalid):
    headers = login(client)
    created = create(client, headers)
    with client.websocket_connect(f"/ws/interview/{created['session_id']}") as ws:
        authenticate(ws, headers)
        until(ws, "question_end")
        if invalid == "pcm":
            ws.send_bytes(b'bad')
        else:
            ws.send_json({"type": "playback_done", "turn_id": "old-turn"})
        assert ws.receive_json()["type"] == "error"


def test_disconnect_releases_session_and_replays_without_new_turn(client, interview_llm, voice_runtime):
    headers = login(client)
    created = create(client, headers)
    for _ in range(2):
        with client.websocket_connect(f"/ws/interview/{created['session_id']}") as ws:
            authenticate(ws, headers)
            messages = until(ws, "question_end")
            assert messages[-1]["turn_id"] == created["turn_id"]
            assert len(messages[0]["session"]["turns"]) == 1


def test_second_connection_is_rejected_without_disrupting_first(client, interview_llm, voice_runtime):
    headers = login(client)
    created = create(client, headers)
    path = f"/ws/interview/{created['session_id']}"
    with client.websocket_connect(path) as first:
        authenticate(first, headers)
        until(first, "question_end")
        with client.websocket_connect(path) as second:
            authenticate(second, headers)
            assert "already has a voice connection" in second.receive_json()["message"]
        first.send_json({"type": "playback_done", "turn_id": created["turn_id"]})
        assert first.receive_json()["state"] == "listening"


def test_model_initialization_failure_is_visible_and_releases_connection(client, interview_llm, voice_runtime, monkeypatch):
    headers = login(client)
    created = create(client, headers)

    async def fail(_self):
        raise RuntimeError("CUDA missing")

    monkeypatch.setattr(FakeRuntime, "prepare", fail)
    with client.websocket_connect(f"/ws/interview/{created['session_id']}") as ws:
        authenticate(ws, headers)
        assert ws.receive_json()["type"] == "snapshot"
        assert ws.receive_json()["stt_active"]
        assert "CUDA configuration" in ws.receive_json()["message"]
    from app.routers.voice import _active
    assert created["session_id"] not in _active
    saved = client.get(f"/interviews/{created['session_id']}", headers=headers).json()
    assert saved["turns"][0]["answer_text"] is None
