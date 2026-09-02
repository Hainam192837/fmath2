from typing import Any, Optional

from ninja import Schema


class NavTabSchema(Schema):
    key: str
    href: str
    label: str


class NavNodeSchema(Schema):
    key: str
    label: str
    path: str
    is_admin: bool
    children: list["NavNodeSchema"]


class SiteConfigSchema(Schema):
    name: str
    long_name: str
    admin_email: str
    domain: str
    language: str
    login_return_path: str
    meta_keywords: str
    meta_description: str
    has_webauthn: bool
    now: str


class OrganizationMiniSchema(Schema):
    id: int
    name: str
    short_name: str


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


class BootstrapSchema(Schema):
    site: SiteConfigSchema
    nav_tabs: list[NavTabSchema]
    nav_tree: list[NavNodeSchema]
    user: Optional[UserSummarySchema] = None


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


class ContestProblemSchema(Schema):
    label: Optional[str] = None
    code: str
    name: str
    order: int
    points: int
    partial: bool
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


class OrganizationListItemSchema(Schema):
    id: int
    slug: str
    name: str
    short_name: str
    is_open: bool
    is_hidden: bool
    logo_override_image: str
    member_count: Optional[int] = None


class OrganizationDetailSchema(OrganizationListItemSchema):
    about: str
    creation_date: str
    admins: list[str]
    members_preview: list[UserSummarySchema]


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


class CommentSummarySchema(Schema):
    id: int
    author: str
    page: str
    page_title: str
    link: str
    time: str
    score: int


class BlogPostSummarySchema(Schema):
    id: int
    slug: str
    title: str
    summary: str
    publish_on: str
    authors: list[str]
    url: str


class TicketSummarySchema(Schema):
    id: int
    title: str


class HomeStatsSchema(Schema):
    users: int
    problems: int
    submissions: int
    judges_online: int


class HomeSchema(Schema):
    posts: list[BlogPostSummarySchema]
    new_problems: list[ProblemListItemSchema]
    recent_comments: list[CommentSummarySchema]
    current_contests: list[ContestListItemSchema]
    future_contests: list[ContestListItemSchema]
    stats: HomeStatsSchema
    own_open_tickets: list[TicketSummarySchema]


NavNodeSchema.model_rebuild()
SubmissionCaseSchema.model_rebuild()
