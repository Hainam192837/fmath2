import hashlib
import time
from pathlib import Path
from typing import Optional

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured

from judge.views.api.auth import get_jwt_secret

HMAC_JWT_ALGORITHMS = frozenset(("HS256", "HS384", "HS512"))
ASYMMETRIC_JWT_ALGORITHMS = frozenset(("RS256", "RS384", "RS512", "ES256", "ES384", "ES512"))
SUPPORTED_JWT_ALGORITHMS = HMAC_JWT_ALGORITHMS | ASYMMETRIC_JWT_ALGORITHMS


def _get_token_lifetime() -> int:
    return int(getattr(settings, "API_JWT_EXP_SECONDS", 1800))


def _get_refresh_token_lifetime() -> int:
    return int(getattr(settings, "API_JWT_REFRESH_EXP_SECONDS", 7 * 24 * 60 * 60))


def _get_jwt_algorithm() -> str:
    algorithm = getattr(settings, "API_JWT_ALGORITHM", "HS256").upper()
    if algorithm not in SUPPORTED_JWT_ALGORITHMS:
        raise ImproperlyConfigured(f"Unsupported API_JWT_ALGORITHM: {algorithm}")
    return algorithm


def _get_jwt_signing_key() -> str:
    algorithm = _get_jwt_algorithm()
    if algorithm in HMAC_JWT_ALGORITHMS:
        return get_jwt_secret()

    private_key = _get_key_from_file("API_JWT_PRIVATE_KEY_PATH") or getattr(settings, "API_JWT_PRIVATE_KEY", None)
    if not private_key:
        raise ImproperlyConfigured(
            "API_JWT_PRIVATE_KEY_PATH or API_JWT_PRIVATE_KEY must be configured "
            "for asymmetric API JWT signing",
        )
    return private_key


def _get_jwt_verification_key() -> str:
    algorithm = _get_jwt_algorithm()
    if algorithm in HMAC_JWT_ALGORITHMS:
        return get_jwt_secret()

    public_key = _get_key_from_file("API_JWT_PUBLIC_KEY_PATH") or getattr(settings, "API_JWT_PUBLIC_KEY", None)
    if not public_key:
        raise ImproperlyConfigured(
            "API_JWT_PUBLIC_KEY_PATH or API_JWT_PUBLIC_KEY must be configured "
            "for asymmetric API JWT verification",
        )
    return public_key


def _get_key_from_file(setting_name: str) -> Optional[str]:
    key_path = getattr(settings, setting_name, None)
    if not key_path:
        return None

    path = Path(key_path).expanduser()
    if not path.is_absolute():
        path = Path(settings.BASE_DIR) / path

    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ImproperlyConfigured(f"{setting_name} points to an unreadable key file: {path}") from exc


def _create_token(user, expires_in: int, token_type: str) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "is_staff": user.is_staff,
        "type": token_type,
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(payload, _get_jwt_signing_key(), algorithm=_get_jwt_algorithm())


def _build_token_response(user) -> dict:
    access_expires_in = _get_token_lifetime()
    refresh_expires_in = _get_refresh_token_lifetime()
    return {
        "access_token": _create_token(user, expires_in=access_expires_in, token_type="access"),
        "refresh_token": _create_token(user, expires_in=refresh_expires_in, token_type="refresh"),
        "token_type": "Bearer",
        "access_expires_in": access_expires_in,
        "refresh_expires_in": refresh_expires_in,
    }


def _extract_bearer_token(request) -> Optional[str]:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        return None
    parts = auth_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def _verify_token(token: str, expected_type: str):
    if _is_token_blacklisted(token):
        return None

    try:
        payload = jwt.decode(token, _get_jwt_verification_key(), algorithms=[_get_jwt_algorithm()])
    except jwt.InvalidTokenError:
        return None

    if payload.get("type") != expected_type:
        return None

    user_id = payload.get("sub")
    if user_id is None:
        return None

    User = get_user_model()
    return User.objects.filter(id=user_id, is_active=True).select_related("profile").first()


def _token_blacklist_key(token: str) -> str:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"api_app_v3:blacklist:{token_hash}"


def _is_token_blacklisted(token: str) -> bool:
    return bool(cache.get(_token_blacklist_key(token)))


def _blacklist_token(token: str) -> None:
    try:
        payload = jwt.decode(
            token,
            _get_jwt_verification_key(),
            algorithms=[_get_jwt_algorithm()],
            options={"verify_exp": False},
        )
    except jwt.InvalidTokenError:
        return

    exp = payload.get("exp")
    if exp is None:
        return

    ttl = max(int(exp - time.time()), 1)
    cache.set(_token_blacklist_key(token), 1, ttl)
