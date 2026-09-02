import time
from pathlib import Path
from typing import List, Optional

import jwt
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError
from ninja.security import HttpBearer

from judge.jinja2.markdown import markdown
from judge.models import Contest, ContestParticipation, ContestSubmission, Language, Submission, SubmissionSource
from judge.views.api.auth import get_jwt_secret

router = Router(tags=["app"])


class ContestListItemSchema(Schema):
    pk: int
    key: str
    name: str
    topic: str
    start_time: str
    end_time: str


class ContestDetailSchema(ContestListItemSchema):
    description: str
    user_count: int


class ContestProblemItemSchema(Schema):
    code: str
    title: str
    order: int
    points: int
    time_limit: float
    memory_limit: int


class ProblemDetailSchema(ContestProblemItemSchema):
    statement: str
    allowed_languages: List[str]
    io_method: dict


class LoginRequestSchema(Schema):
    username: str
    password: str


class LoginResponseSchema(Schema):
    access_token: str
    token_type: str
    expires_in: int


def _create_access_token(user, expires_in: int) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "is_staff": user.is_staff,
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm="HS256")


def _verify_access_token(token: str):
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None

    user_id = payload.get("sub")
    if user_id is None:
        return None

    User = get_user_model()
    return User.objects.filter(id=user_id, is_active=True).select_related("profile").first()


class JWTAuth(HttpBearer):
    def authenticate(self, request, token):
        user = _verify_access_token(token)
        if user is None:
            raise HttpError(401, "Invalid or expired token")
        return user


@router.get("/contests/", response=List[ContestListItemSchema], auth=JWTAuth())
def list_contests(request):
    contests = (
        Contest.get_visible_contests(request.auth)
        .filter(is_exam_contest=True)
        .exclude(end_time__lt=timezone.now())
        .order_by("start_time")
    )

    return [
        {
            "pk": contest.pk,
            "key": contest.key,
            "name": contest.name,
            "topic": contest.topic,
            "start_time": contest.start_time.isoformat(),
            "end_time": contest.end_time.isoformat(),
        }
        for contest in contests
    ]


@router.get("/contest/{contest_key}/", response=ContestDetailSchema, auth=JWTAuth())
def get_contest_detail(request, contest_key: str):
    try:
        contest = Contest.objects.get(key=contest_key)
    except Contest.DoesNotExist:
        raise HttpError(404, "Contest not found")

    if not contest.is_accessible_by(request.auth):
        raise HttpError(403, "You do not have permission to access this contest")

    return {
        "pk": contest.pk,
        "key": contest.key,
        "name": contest.name,
        "topic": contest.topic,
        "description": contest.description,
        "start_time": contest.start_time.isoformat(),
        "end_time": contest.end_time.isoformat(),
        "user_count": contest.user_count,
    }


@router.get("/contest/{contest_key}/problems/", response=List[ContestProblemItemSchema], auth=JWTAuth())
def list_contest_problems(request, contest_key: str):
    try:
        contest = Contest.objects.get(key=contest_key)
    except Contest.DoesNotExist:
        raise HttpError(404, "Contest not found")

    if not contest.is_joinable_by(request.auth):
        raise HttpError(403, "You do not have permission to access this contest")

    # can_see_problems = (
    #     contest.is_in_contest(request.auth)
    #     or contest.ended
    #     or contest.is_editable_by(request.auth)
    # )
    # if not can_see_problems:
    #     return []

    contest_problems = (
        contest.contest_problems.select_related("problem").defer("problem__description").order_by("order")
    )

    return [
        {
            "code": contest_problem.problem.code,
            "title": contest_problem.problem.name,
            "order": contest_problem.order,
            "points": int(contest_problem.points),
            "time_limit": contest_problem.problem.time_limit,
            "memory_limit": contest_problem.problem.memory_limit,
        }
        for contest_problem in contest_problems
    ]


@router.get("/contest/{contest_key}/problems/{problem_code}/", response=ProblemDetailSchema, auth=JWTAuth())
def get_contest_problem_detail(request, contest_key: str, problem_code: str):
    try:
        contest = Contest.objects.get(key=contest_key)
    except Contest.DoesNotExist:
        raise HttpError(404, "Contest not found")

    if not contest.is_joinable_by(request.auth):
        raise HttpError(403, "You do not have permission to access this contest")

    contest_problem = (
        contest.contest_problems.select_related("problem")
        .prefetch_related("problem__allowed_languages")
        .filter(problem__code=problem_code)
        .first()
    )
    if contest_problem is None:
        raise HttpError(404, "Problem not found in contest")

    problem = contest_problem.problem
    rendered_statement = str(markdown(problem.description, problem.markdown_style))

    return {
        "code": problem.code,
        "title": problem.name,
        "order": contest_problem.order,
        "points": int(contest_problem.points),
        "time_limit": problem.time_limit,
        "memory_limit": problem.memory_limit,
        "statement": rendered_statement,
        "allowed_languages": list(problem.allowed_languages.values_list("name", flat=True)),
        "io_method": problem.io_method,
    }


class ContestJoinRequestSchema(Schema):
    access_code: Optional[str] = None


class MessageSchema(Schema):
    detail: str


@router.post("/contest/{contest_key}/join/", response=MessageSchema, auth=JWTAuth())
def join_contest(request, contest_key: str, payload: ContestJoinRequestSchema = None):
    user = request.auth
    profile = user.profile

    try:
        contest = Contest.objects.get(key=contest_key)
    except Contest.DoesNotExist:
        raise HttpError(404, "Contest not found")

    if not contest.is_accessible_by(user):
        raise HttpError(403, "You do not have permission to access this contest")

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
                pass
            else:
                break
    else:
        SPECTATE = ContestParticipation.SPECTATE
        LIVE = ContestParticipation.LIVE
        if not is_editor and requires_access_code:
            raise HttpError(403, "Access code required")
        try:
            participation = ContestParticipation.objects.get(
                contest=contest,
                user=profile,
                virtual=(SPECTATE if is_editor or is_tester else LIVE),
            )
        except ContestParticipation.DoesNotExist:
            if requires_access_code:
                raise HttpError(403, "Access code required")
            participation = ContestParticipation.objects.create(
                contest=contest,
                user=profile,
                virtual=(SPECTATE if is_editor or is_tester else LIVE),
                real_start=timezone.now(),
            )
        else:
            if participation.ended:
                participation = ContestParticipation.objects.get_or_create(
                    contest=contest,
                    user=profile,
                    virtual=SPECTATE,
                    defaults={"real_start": timezone.now()},
                )[0]

    profile.current_contest = participation
    profile.save()
    contest._updating_stats_only = True
    contest.update_user_count()
    return {"detail": "Successfully joined the contest"}


@router.post("/contest/{contest_key}/leave/", response=MessageSchema, auth=JWTAuth())
def leave_contest(request, contest_key: str):
    user = request.auth
    profile = user.profile

    if profile.current_contest is None or profile.current_contest.contest.key != contest_key:
        raise HttpError(400, 'You are not in contest "%s"' % contest_key)

    contest = Contest.objects.get(key=contest_key)
    if contest.forbidden_leave:
        raise HttpError(403, 'You are not allowed to leave contest "%s" at this time' % contest.name)

    profile.remove_contest()
    return {"detail": "Successfully left the contest"}


class CurrentContestSchema(Schema):
    pk: int


class SubmitRequestSchema(Schema):
    language_key: str
    source: str


class SubmitResponseSchema(Schema):
    detail: str
    submission_id: int


class ExistingSubmissionCheckSchema(Schema):
    has_submission: bool
    submission_id: Optional[int] = None
    version_update: Optional[int] = None


class ExistingSubmissionCodeSchema(Schema):
    submission_id: int
    language_key: Optional[str] = None
    source: str


class VersionUpdateSchema(Schema):
    version_update: int


@router.get("/contests/current/", response=Optional[CurrentContestSchema], auth=JWTAuth())
def get_current_contest(request):
    profile = request.auth.profile
    if profile.current_contest is None:
        return None
    participation = profile.current_contest
    contest = participation.contest
    return {
        "pk": contest.pk,
    }


@router.get("/contest/{contest_key}/version/", response=VersionUpdateSchema, auth=JWTAuth())
def check_contest_version(request, contest_key: str):
    try:
        contest = Contest.objects.only("id", "version_update").get(key=contest_key)
    except Contest.DoesNotExist:
        raise HttpError(404, "Contest not found")

    if not contest.is_accessible_by(request.auth):
        raise HttpError(403, "You do not have permission to access this contest")

    return {
        "version_update": contest.version_update,
    }


@router.get(
    "/contest/{contest_key}/problems/{problem_code}/version/",
    response=VersionUpdateSchema,
    auth=JWTAuth(),
)
def check_contest_problem_version(request, contest_key: str, problem_code: str):
    try:
        contest = Contest.objects.get(key=contest_key)
    except Contest.DoesNotExist:
        raise HttpError(404, "Contest not found")

    if not contest.is_accessible_by(request.auth):
        raise HttpError(403, "You do not have permission to access this contest")

    contest_problem = (
        contest.contest_problems.select_related("problem")
        .only("problem__version_update")
        .filter(problem__code=problem_code)
        .first()
    )
    if contest_problem is None:
        raise HttpError(404, "Problem not found in contest")

    return {
        "version_update": contest_problem.problem.version_update,
    }


@router.post("/contest/{contest_key}/problems/{problem_code}/submit/", response=SubmitResponseSchema, auth=JWTAuth())
def submit_contest_problem(request, contest_key: str, problem_code: str, payload: SubmitRequestSchema):
    user = request.auth
    profile = user.profile

    if profile.current_contest is None or profile.current_contest.contest.key != contest_key:
        raise HttpError(403, 'You are not in contest "%s"' % contest_key)

    participation = profile.current_contest
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

    if not user.is_superuser and problem.banned_users.filter(id=profile.id).exists():
        raise HttpError(403, "You have been banned from submitting this problem")

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

    with transaction.atomic():
        if existing_cs is not None:
            submission = existing_cs.submission
            src_obj = submission.source

            # Backup old source
            try:
                backup_dir = Path("/tmp") / contest_key / user.username
                backup_dir.mkdir(parents=True, exist_ok=True)
                ts = int(time.time())
                backup_path = backup_dir / f"{problem_code}_{ts}.{language.extension}"
                backup_path.write_text(src_obj.source, encoding="utf-8")
            except OSError:
                pass

            # Update submission metadata
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

            src_obj.source = payload.source
            src_obj.save(update_fields=["source"])
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

            SubmissionSource(
                submission=submission,
                source=payload.source,
            ).save()

            ContestSubmission(
                submission=submission,
                problem=contest_problem,
                participation=participation,
            ).save()

    if not contest.delay_contest:
        submission.judge(force_judge=True)

    return {"detail": "Submitted successfully", "submission_id": submission.id}


def _get_current_contest_problem_submission(request, contest_key: str, problem_code: str):
    user = request.auth
    profile = user.profile

    if profile.current_contest is None or profile.current_contest.contest.key != contest_key:
        raise HttpError(403, 'You are not in contest "%s"' % contest_key)

    participation = profile.current_contest
    contest = participation.contest

    contest_problem = contest.contest_problems.select_related("problem").filter(problem__code=problem_code).first()
    if contest_problem is None:
        raise HttpError(404, "Problem not found in contest")

    return (
        ContestSubmission.objects.select_related("submission", "submission__source", "submission__language")
        .filter(participation=participation, problem=contest_problem)
        .first()
    )


@router.get(
    "/contest/{contest_key}/problems/{problem_code}/submission/exists/",
    response=ExistingSubmissionCheckSchema,
    auth=JWTAuth(),
)
def check_existing_contest_submission(request, contest_key: str, problem_code: str):
    existing_cs = _get_current_contest_problem_submission(request, contest_key, problem_code)

    if existing_cs is None:
        return {
            "has_submission": False,
            "submission_id": None,
            "version_update": None,
        }

    submission = existing_cs.submission

    return {
        "has_submission": True,
        "submission_id": submission.id,
        "version_update": submission.version_update,
    }


@router.get(
    "/contest/{contest_key}/problems/{problem_code}/submission/source/",
    response=ExistingSubmissionCodeSchema,
    auth=JWTAuth(),
)
def get_existing_contest_submission_source(request, contest_key: str, problem_code: str):
    existing_cs = _get_current_contest_problem_submission(request, contest_key, problem_code)

    if existing_cs is None:
        raise HttpError(404, "Submission not found")

    submission = existing_cs.submission
    source_obj = getattr(submission, "source", None)

    return {
        "submission_id": submission.id,
        "language_key": submission.language.key if submission.language_id else None,
        "source": source_obj.source if source_obj is not None else "",
    }


@router.post("/auth/login/", response=LoginResponseSchema, auth=None)
def login(request, payload: LoginRequestSchema):
    user = authenticate(request, username=payload.username, password=payload.password)
    if user is None or not user.is_active:
        raise HttpError(401, "Invalid credentials")

    expires_in = int(getattr(settings, "DMOJ_API_JWT_EXP_SECONDS", 1800))
    access_token = _create_access_token(user, expires_in=expires_in)
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": expires_in,
    }
