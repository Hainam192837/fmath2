from typing import Optional

from ninja import Schema

from .common import NavNodeSchema, NavTabSchema, SiteConfigSchema
from .user import UserSummarySchema


class BootstrapSchema(Schema):
    site: SiteConfigSchema
    nav_tabs: list[NavTabSchema]
    nav_tree: list[NavNodeSchema]
    user: Optional[UserSummarySchema] = None
