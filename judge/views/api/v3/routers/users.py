from ninja import Query, Router, Schema
from ninja.errors import HttpError

from judge.models import Profile
from judge.views.api.v3.cache import etag_json_response, etag_not_modified_response
from judge.views.api.v3.permissions import require_authenticated
from judge.views.api.v3.schemas.user import UserDetailSchema, UserSummarySchema
from judge.views.api.v3.serializers.users import serialize_profile_summary, serialize_user_detail

router = Router(tags=["users"])


class UserListFilters(Schema):
    organization: int | None = None
    page: int = 1
    page_size: int = 20


@router.get("/users", response=list[UserSummarySchema])
def list_users(request, filters: Query[UserListFilters]):
    user = require_authenticated(request)
    etag_key = (
        f"api:v3:users:list:user:{user.id}:"
        f"organization:{filters.organization}:page:{filters.page}:size:{filters.page_size}"
    )
    not_modified = etag_not_modified_response(request, etag_key=etag_key)
    if not_modified is not None:
        return not_modified

    queryset = Profile.objects.filter(is_unlisted=False, user__is_active=True) \
                              .select_related("user") \
                              .prefetch_related("organizations")
    if filters.organization is not None:
        queryset = queryset.filter(organizations=filters.organization)

    start = max(filters.page - 1, 0) * filters.page_size
    end = start + filters.page_size
    queryset = queryset.order_by("-performance_points", "-problem_count", "user__username")[start:end]
    data = [serialize_profile_summary(profile) for profile in queryset]
    return etag_json_response(request, data, etag_key=etag_key, safe=False)


@router.get("/users/{username}", response=UserDetailSchema)
def get_user(request, username: str):
    viewer = require_authenticated(request)
    etag_key = f"api:v3:users:{username}:viewer:{viewer.id}"
    not_modified = etag_not_modified_response(request, etag_key=etag_key)
    if not_modified is not None:
        return not_modified

    try:
        profile = Profile.objects.select_related("user", "language").prefetch_related("organizations").get(
            user__username=username
        )
    except Profile.DoesNotExist:
        raise HttpError(404, "User not found")

    return etag_json_response(request, serialize_user_detail(profile, viewer), etag_key=etag_key)
