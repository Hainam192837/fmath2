from django.db import OperationalError
from django.db.models import Q
from ninja import Query, Router, Schema
from ninja.errors import HttpError

from judge.models import Problem
from judge.views.api.v3.cache import etag_json_response, etag_not_modified_response
from judge.views.api.v3.permissions import require_authenticated
from judge.views.api.v3.schemas.problem import ProblemDetailSchema, ProblemListItemSchema
from judge.views.api.v3.serializers.problems import serialize_problem_detail, serialize_problem_list_item

router = Router(tags=["problems"])


class ProblemListFilters(Schema):
    search: str | None = None
    partial: bool | None = None
    group: str | None = None
    type: str | None = None
    page: int = 1
    page_size: int = 20


def apply_problem_search(queryset, query: str):
    try:
        searched = queryset.search(query)
        # Force a cheap query so missing FULLTEXT indexes fail here and can fall back.
        searched.exists()
        return searched
    except OperationalError as exc:
        if "FULLTEXT index" not in str(exc):
            raise
        return queryset.filter(
            Q(code__icontains=query) | Q(name__icontains=query) | Q(description__icontains=query)
        )


@router.get("/problems", response=list[ProblemListItemSchema])
def list_problems(request, filters: Query[ProblemListFilters]):
    user = require_authenticated(request)
    etag_key = (
        f"api:v3:problems:list:user:{user.id}:search:{filters.search or ''}:partial:{filters.partial}:"
        f"group:{filters.group or ''}:type:{filters.type or ''}:page:{filters.page}:size:{filters.page_size}"
    )
    not_modified = etag_not_modified_response(request, etag_key=etag_key)
    if not_modified is not None:
        return not_modified

    queryset = Problem.get_visible_problems(user).select_related("group").prefetch_related("types").distinct()

    if filters.partial is not None:
        queryset = queryset.filter(partial=filters.partial)
    if filters.group:
        queryset = queryset.filter(group__full_name=filters.group)
    if filters.type:
        queryset = queryset.filter(types__full_name=filters.type)
    if filters.search:
        query = filters.search.strip()
        if query:
            queryset = apply_problem_search(queryset, query)

    start = max(filters.page - 1, 0) * filters.page_size
    end = start + filters.page_size
    data = [serialize_problem_list_item(problem) for problem in queryset.order_by("code")[start:end]]
    return etag_json_response(request, data, etag_key=etag_key, safe=False)


@router.get("/problems/{problem_code}", response=ProblemDetailSchema)
def get_problem(request, problem_code: str):
    user = require_authenticated(request)
    etag_key = f"api:v3:problems:{problem_code}:user:{user.id}"
    not_modified = etag_not_modified_response(request, etag_key=etag_key)
    if not_modified is not None:
        return not_modified

    try:
        problem = Problem.objects.get(code=problem_code)
    except Problem.DoesNotExist:
        raise HttpError(404, "Problem not found")

    if not problem.is_accessible_by(user, skip_contest_problem_check=True):
        raise HttpError(404, "Problem not found")

    return etag_json_response(request, serialize_problem_detail(problem, user), etag_key=etag_key)
