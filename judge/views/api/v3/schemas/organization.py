from typing import TYPE_CHECKING, Optional

from ninja import Schema

if TYPE_CHECKING:
    from .user import UserSummarySchema


class OrganizationMiniSchema(Schema):
    id: int
    name: str
    short_name: str


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
    members_preview: list["UserSummarySchema"]
