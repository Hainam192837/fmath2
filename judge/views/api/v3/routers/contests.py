from django.db import IntegrityError
from django.db.models import Max
from django.utils import timezone
from ninja import Query, Router, Schema
from ninja.errors import HttpError

from judge.jinja2.markdown import markdown
from judge.models import Contest, ContestParticipation, ContestSubmission
from judge.views.api.v3.cache import etag_json_response, etag_not_modified_response
from judge.views.api.v3.permissions import require_authenticated
from judge.views.api.v3.schemas.auth import MessageSchema
from judge.views.api.v3.schemas.contest import (
    ContestDetailSchema,
    ContestJoinRequestSchema,
    ContestListItemSchema,
    ContestProblemSchema,
    LeaderboardEntrySchema,
)
from judge.views.api.v3.schemas.problem import ContestProblemDetailSchema
from judge.views.api.v3.serializers.contests import (
    serialize_contest_detail,
    serialize_contest_list_item,
    serialize_contest_problem,
    serialize_leaderboard_entry,
)
from judge.views.api.v3.services.contests import (
    get_contest_or_404,
    get_contest_problem_or_404,
    require_contest_access,
    require_contest_joinable,
)
from judge.views.contest.ranking import get_contest_ranking_list

router = Router(tags=["contests"])


class ContestListFilters(Schema):
    tag: str | None = None
    page: int = 1
    page_size: int = 20


@router.get("/contests", response=list[ContestListItemSchema])
def list_contests(request, filters: Query[ContestListFilters]):
    user = require_authenticated(request)
    tag_filter = filters.tag or ""
    etag_key = f"api:v3:contests:list:user:{user.id}:tag:{tag_filter}:page:{filters.page}:size:{filters.page_size}"
    not_modified = etag_not_modified_response(request, etag_key=etag_key)
    if not_modified is not None:
        return not_modified

    queryset = Contest.get_visible_contests(user).prefetch_related("tags").order_by("-end_time")
    if filters.tag:
        queryset = queryset.filter(tags__name=filters.tag)

    start = max(filters.page - 1, 0) * filters.page_size
    end = start + filters.page_size
    data = [serialize_contest_list_item(contest, user) for contest in queryset[start:end]]
    return etag_json_response(request, data, etag_key=etag_key, safe=False)


@router.get("/contests/{contest_key}", response=ContestDetailSchema)
def get_contest(request, contest_key: str):
    user = require_authenticated(request)
    etag_key = f"api:v3:contests:{contest_key}:user:{user.id}"
    not_modified = etag_not_modified_response(request, etag_key=etag_key)
    if not_modified is not None:
        return not_modified

    contest = get_contest_or_404(contest_key)

    if not contest.is_accessible_by(user):
        raise HttpError(404, "Contest not found")

    return etag_json_response(request, serialize_contest_detail(contest, user), etag_key=etag_key)


@router.post("/contests/{contest_key}/join", response=MessageSchema)
def join_contest(request, contest_key: str, payload: ContestJoinRequestSchema = None):
    user = require_authenticated(request)
    profile = user.profile
    contest = require_contest_access(get_contest_or_404(contest_key), user)

    is_editor = profile.id in contest.editor_ids
    is_tester = profile.id in contest.tester_ids
    can_edit = contest.is_editable_by(user)

    if not contest.can_join and not (is_editor or is_tester):
        raise HttpError(400, "Contest is not currently ongoing")

    if profile.current_contest is not None:
        raise HttpError(400, 'You are already in a contest: "%s"' % profile.current_contest.contest.name)

    if not user.is_superuser and contest.banned_users.filter(id=profile.id).exists():
        raise HttpError(403, "You have been banned from this contest")

    access_code = payload.access_code if payload else None
    requires_access_code = not can_edit and contest.access_code and access_code != contest.access_code

    if contest.ended:
        if requires_access_code:
            raise HttpError(403, "Access code required")

        while True:
            virtual_id = max(
                (
                    ContestParticipation.objects.filter(contest=contest, user=profile).aggregate(
                        virtual_id=Max("virtual")
                    )["virtual_id"]
                    or 0
                )
                + 1,
                1,
            )
            try:
                participation = ContestParticipation.objects.create(
                    contest=contest,
                    user=profile,
                    virtual=virtual_id,
                    real_start=timezone.now(),
                )
            except IntegrityError:
                continue
            break
    else:
        spectate = ContestParticipation.SPECTATE
        live = ContestParticipation.LIVE
        if not is_editor and requires_access_code:
            raise HttpError(403, "Access code required")
        try:
            participation = ContestParticipation.objects.get(
                contest=contest,
                user=profile,
                virtual=(spectate if is_editor or is_tester else live),
            )
        except ContestParticipation.DoesNotExist:
            if requires_access_code:
                raise HttpError(403, "Access code required")
            participation = ContestParticipation.objects.create(
                contest=contest,
                user=profile,
                virtual=(spectate if is_editor or is_tester else live),
                real_start=timezone.now(),
            )
        else:
            if participation.ended:
                participation = ContestParticipation.objects.get_or_create(
                    contest=contest,
                    user=profile,
                    virtual=spectate,
                    defaults={"real_start": timezone.now()},
                )[0]

    profile.current_contest = participation
    profile.save(update_fields=["current_contest"])
    contest._updating_stats_only = True
    contest.update_user_count()
    return {"detail": "Successfully joined the contest"}


@router.post("/contests/{contest_key}/leave", response=MessageSchema)
def leave_contest(request, contest_key: str):
    user = require_authenticated(request)
    profile = user.profile

    if profile.current_contest is None or profile.current_contest.contest.key != contest_key:
        raise HttpError(400, 'You are not in contest "%s"' % contest_key)

    contest = get_contest_or_404(contest_key)
    if contest.forbidden_leave:
        raise HttpError(403, 'You are not allowed to leave contest "%s" at this time' % contest.name)

    profile.remove_contest()
    return {"detail": "Successfully left the contest"}


@router.get("/contests/{contest_key}/problems", response=list[ContestProblemSchema])
def list_contest_problems(request, contest_key: str):
    user = require_authenticated(request)
    etag_key = f"api:v3:contests:{contest_key}:problems:user:{user.id}"
    not_modified = etag_not_modified_response(request, etag_key=etag_key)
    if not_modified is not None:
        return not_modified

    contest = require_contest_joinable(get_contest_or_404(contest_key), user)
    contest_problems = contest.contest_problems.select_related("problem").order_by("order")
    data = [serialize_contest_problem(contest, contest_problem) for contest_problem in contest_problems]
    return etag_json_response(request, data, etag_key=etag_key, safe=False)


@router.get("/contests/{contest_key}/leaderboard", response=list[LeaderboardEntrySchema])
def get_contest_leaderboard(request, contest_key: str):
    user = require_authenticated(request)
    contest = require_contest_access(get_contest_or_404(contest_key), user)
    if not contest.can_see_own_scoreboard(user):
        raise HttpError(403, "You do not have permission to view this leaderboard")

    ranking_rows, _ = get_contest_ranking_list(request, contest)
    return [serialize_leaderboard_entry(rank, entry) for rank, entry in ranking_rows]


@router.get("/contests/{contest_key}/problems/{problem_code}", response=ContestProblemDetailSchema)
def get_contest_problem_detail(request, contest_key: str, problem_code: str):
    user = require_authenticated(request)
    etag_key = f"api:v3:contests:{contest_key}:problems:{problem_code}:user:{user.id}"
    not_modified = etag_not_modified_response(request, etag_key=etag_key)
    if not_modified is not None:
        return not_modified

    contest = require_contest_joinable(get_contest_or_404(contest_key), user)
    contest_problem = get_contest_problem_or_404(contest, problem_code, with_languages=True)
    problem = contest_problem.problem

    participation = user.profile.current_contest
    latest_submission = None
    if participation is not None and participation.contest_id == contest.id:
        latest_submission = (
            ContestSubmission.objects.select_related("submission")
            .filter(participation=participation, problem=contest_problem)
            .first()
        )

    data = {
        **serialize_contest_problem(contest, contest_problem),
        "statement": str(markdown(problem.description, problem.markdown_style)),
        "allowed_languages": list(problem.allowed_languages.values_list("key", flat=True)),
        "io_method": problem.io_method,
        "version_update": problem.version_update,
        "has_submission": latest_submission is not None,
        "latest_submission_id": latest_submission.submission_id if latest_submission is not None else None,
        "latest_submission_version": (
            latest_submission.submission.version_update if latest_submission is not None else None
        ),
    }
    return etag_json_response(request, data, etag_key=etag_key)
