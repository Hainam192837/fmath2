from ninja import Schema


class CommentSummarySchema(Schema):
    id: int
    author: str
    page: str
    page_title: str
    link: str
    time: str
    score: int
