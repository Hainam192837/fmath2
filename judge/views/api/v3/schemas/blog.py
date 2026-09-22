from ninja import Schema


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
