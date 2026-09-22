from typing import Optional

from ninja import Schema

from .organization import OrganizationMiniSchema


class UserSummarySchema(Schema):
    id: int
    username: str
    display_name: str
    rank: str
    points: float
    performance_points: float
    problem_count: int
    rating: Optional[int] = None
    organization: Optional[OrganizationMiniSchema] = None
    current_contest_key: Optional[str] = None
    is_staff: bool
    is_superuser: bool


class ContestHistoryItemSchema(Schema):
    key: str
    name: str
    rating: int
    rank: int
    end_time: str


class AuthoredProblemSchema(Schema):
    code: str
    name: str


class UserDetailSchema(UserSummarySchema):
    about: str
    timezone: str
    language: Optional[str] = None
    organizations: list[OrganizationMiniSchema]
    authored_problems: list[AuthoredProblemSchema]
    solved_problems: list[str]
    contest_history: list[ContestHistoryItemSchema]
    volatility: Optional[float] = None
    editable_by_current_user: bool
