from ninja.errors import HttpError
from ninja.security import HttpBearer

from judge.views.api.v3.token import _verify_token


class JWTAuth(HttpBearer):
    def authenticate(self, request, token):
        user = _verify_token(token, expected_type="access")
        if user is None:
            raise HttpError(401, "Invalid or expired access token")
        return user
