"""JSON controls plus binary mono PCM16LE, 16 kHz, 512 samples per frame."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.schemas.interviews import InterviewView


class StrictMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Authenticate(StrictMessage):
    type: Literal["auth"]
    token: str = Field(min_length=1, max_length=8192)


class PlaybackDone(StrictMessage):
    type: Literal["playback_done"]
    turn_id: str


class Mute(StrictMessage):
    type: Literal["mute"]
    muted: bool


class End(StrictMessage):
    type: Literal["end"]


controls = TypeAdapter(Annotated[PlaybackDone | Mute | End, Field(discriminator="type")])


class Snapshot(StrictMessage):
    type: Literal["snapshot"] = "snapshot"
    session: InterviewView


class State(StrictMessage):
    type: Literal["state"] = "state"
    state: Literal["idle", "listening", "thinking"]
    stt_active: bool = False


class Transcript(StrictMessage):
    type: Literal["transcript"] = "transcript"
    turn_id: str
    text: str
    final: bool


class Question(StrictMessage):
    type: Literal["question_start", "question_chunk", "question_end"]
    turn_id: str
    text: str = ""


class Error(StrictMessage):
    type: Literal["error"] = "error"
    message: str


class IntroComplete(StrictMessage):
    type: Literal["intro_complete"] = "intro_complete"
