import time
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from ninja import Query, Router, Schema
from ninja.errors import HttpError

from judge.models import ContestSubmission, Language, Problem, Submission
from judge.models.submission import SubmissionSource
from judge.views.api.v3.permissions import require_authenticated
from judge.views.api.v3.schemas.submission import (
    ContestSubmissionItemSchema,
    ContestSubmissionSourceSchema,
    SubmissionDetailSchema,
    SubmissionListItemSchema,
    SubmitRequestSchema,
    SubmitResponseSchema,
)
from judge.views.api.v3.serializers.submissions import (
    serialize_contest_submission,
    serialize_contest_submission_source,
    serialize_submission_detail,
    serialize_submission_list_item,
)
from judge.views.api.v3.services.contests import get_contest_problem_or_404, get_current_participation_or_403

router = Router(tags=["submissions"])


class SubmissionListFilters(Schema):
    user: str | None = None
    problem: str | None = None
    result: str | None = None
    page: int = 1
    page_size: int = 20


@router.get("/submissions", response=list[SubmissionListItemSchema])
def list_submissions(request, filters: Query[SubmissionListFilters]):
    user = require_authenticated(request)
    queryset = Submission.objects.select_related("problem", "user__user", "language").order_by("-id")
    queryset = queryset.filter(problem__in=Problem.get_visible_problems(user).values("id"))

    if filters.user:
        queryset = queryset.filter(user__user__username=filters.user)
    if filters.problem:
        queryset = queryset.filter(problem__code=filters.problem)
    if filters.result:
        queryset = queryset.filter(result=filters.result)

    start = max(filters.page - 1, 0) * filters.page_size
    end = start + filters.page_size
    data = [serialize_submission_list_item(submission) for submission in queryset[start:end]]
    response = JsonResponse(data, safe=False)
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


@router.get("/submissions/{submission_id}", response=SubmissionDetailSchema)
def get_submission(request, submission_id: int):
    user = require_authenticated(request)
    try:
        submission = Submission.objects.select_related("problem", "user__user", "language").prefetch_related(
            "test_cases"
        ).get(id=submission_id)
    except Submission.DoesNotExist:
        raise HttpError(404, "Submission not found")

    if not submission.can_see_detail(user):
        raise HttpError(403, "Permission denied")

    data = serialize_submission_detail(submission)
    response = JsonResponse(data)
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


@router.post(
    "/contests/{contest_key}/problems/{problem_code}/submit",
    response=SubmitResponseSchema,
)
def submit_contest_problem(request, contest_key: str, problem_code: str, payload: SubmitRequestSchema):
    user = require_authenticated(request)
    profile = user.profile
    participation = get_current_participation_or_403(user, contest_key)
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
                backup_path = backup_dir / f"{problem_code}_{int(time.time())}.{language.extension}"
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
    "/contests/{contest_key}/problems/{problem_code}/submissions",
    response=list[ContestSubmissionItemSchema],
)
def list_contest_problem_submissions(request, contest_key: str, problem_code: str):
    participation = get_current_participation_or_403(require_authenticated(request), contest_key)
    contest_problem = get_contest_problem_or_404(participation.contest, problem_code)

    submissions = (
        Submission.objects.filter(contest__participation=participation, contest__problem=contest_problem)
        .select_related("language", "source")
        .order_by("-date")
    )
    return [serialize_contest_submission(submission, include_source=True) for submission in submissions]


@router.get(
    "/contests/{contest_key}/problems/{problem_code}/submission/{contest_submission_id}",
    response=ContestSubmissionSourceSchema,
)
def get_contest_problem_submission_source(
    request,
    contest_key: str,
    problem_code: str,
    contest_submission_id: int,
):
    participation = get_current_participation_or_403(require_authenticated(request), contest_key)
    contest_problem = get_contest_problem_or_404(participation.contest, problem_code)

    contest_submission = (
        ContestSubmission.objects.select_related("submission", "submission__source", "submission__language")
        .filter(
            id=contest_submission_id,
            participation=participation,
            problem=contest_problem,
        )
        .first()
    )
    if contest_submission is None:
        raise HttpError(404, "Contest submission not found")

    return serialize_contest_submission_source(contest_submission)
