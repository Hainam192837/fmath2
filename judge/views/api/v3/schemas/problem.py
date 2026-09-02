from typing import Any, Optional

from ninja import Schema


class ProblemListItemSchema(Schema):
    code: str
    name: str
    group: Optional[str] = None
    types: list[str]
    points: float
    partial: bool
    is_public: bool
    is_organization_private: bool


class JudgeMiniSchema(Schema):
    name: str
    ping: Optional[float] = None
    load: Optional[float] = None


class SubmissionMiniSchema(Schema):
    id: int
    status: str
    result: Optional[str] = None
    date: str


class LanguageLimitSchema(Schema):
    language: str
    time_limit: Optional[float] = None
    memory_limit: Optional[int] = None


class ProblemDetailSchema(ProblemListItemSchema):
    authors: list[str]
    curators: list[str]
    time_limit: float
    memory_limit: int
    short_circuit: bool
    allowed_languages: list[str]
    language_resource_limits: list[LanguageLimitSchema]
    statement: str
    io_method: dict[str, Any]
    can_edit: bool
    can_submit: bool
    online_judges: list[JudgeMiniSchema]
    latest_submission: Optional[SubmissionMiniSchema] = None


class ContestProblemDetailSchema(Schema):
    code: str
    name: str
    title: Optional[str] = None
    order: int
    points: int
    partial: bool
    time_limit: float
    memory_limit: int
    max_submissions: Optional[int] = None
    label: Optional[str] = None
    statement: str
    allowed_languages: list[str]
    io_method: dict[str, Any]
    version_update: int
    has_submission: bool
    latest_submission_id: Optional[int] = None
    latest_submission_version: Optional[int] = None
