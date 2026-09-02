from ninja.errors import HttpError


def get_request_user(request):
    user = getattr(request, "auth", None)
    if user is not None:
        return user
    return getattr(request, "user", None)


def require_authenticated(request):
    user = get_request_user(request)
    if not user or not user.is_authenticated:
        raise HttpError(401, "Authentication required")
    return user


def get_profile_or_none(request):
    user = get_request_user(request)
    if user and user.is_authenticated:
        return getattr(user, "profile", None)
    return None
