from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Action = Literal["follow_up", "challenge", "move_on", "switch_topic"]
Coverage = Literal["not_started", "in_progress", "covered"]
ScoreValue = Annotated[int, Field(strict=True, ge=1, le=5)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class InterviewConfig(StrictModel):
    role: str = Field(default="", max_length=200)
    experience: Text
    skills: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]] = Field(max_length=30)
    difficulty: Literal["Gentle", "Balanced", "Challenging"]
    interview_type: Literal["Mixed", "Technical", "Behavioral", "System design", "Coding"]
    duration: int = Field(strict=True, ge=5, le=120, description="Duration in minutes")

    @field_validator("skills")
    @classmethod
    def unique_skills(cls, values: list[str]) -> list[str]:
        return list({value.casefold(): value for value in reversed(values)}.values())[::-1]


class InterviewCreate(StrictModel):
    mode: Literal["random"]
    config: InterviewConfig


class AnswerInput(StrictModel):
    answer_text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]
    # Optional for API clients; the browser sends this to reject stale/double submissions.
    turn_id: str | None = None


class TopicSeed(StrictModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    skill_tag: Text | None = None
    question_seeds: list[Text] = Field(min_length=2, max_length=3)
    expected_concepts: list[Text] = Field(min_length=1, max_length=20)
    topic_type: Literal["discussion", "coding"] = "discussion"


class PlanOutput(StrictModel):
    topics: list[TopicSeed] = Field(min_length=4, max_length=8)

    @model_validator(mode="after")
    def distinct_topics(self) -> "PlanOutput":
        if len({topic.name.casefold() for topic in self.topics}) != len(self.topics):
            raise ValueError("Plan must contain distinct topics")
        return self


class QuestionOutput(StrictModel):
    question_text: Text


class ActionOutput(StrictModel):
    action: Action
    rationale: Text
    # Empty for move_on/switch_topic; the orchestrator selects the new topic.
    question_text: str = Field(max_length=4000)

    @model_validator(mode="after")
    def follow_up_needs_question(self) -> "ActionOutput":
        if self.action in {"follow_up", "challenge"} and not self.question_text:
            raise ValueError("Follow-up/challenge requires a question")
        return self


class ScoreOutput(StrictModel):
    technical_correctness: ScoreValue
    completeness: ScoreValue
    communication: ScoreValue
    problem_solving: ScoreValue
    expected_concepts: list[Text]
    missing_concepts: list[Text]
    skill_tags: list[Text]
    feedback: Text


class ScoreView(ScoreOutput):
    technical_correctness: float = Field(ge=1, le=5)
    completeness: float = Field(ge=1, le=5)
    communication: float = Field(ge=1, le=5)
    problem_solving: float = Field(ge=1, le=5)
    rubric_version: str
    scored_by_model: str
    provisional: bool
    tests_passed: int | None = None
    tests_total: int | None = None
    complexity_correct: bool | None = None
    edge_cases_identified: list[str] | None = None


class ReportOutput(StrictModel):
    summary: Text
    improvement_suggestions: list[Text] = Field(min_length=1, max_length=8)


class ReportView(ReportOutput):
    id: str
    session_id: str
    overall_score: float
    generated_by_model: str
    provisional: bool
    coding_breakdown: dict[str, int | float] | None = None
    dimension_breakdown: dict[str, float] = Field(default_factory=dict)
    turns: list[dict] = Field(default_factory=list)


class InterviewHistoryItem(BaseModel):
    session_id: str
    mode: str
    started_at: datetime
    completed_at: datetime | None
    status: str
    overall_score: float | None


class InterviewHistoryPage(BaseModel):
    items: list[InterviewHistoryItem]
    page: int
    page_size: int
    total: int


class ReportReference(BaseModel):
    method: Literal["POST"] = "POST"
    url: str


class TurnResult(BaseModel):
    session_id: str
    turn_id: str | None
    next_question: str | None
    is_complete: bool
    completion_reason: str | None = None
    report_generation: ReportReference | None = None


class InterviewCreated(TurnResult):
    first_question: str


class TurnView(BaseModel):
    id: str
    turn_index: int
    question_text: str
    answer_text: str | None
    action_taken: str | None
    topic: str
    topic_type: Literal["discussion", "coding"] = "discussion"
    generated_by_model: str | None
    provisional: bool
    score: ScoreView | None


class InterviewView(BaseModel):
    session_id: str
    mode: Literal["random", "resume", "job"]
    status: str
    config: InterviewConfig
    started_at: datetime
    completed_at: datetime | None
    time_remaining: float
    current_topic: str | None
    current_topic_type: Literal["discussion", "coding"] | None = None
    coding_status: str | None = None
    turns_on_current_topic: int
    topic_coverage: dict[str, Coverage]
    turns: list[TurnView]
    completion_reason: str | None
    report_generation: ReportReference | None
    preparation_status: Literal["preparing", "ready", "failed"] = "ready"
