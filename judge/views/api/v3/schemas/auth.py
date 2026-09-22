from typing import Optional

from ninja import Schema


class MessageSchema(Schema):
    detail: str


class TokenPairSchema(Schema):
    access_token: str
    refresh_token: str
    token_type: str
    access_expires_in: int
    refresh_expires_in: int


class LoginRequestSchema(Schema):
    username: str
    password: str


class RefreshRequestSchema(Schema):
    refresh_token: Optional[str] = None


class LogoutRequestSchema(Schema):
    refresh_token: Optional[str] = None
