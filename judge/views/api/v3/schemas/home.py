from ninja import Schema

from .blog import BlogPostSummarySchema, TicketSummarySchema
from .comment import CommentSummarySchema
from .contest import ContestListItemSchema
from .problem import ProblemListItemSchema


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
