from django.contrib.auth import authenticate
from django.http import JsonResponse
from ninja import Router
from ninja.errors import HttpError

from judge.views.api.v3.auth import JWTAuth
from judge.views.api.v3.permissions import require_authenticated
from judge.views.api.v3.schemas.auth import (
    LoginRequestSchema,
    LogoutRequestSchema,
    MessageSchema,
    RefreshRequestSchema,
    TokenPairSchema,
)
from judge.views.api.v3.serializers.users import serialize_user_detail
from judge.views.api.v3.token import _blacklist_token, _build_token_response, _extract_bearer_token, _verify_token

router = Router(tags=["auth"])


@router.post("/auth/login", response=TokenPairSchema, auth=None)
def login(request, payload: LoginRequestSchema):
    user = authenticate(request, username=payload.username, password=payload.password)
    if user is None or not user.is_active:
        raise HttpError(401, "Invalid credentials")
    response = JsonResponse(_build_token_response(user))
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


@router.post("/auth/refresh", response=TokenPairSchema, auth=None)
def refresh_access_token(request, payload: RefreshRequestSchema = None):
    token = payload.refresh_token if payload is not None and payload.refresh_token else _extract_bearer_token(request)
    if not token:
        raise HttpError(401, "Refresh token is required")

    user = _verify_token(token, expected_type="refresh")
    if user is None:
        raise HttpError(401, "Invalid or expired refresh token")
    response = JsonResponse(_build_token_response(user))
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


@router.post("/auth/logout", response=MessageSchema, auth=JWTAuth())
def logout(request, payload: LogoutRequestSchema = None):
    access_token = _extract_bearer_token(request)
    if access_token:
        _blacklist_token(access_token)

    refresh_token = payload.refresh_token if payload is not None else None
    if refresh_token:
        user = _verify_token(refresh_token, expected_type="refresh")
        if user is None or user.id != request.auth.id:
            raise HttpError(401, "Invalid refresh token")
        _blacklist_token(refresh_token)

    response = JsonResponse({"detail": "Logged out successfully. Provided tokens have been revoked."})
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


@router.get("/me")
def me(request):
    user = require_authenticated(request)
    response = JsonResponse(serialize_user_detail(user.profile, user))
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response
