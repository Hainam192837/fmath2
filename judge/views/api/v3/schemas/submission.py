from typing import Optional

from ninja import Schema


class SubmissionListItemSchema(Schema):
    id: int
    problem: str
    user: str
    date: str
    language: Optional[str] = None
    time: Optional[float] = None
    memory: Optional[float] = None
    points: Optional[float] = None
    result: Optional[str] = None
    status: str


class SubmissionCaseSchema(Schema):
    case_id: Optional[int] = None
    batch_id: Optional[int] = None
    status: Optional[str] = None
    time: Optional[float] = None
    memory: Optional[float] = None
    points: Optional[float] = None
    total: Optional[float] = None
    cases: Optional[list["SubmissionCaseSchema"]] = None


class SubmissionDetailSchema(SubmissionListItemSchema):
    case_points: float
    case_total: float
    cases: list[SubmissionCaseSchema]


class SubmitRequestSchema(Schema):
    language_key: str
    source: str


class SubmitResponseSchema(Schema):
    detail: str
    submission_id: int
    replaced_existing: bool


class ContestSubmissionItemSchema(Schema):
    submission_id: int
    language_key: Optional[str] = None
    source: Optional[str] = None
    status: str
    result: Optional[str] = None
    status_display: str
    points: Optional[float] = None
    case_points: float
    case_total: float
    time: Optional[float] = None
    memory: Optional[float] = None
    is_graded: bool
    is_pretested: bool
    version_update: int
    submitted_at: str


class ContestSubmissionSourceSchema(Schema):
    contest_submission_id: int
    submission_id: int
    language_key: Optional[str] = None
    source: str
    version_update: int
    submitted_at: str


SubmissionCaseSchema.model_rebuild()
