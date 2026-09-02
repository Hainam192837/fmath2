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


NavNodeSchema.model_rebuild()
