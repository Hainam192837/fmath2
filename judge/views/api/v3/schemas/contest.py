from typing import Optional

from ninja import Schema


class ContestProblemSchema(Schema):
    label: Optional[str] = None
    code: str
    name: str
    title: Optional[str] = None
    order: int
    points: int
    partial: bool
    time_limit: Optional[float] = None
    memory_limit: Optional[int] = None
    max_submissions: Optional[int] = None


class ContestListItemSchema(Schema):
    key: str
    name: str
    start_time: str
    end_time: str
    time_limit: Optional[float] = None
    is_rated: bool
    is_private: bool
    is_organization_private: bool
    tags: list[str]
    can_join: bool
    can_view_tasks: bool
    is_in_contest: bool


class ContestDetailSchema(ContestListItemSchema):
    description: str
    scoreboard_visibility: str
    hidden_scoreboard: bool
    organizations: list[int]
    authors: list[str]
    current_user_in_contest: bool
    can_see_rankings: bool
    can_see_problems: bool
    problems: list[ContestProblemSchema]


class ContestJoinRequestSchema(Schema):
    access_code: Optional[str] = None


class LeaderboardProblemCellSchema(Schema):
    has_data: bool
    points: Optional[float] = None
    time: Optional[float] = None
    status: Optional[str] = None
    is_pretested: Optional[bool] = None


class LeaderboardEntrySchema(Schema):
    rank: str
    user_id: int
    username: str
    points: float
    cumulative_time: float
    tiebreaker: float
    is_disqualified: bool
    participation_type: int
    participation_rating: Optional[int] = None
    organization: Optional[str] = None
    problem_cells: list[LeaderboardProblemCellSchema]
