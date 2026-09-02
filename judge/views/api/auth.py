from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def get_jwt_secret() -> str:
    secret = getattr(settings, "DMOJ_API_JWT_SECRET_KEY", None)
    if not secret:
        raise ImproperlyConfigured("DMOJ_API_JWT_SECRET_KEY must be configured")
    return secret
