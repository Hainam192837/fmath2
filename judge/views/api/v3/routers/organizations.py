from django.db.models import Count
from ninja import Query, Router, Schema
from ninja.errors import HttpError

from judge.models import Organization
from judge.views.api.v3.cache import etag_json_response, etag_not_modified_response
from judge.views.api.v3.permissions import require_authenticated
from judge.views.api.v3.schemas.organization import OrganizationDetailSchema, OrganizationListItemSchema
from judge.views.api.v3.serializers.organizations import (
    serialize_organization_detail,
    serialize_organization_list_item,
)

router = Router(tags=["organizations"])


class OrganizationListFilters(Schema):
    is_open: bool | None = None
    page: int = 1
    page_size: int = 20


@router.get("/organizations", response=list[OrganizationListItemSchema])
def list_organizations(request, filters: Query[OrganizationListFilters]):
    user = require_authenticated(request)
    etag_key = (
        f"api:v3:organizations:list:user:{user.id}:open:{filters.is_open}:"
        f"page:{filters.page}:size:{filters.page_size}"
    )
    not_modified = etag_not_modified_response(request, etag_key=etag_key)
    if not_modified is not None:
        return not_modified

    queryset = Organization.objects.annotate(member_count=Count("member")).order_by("name")
    if not getattr(user, "is_superuser", False):
        queryset = queryset.filter(is_hidden=False)
    if filters.is_open is not None:
        queryset = queryset.filter(is_open=filters.is_open)

    start = max(filters.page - 1, 0) * filters.page_size
    end = start + filters.page_size
    data = [serialize_organization_list_item(organization) for organization in queryset[start:end]]
    return etag_json_response(request, data, etag_key=etag_key, safe=False)


@router.get("/organizations/{organization_id}", response=OrganizationDetailSchema)
def get_organization(request, organization_id: int):
    user = require_authenticated(request)
    etag_key = f"api:v3:organizations:{organization_id}:user:{user.id}"
    not_modified = etag_not_modified_response(request, etag_key=etag_key)
    if not_modified is not None:
        return not_modified

    try:
        organization = Organization.objects.get(id=organization_id)
    except Organization.DoesNotExist:
        raise HttpError(404, "Organization not found")

    if organization.is_hidden and not getattr(user, "is_superuser", False):
        raise HttpError(404, "Organization not found")

    return etag_json_response(request, serialize_organization_detail(organization), etag_key=etag_key)
