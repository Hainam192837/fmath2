import hashlib
import time
from pathlib import Path
from typing import List, Optional

import jwt
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError
from ninja.security import HttpBearer

from judge.jinja2.markdown import markdown
from judge.models import Contest, ContestParticipation, ContestSubmission, Language, Submission
from judge.models.submission import SubmissionSource
from judge.views.api.auth import get_jwt_secret
from judge.views.contest.ranking import get_contest_ranking_list

router = Router(tags=["app-v2"])


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


class UserProfileSchema(Schema):
    id: int
    username: str
    email: str
    display_name: str
    rank: str
    points: float
    performance_points: float
    problem_count: int
    current_contest_key: Optional[str] = None
    is_staff: bool
    is_superuser: bool


class ContestListItemSchema(Schema):
    pk: int
    key: str
    name: str
    topic: str
    description: str
    start_time: str
    end_time: str
    is_joinable: bool
    is_in_contest: bool
    is_accessible: bool
    user_count: int
    version_update: int


class ContestProblemItemSchema(Schema):
    code: str
    title: str
    order: int
    points: int
    partial: bool
    time_limit: float
    memory_limit: int
    max_submissions: Optional[int] = None
    label: Optional[str] = None


class LeaderboardProblemCellSchema(Schema):
    has_data: bool
    points: Optional[float] = None
    time: Optional[float] = None
    status: Optional[str] = None
    is_pretested: Optional[bool] = None


class LeaderboardEntrySchema(Schema):
    rank: str
    user_id: int
    username: str
    points: float
    cumulative_time: float
    tiebreaker: float
    is_disqualified: bool
    participation_type: int
    participation_rating: Optional[int] = None
    organization: Optional[str] = None
    problem_cells: List[LeaderboardProblemCellSchema]


class ContestDetailSchema(ContestListItemSchema):
    hidden_scoreboard: bool
    scoreboard_visibility: str
    can_see_problems: bool
    can_see_rankings: bool
    current_user_in_contest: bool
    problems: List[ContestProblemItemSchema]


class ContestJoinRequestSchema(Schema):
    access_code: Optional[str] = None


class ProblemDetailSchema(ContestProblemItemSchema):
    statement: str
    allowed_languages: List[str]
    io_method: dict
    version_update: int
    has_submission: bool
    latest_submission_id: Optional[int] = None
    latest_submission_version: Optional[int] = None


class SubmitRequestSchema(Schema):
    language_key: str
    source: str


class SubmitResponseSchema(Schema):
    detail: str
    submission_id: int
    replaced_existing: bool


class SubmissionItemSchema(Schema):
    submission_id: int
    language_key: Optional[str] = None
    source: Optional[str] = None
    status: str
    result: Optional[str] = None
    status_display: str
    points: Optional[float] = None
    case_points: float
    case_total: float
    time: Optional[float] = None
    memory: Optional[float] = None
    is_graded: bool
    is_pretested: bool
    version_update: int
    submitted_at: str


class ContestSubmissionSourceSchema(Schema):
    contest_submission_id: int
    submission_id: int
    language_key: Optional[str] = None
    source: str
    version_update: int
    submitted_at: str


def _get_token_lifetime() -> int:
    return int(getattr(settings, "DMOJ_API_JWT_EXP_SECONDS", 1800))


def _get_refresh_token_lifetime() -> int:
    return int(getattr(settings, "DMOJ_API_JWT_REFRESH_EXP_SECONDS", 7 * 24 * 60 * 60))


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
    return jwt.encode(payload, get_jwt_secret(), algorithm="HS256")


def _verify_token(token: str, expected_type: str):
    if _is_token_blacklisted(token):
        return None

    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])
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
    return f"api_app_v2:blacklist:{token_hash}"


def _is_token_blacklisted(token: str) -> bool:
    return bool(cache.get(_token_blacklist_key(token)))


def _blacklist_token(token: str) -> None:
    try:
        payload = jwt.decode(
            token,
            get_jwt_secret(),
            algorithms=["HS256"],
            options={"verify_exp": False},
        )
    except jwt.InvalidTokenError:
        return

    exp = payload.get("exp")
    if exp is None:
        return

    ttl = max(int(exp - time.time()), 1)
    cache.set(_token_blacklist_key(token), 1, ttl)


class AccessJWTAuth(HttpBearer):
    def authenticate(self, request, token):
        user = _verify_token(token, expected_type="access")
        if user is None:
            raise HttpError(401, "Invalid or expired access token")
        return user


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


def _serialize_user(user) -> dict:
    profile = user.profile
    current_contest_key = None
    if profile.current_contest_id is not None:
        current_contest_key = profile.current_contest.contest.key

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email or "",
        "display_name": profile.name or user.username,
        "rank": profile.display_rank,
        "points": profile.points,
        "performance_points": profile.performance_points,
        "problem_count": profile.problem_count,
        "current_contest_key": current_contest_key,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
    }


def _get_contest_or_404(contest_key: str) -> Contest:
    try:
        return Contest.objects.get(key=contest_key)
    except Contest.DoesNotExist:
        raise HttpError(404, "Contest not found")


def _require_contest_access(contest: Contest, user) -> Contest:
    if not contest.is_accessible_by(user):
        raise HttpError(403, "You do not have permission to access this contest")
    return contest


def _require_contest_joinable(contest: Contest, user) -> Contest:
    if not contest.is_joinable_by(user):
        raise HttpError(403, "You do not have permission to access this contest")
    return contest


def _get_contest_problem_or_404(contest: Contest, problem_code: str, with_languages: bool = False):
    queryset = contest.contest_problems.select_related("problem")
    if with_languages:
        queryset = queryset.prefetch_related("problem__allowed_languages")
    contest_problem = queryset.filter(problem__code=problem_code).first()
    if contest_problem is None:
        raise HttpError(404, "Problem not found in contest")
    return contest_problem


def _get_current_participation_or_403(user, contest_key: str):
    profile = user.profile
    if profile.current_contest is None or profile.current_contest.contest.key != contest_key:
        raise HttpError(403, 'You are not in contest "%s"' % contest_key)
    return profile.current_contest


def _serialize_contest_problem(contest, contest_problem) -> dict:
    problem = contest_problem.problem
    label = None
    if hasattr(contest, "get_label_for_problem"):
        label = contest.get_label_for_problem(contest_problem.order - 1)

    return {
        "code": problem.code,
        "title": problem.name,
        "order": contest_problem.order,
        "points": int(contest_problem.points),
        "partial": contest_problem.partial,
        "time_limit": problem.time_limit,
        "memory_limit": problem.memory_limit,
        "max_submissions": contest_problem.max_submissions or None,
        "label": label,
    }


def _serialize_submission(submission, include_source: bool = False) -> dict:
    source = None
    if include_source:
        source_obj = getattr(submission, "source", None)
        source = source_obj.source if source_obj is not None else ""

    return {
        "submission_id": submission.id,
        "language_key": submission.language.key if submission.language_id else None,
        "source": source,
        "status": submission.short_status,
        "result": submission.result,
        "status_display": str(submission.long_status),
        "points": submission.points,
        "case_points": submission.case_points,
        "case_total": submission.case_total,
        "time": submission.time,
        "memory": submission.memory,
        "is_graded": submission.is_graded,
        "is_pretested": submission.is_pretested,
        "version_update": submission.version_update,
        "submitted_at": submission.date.isoformat(),
    }


def _serialize_leaderboard_entry(rank, entry) -> dict:
    problem_cells = []
    for cell in entry.problem_cells:
        if not cell or not cell.get("has_data"):
            problem_cells.append({"has_data": False})
            continue

        problem_cells.append(
            {
                "has_data": True,
                "points": cell.get("points"),
                "time": cell.get("time"),
                "status": cell.get("state") or cell.get("status"),
                "is_pretested": cell.get("is_pretested"),
            }
        )

    organization = None
    if entry.organization is not None:
        organization = entry.organization.name

    return {
        "rank": str(rank),
        "user_id": entry.id,
        "username": entry.username,
        "points": entry.points,
        "cumulative_time": entry.cumtime,
        "tiebreaker": entry.tiebreaker,
        "is_disqualified": entry.participation.is_disqualified,
        "participation_type": entry.participation.virtual,
        "participation_rating": entry.participation_rating,
        "organization": organization,
        "problem_cells": problem_cells,
    }


def _extract_bearer_token(request) -> Optional[str]:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        return None
    parts = auth_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


@router.post("/auth/login/", response=TokenPairSchema, auth=None)
def login(request, payload: LoginRequestSchema):
    user = authenticate(request, username=payload.username, password=payload.password)
    if user is None or not user.is_active:
        raise HttpError(401, "Invalid credentials")

    return _build_token_response(user)


@router.post("/auth/refresh/", response=TokenPairSchema, auth=None)
def refresh_access_token(request, payload: RefreshRequestSchema = None):
    token = payload.refresh_token if payload is not None and payload.refresh_token else _extract_bearer_token(request)
    if not token:
        raise HttpError(401, "Refresh token is required")

    user = _verify_token(token, expected_type="refresh")
    if user is None:
        raise HttpError(401, "Invalid or expired refresh token")
    return _build_token_response(user)


@router.post("/auth/logout/", response=MessageSchema, auth=AccessJWTAuth())
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

    return {"detail": "Logged out successfully. Provided tokens have been revoked."}


@router.get("/auth/me/", response=UserProfileSchema, auth=AccessJWTAuth())
def get_me(request):
    return _serialize_user(request.auth)


@router.get("/contests/", response=List[ContestListItemSchema], auth=AccessJWTAuth())
def list_contests(request):
    now = timezone.now()
    contests = (
        Contest.get_visible_contests(request.auth)
        .filter(is_exam_contest=True)
        .exclude(end_time__lt=now)
        .order_by("start_time")
    )

    return [
        {
            "pk": contest.pk,
            "key": contest.key,
            "name": contest.name,
            "topic": contest.topic,
            "description": contest.description,
            "start_time": contest.start_time.isoformat(),
            "end_time": contest.end_time.isoformat(),
            "is_joinable": contest.is_joinable_by(request.auth),
            "is_in_contest": contest.is_in_contest(request.auth),
            "is_accessible": contest.is_accessible_by(request.auth),
            "user_count": contest.user_count,
            "version_update": contest.version_update,
        }
        for contest in contests
    ]


@router.get("/contest/{contest_key}/", response=ContestDetailSchema, auth=AccessJWTAuth())
def get_contest_detail(request, contest_key: str):
    contest = _require_contest_access(_get_contest_or_404(contest_key), request.auth)
    in_contest = contest.is_in_contest(request.auth)
    can_see_rankings = contest.can_see_full_scoreboard(request.auth)
    can_see_problems = in_contest or contest.ended or contest.is_editable_by(request.auth)
    problems = []

    if can_see_problems:
        problems = [
            _serialize_contest_problem(contest, contest_problem)
            for contest_problem in contest.contest_problems.select_related("problem").order_by("order")
        ]

    return {
        "pk": contest.pk,
        "key": contest.key,
        "name": contest.name,
        "topic": contest.topic,
        "description": contest.description,
        "start_time": contest.start_time.isoformat(),
        "end_time": contest.end_time.isoformat(),
        "is_joinable": contest.is_joinable_by(request.auth),
        "is_in_contest": in_contest,
        "is_accessible": contest.is_accessible_by(request.auth),
        "user_count": contest.user_count,
        "version_update": contest.version_update,
        "hidden_scoreboard": contest.scoreboard_visibility
        in (contest.SCOREBOARD_AFTER_CONTEST, contest.SCOREBOARD_AFTER_PARTICIPATION),
        "scoreboard_visibility": contest.scoreboard_visibility,
        "can_see_problems": can_see_problems,
        "can_see_rankings": can_see_rankings,
        "current_user_in_contest": request.auth.profile.current_contest_id is not None
        and request.auth.profile.current_contest.contest_id == contest.id,
        "problems": problems,
    }


@router.post("/contest/{contest_key}/join/", response=MessageSchema, auth=AccessJWTAuth())
def join_contest(request, contest_key: str, payload: ContestJoinRequestSchema = None):
    user = request.auth
    profile = user.profile
    contest = _require_contest_access(_get_contest_or_404(contest_key), user)

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


@router.post("/contest/{contest_key}/leave/", response=MessageSchema, auth=AccessJWTAuth())
def leave_contest(request, contest_key: str):
    user = request.auth
    profile = user.profile

    if profile.current_contest is None or profile.current_contest.contest.key != contest_key:
        raise HttpError(400, 'You are not in contest "%s"' % contest_key)

    contest = _get_contest_or_404(contest_key)
    if contest.forbidden_leave:
        raise HttpError(403, 'You are not allowed to leave contest "%s" at this time' % contest.name)

    profile.remove_contest()
    return {"detail": "Successfully left the contest"}


@router.get("/contest/{contest_key}/problems/", response=List[ContestProblemItemSchema], auth=AccessJWTAuth())
def list_contest_problems(request, contest_key: str):
    contest = _require_contest_joinable(_get_contest_or_404(contest_key), request.auth)
    contest_problems = contest.contest_problems.select_related("problem").order_by("order")
    return [_serialize_contest_problem(contest, contest_problem) for contest_problem in contest_problems]


@router.get("/contest/{contest_key}/leaderboard/", response=List[LeaderboardEntrySchema], auth=AccessJWTAuth())
def get_contest_leaderboard(request, contest_key: str):
    contest = _require_contest_access(_get_contest_or_404(contest_key), request.auth)
    if not contest.can_see_own_scoreboard(request.auth):
        raise HttpError(403, "You do not have permission to view this leaderboard")

    ranking_rows, _ = get_contest_ranking_list(request, contest)
    return [_serialize_leaderboard_entry(rank, entry) for rank, entry in ranking_rows]


@router.get("/contest/{contest_key}/problems/{problem_code}/", response=ProblemDetailSchema, auth=AccessJWTAuth())
def get_contest_problem_detail(request, contest_key: str, problem_code: str):
    contest = _require_contest_joinable(_get_contest_or_404(contest_key), request.auth)
    contest_problem = _get_contest_problem_or_404(contest, problem_code, with_languages=True)
    problem = contest_problem.problem
    rendered_statement = str(markdown(problem.description, problem.markdown_style))

    participation = request.auth.profile.current_contest
    latest_submission = None
    if participation is not None and participation.contest_id == contest.id:
        latest_submission = (
            ContestSubmission.objects.select_related("submission")
            .filter(participation=participation, problem=contest_problem)
            .first()
        )

    return {
        **_serialize_contest_problem(contest, contest_problem),
        "statement": rendered_statement,
        "allowed_languages": list(problem.allowed_languages.values_list("key", flat=True)),
        "io_method": problem.io_method,
        "version_update": problem.version_update,
        "has_submission": latest_submission is not None,
        "latest_submission_id": latest_submission.submission_id if latest_submission is not None else None,
        "latest_submission_version": (
            latest_submission.submission.version_update if latest_submission is not None else None
        ),
    }


@router.get(
    "/contest/{contest_key}/problems/{problem_code}/submission/{submission_id}/",
    response=ContestSubmissionSourceSchema,
    auth=AccessJWTAuth(),
)
def get_contest_problem_submission_source(request, contest_key: str, problem_code: str, submission_id: int):
    participation = _get_current_participation_or_403(request.auth, contest_key)
    contest = participation.contest
    contest_problem = _get_contest_problem_or_404(contest, problem_code)

    contest_submission = (
        ContestSubmission.objects.select_related("submission", "submission__source", "submission__language")
        .filter(
            id=submission_id,
            participation=participation,
            problem=contest_problem,
        )
        .first()
    )
    if contest_submission is None:
        raise HttpError(404, "Contest submission not found")

    submission = contest_submission.submission
    source_obj = getattr(submission, "source", None)

    return {
        "contest_submission_id": contest_submission.id,
        "submission_id": submission.id,
        "language_key": submission.language.key if submission.language_id else None,
        "source": source_obj.source if source_obj is not None else "",
        "version_update": submission.version_update,
        "submitted_at": submission.date.isoformat(),
    }


@router.post(
    "/contest/{contest_key}/problems/{problem_code}/submit/",
    response=SubmitResponseSchema,
    auth=AccessJWTAuth(),
)
def submit_contest_problem(request, contest_key: str, problem_code: str, payload: SubmitRequestSchema):
    user = request.auth
    profile = user.profile
    participation = _get_current_participation_or_403(user, contest_key)
    contest = participation.contest

    if contest.start_time > timezone.now():
        raise HttpError(403, "Contest has not started yet")

    contest_problem = (
        contest.contest_problems.select_related("problem")
        .prefetch_related("problem__allowed_languages", "problem__banned_users")
        .filter(problem__code=problem_code)
        .first()
    )
    if contest_problem is None:
        raise HttpError(404, "Problem not found in contest")

    problem = contest_problem.problem

    try:
        language = Language.objects.get(key=payload.language_key)
    except Language.DoesNotExist:
        raise HttpError(400, "Language '%s' not found" % payload.language_key)

    if not problem.allowed_languages.filter(id=language.id).exists():
        raise HttpError(400, "Language '%s' is not allowed for this problem" % payload.language_key)

    if (
        not user.has_perm("judge.spam_submission")
        and Submission.objects.filter(user=profile, rejudged_date__isnull=True)
        .exclude(contest_object__isnull=False, contest_object__delay_contest=True)
        .exclude(status__in=["D", "IE", "CE", "AB"])
        .count()
        >= settings.DMOJ_SUBMISSION_LIMIT
    ):
        raise HttpError(429, "Too many pending submissions")

    existing_cs = (
        ContestSubmission.objects.select_related("submission", "submission__source")
        .filter(participation=participation, problem=contest_problem)
        .first()
    )

    replaced_existing = existing_cs is not None

    with transaction.atomic():
        if existing_cs is not None:
            submission = existing_cs.submission
            source_obj = submission.source

            try:
                backup_dir = Path("/tmp") / contest_key / user.username
                backup_dir.mkdir(parents=True, exist_ok=True)
                ts = int(time.time())
                backup_path = backup_dir / f"{problem_code}_{ts}.{language.extension}"
                backup_path.write_text(source_obj.source, encoding="utf-8")
            except OSError:
                pass

            submission.language = language
            submission.status = "QU"
            submission.result = None
            submission.error = None
            submission.time = None
            submission.memory = None
            submission.points = None
            submission.case_points = 0
            submission.case_total = 0
            submission.current_testcase = 0
            submission.rejudged_date = None
            if participation.live:
                submission.locked_after = contest.locked_after
            submission.save()

            source_obj.source = payload.source
            source_obj.save(update_fields=["source"])
        else:
            submission = Submission(
                user=profile,
                problem=problem,
                language=language,
                contest_object=contest,
            )
            if participation.live:
                submission.locked_after = contest.locked_after
            submission.save()

            SubmissionSource.objects.create(
                submission=submission,
                source=payload.source,
            )
            ContestSubmission.objects.create(
                submission=submission,
                problem=contest_problem,
                participation=participation,
            )

    if not contest.delay_contest:
        submission.judge(force_judge=True)

    return {
        "detail": "Submitted successfully",
        "submission_id": submission.id,
        "replaced_existing": replaced_existing,
    }


@router.get(
    "/contest/{contest_key}/problems/{problem_code}/submissions/",
    response=List[SubmissionItemSchema],
    auth=AccessJWTAuth(),
)
def list_contest_problem_submissions(request, contest_key: str, problem_code: str):
    participation = _get_current_participation_or_403(request.auth, contest_key)
    contest = participation.contest
    contest_problem = _get_contest_problem_or_404(contest, problem_code)

    submissions = (
        Submission.objects.filter(contest__participation=participation, contest__problem=contest_problem)
        .select_related("language", "source")
        .order_by("-date")
    )
    return [_serialize_submission(submission, include_source=True) for submission in submissions]
