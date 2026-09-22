from django.db.models import Max
from django.urls import reverse
from django.utils import timezone

from judge.jinja2.markdown import markdown
from judge.models import BlogPost, Comment, Contest, Judge, Problem, Profile, Submission
from judge.views.submission import group_test_cases


def serialize_profile_summary(profile):
    current_contest = profile.current_contest.contest.key if profile.current_contest else None
    organization = profile.organization
    return {
        "id": profile.id,
        "username": profile.user.username,
        "display_name": profile.name or profile.user.username,
        "rank": profile.display_rank,
        "points": profile.points,
        "performance_points": profile.performance_points,
        "problem_count": profile.problem_count,
        "rating": profile.rating,
        "organization": (
            {"id": organization.id, "name": organization.name, "short_name": organization.short_name}
            if organization
            else None
        ),
        "current_contest_key": current_contest,
        "is_staff": profile.user.is_staff,
        "is_superuser": profile.user.is_superuser,
    }


def serialize_problem_list_item(problem):
    return {
        "code": problem.code,
        "name": problem.name,
        "group": problem.group.full_name if problem.group else None,
        "types": list(problem.types.values_list("full_name", flat=True)),
        "points": problem.points,
        "partial": problem.partial,
        "is_public": problem.is_public,
        "is_organization_private": problem.is_organization_private,
    }


def serialize_problem_detail(problem, user):
    judges = Judge.objects.filter(online=True, problems=problem).order_by("name")
    latest_submission = None
    if user.is_authenticated:
        latest_submission = (
            Submission.objects.filter(problem=problem, user=user.profile)
            .order_by("-id")
            .only("id", "status", "result", "date")
            .first()
        )

    return {
        **serialize_problem_list_item(problem),
        "authors": list(problem.authors.values_list("user__username", flat=True)),
        "curators": list(problem.curators.values_list("user__username", flat=True)),
        "time_limit": problem.time_limit,
        "memory_limit": problem.memory_limit,
        "short_circuit": problem.short_circuit,
        "allowed_languages": list(problem.allowed_languages.values_list("key", flat=True)),
        "language_resource_limits": [
            {
                "language": key,
                "time_limit": time_limit,
                "memory_limit": memory_limit,
            }
            for key, time_limit, memory_limit in problem.language_limits.values_list(
                "language__key", "time_limit", "memory_limit"
            )
        ],
        "statement": problem.description,
        "io_method": problem.io_method,
        "can_edit": problem.is_editable_by(user),
        "can_submit": problem.is_accessible_by(user, skip_contest_problem_check=True),
        "online_judges": [
            {"name": judge.name, "ping": judge.ping_ms, "load": judge.load}
            for judge in judges
        ],
        "latest_submission": (
            {
                "id": latest_submission.id,
                "status": latest_submission.status,
                "result": latest_submission.result,
                "date": latest_submission.date.isoformat(),
            }
            if latest_submission
            else None
        ),
    }


def serialize_contest_list_item(contest, user):
    return {
        "key": contest.key,
        "name": contest.name,
        "start_time": contest.start_time.isoformat(),
        "end_time": contest.end_time.isoformat(),
        "time_limit": contest.time_limit.total_seconds() if contest.time_limit else None,
        "is_rated": contest.is_rated,
        "is_private": contest.is_private,
        "is_organization_private": contest.is_organization_private,
        "tags": list(contest.tags.values_list("name", flat=True)),
        "can_join": contest.is_joinable_by(user),
        "can_view_tasks": contest.can_view_tasks(user),
        "is_in_contest": contest.is_in_contest(user) if user.is_authenticated else False,
    }


def serialize_contest_detail(contest, user):
    can_see_rankings = contest.can_see_full_scoreboard(user)
    can_see_problems = contest.is_in_contest(user) or contest.ended or contest.is_editable_by(user)
    problems = list(
        contest.contest_problems.select_related("problem").order_by("order").defer("problem__description")
    )
    return {
        **serialize_contest_list_item(contest, user),
        "description": str(markdown(contest.description, contest.markdown_style)),
        "scoreboard_visibility": contest.scoreboard_visibility,
        "hidden_scoreboard": contest.scoreboard_visibility
        in (contest.SCOREBOARD_AFTER_CONTEST, contest.SCOREBOARD_AFTER_PARTICIPATION),
        "organizations": list(contest.organizations.values_list("id", flat=True)),
        "authors": list(contest.authors.values_list("user__username", flat=True)),
        "current_user_in_contest": contest.is_in_contest(user) if user.is_authenticated else False,
        "can_see_rankings": can_see_rankings,
        "can_see_problems": can_see_problems,
        "problems": [
            {
                "label": contest.get_label_for_problem(index),
                "code": contest_problem.problem.code,
                "name": contest_problem.problem.name,
                "order": contest_problem.order,
                "points": int(contest_problem.points),
                "partial": contest_problem.partial,
                "max_submissions": contest_problem.max_submissions,
            }
            for index, contest_problem in enumerate(problems)
        ]
        if can_see_problems
        else [],
    }


def serialize_submission_list_item(submission):
    return {
        "id": submission.id,
        "problem": submission.problem.code,
        "user": submission.user.user.username,
        "date": submission.date.isoformat(),
        "language": submission.language.key if submission.language else None,
        "time": submission.time,
        "memory": submission.memory,
        "points": submission.points,
        "result": submission.result,
        "status": submission.status,
    }


def serialize_submission_detail(submission):
    cases = []
    grouped_cases, _, _ = group_test_cases(submission.test_cases.all())
    for batch in grouped_cases:
        batch_cases = [
            {
                "case_id": case.case,
                "status": case.status,
                "time": case.time,
                "memory": case.memory,
                "points": case.points,
                "total": case.total,
            }
            for case in batch["cases"]
        ]
        if batch["id"] is None:
            cases.extend(batch_cases)
        else:
            cases.append(
                {
                    "batch_id": batch["id"],
                    "cases": batch_cases,
                    "points": batch["points"],
                    "total": batch["total"],
                }
            )

    return {
        **serialize_submission_list_item(submission),
        "case_points": submission.case_points,
        "case_total": submission.case_total,
        "cases": cases,
    }


def serialize_organization_list_item(organization):
    return {
        "id": organization.id,
        "slug": organization.slug,
        "name": organization.name,
        "short_name": organization.short_name,
        "is_open": organization.is_open,
        "is_hidden": organization.is_hidden,
        "logo_override_image": organization.logo_override_image,
        "member_count": getattr(organization, "member_count", None),
    }


def serialize_organization_detail(organization):
    members = (
        organization.members.filter(is_unlisted=False)
        .select_related("user")
        .order_by("-performance_points", "-problem_count")[:20]
    )
    return {
        **serialize_organization_list_item(organization),
        "about": organization.about,
        "creation_date": organization.creation_date.isoformat(),
        "admins": list(organization.admins.values_list("user__username", flat=True)),
        "members_preview": [serialize_profile_summary(member) for member in members],
    }


def serialize_user_detail(profile, viewer):
    ratings = profile.ratings.order_by("-contest__end_time").select_related("contest")
    last_rating = ratings.first()
    solved_problems = list(
        Submission.objects.filter(
            result="AC",
            user=profile,
            problem__is_public=True,
            problem__is_organization_private=False,
        )
        .values_list("problem__code", flat=True)
        .distinct()
    )
    authored = profile.authored_problems.filter(is_public=True, is_organization_private=False).order_by("code")

    return {
        **serialize_profile_summary(profile),
        "about": profile.about or "",
        "timezone": profile.timezone,
        "language": profile.language.key if profile.language else None,
        "organizations": [
            {"id": organization.id, "name": organization.name, "short_name": organization.short_name}
            for organization in profile.organizations.all()
        ],
        "authored_problems": [{"code": problem.code, "name": problem.name} for problem in authored],
        "solved_problems": solved_problems,
        "contest_history": [
            {
                "key": rating.contest.key,
                "name": rating.contest.name,
                "rating": rating.rating,
                "rank": rating.rank,
                "end_time": rating.contest.end_time.isoformat(),
            }
            for rating in ratings[:20]
        ],
        "rating": last_rating.rating if last_rating else None,
        "volatility": last_rating.volatility if last_rating else None,
        "editable_by_current_user": viewer.is_authenticated and viewer == profile.user,
    }


def serialize_comment_summary(comment):
    return {
        "id": comment.id,
        "author": comment.author.user.username,
        "page": comment.page,
        "page_title": comment.page_title,
        "link": comment.link,
        "time": comment.time.isoformat(),
        "score": comment.score,
    }


def get_home_payload(user):
    now = timezone.now()
    visible_contests = Contest.get_visible_contests(user).filter(is_visible=True).order_by("start_time")

    posts = (
        BlogPost.objects.filter(visible=True, publish_on__lte=now)
        .order_by("-sticky", "-publish_on")
        .prefetch_related("authors__user")[:5]
    )
    problems = Problem.get_public_problems().order_by("-date", "code")[:8]
    comments = Comment.most_recent(user, 8)

    current_contests = visible_contests.filter(start_time__lte=now, end_time__gt=now)[:8]
    future_contests = visible_contests.filter(start_time__gt=now)[:8]

    profile = user.profile if user.is_authenticated else None
    own_open_tickets = []
    if profile is not None:
        own_open_tickets = list(profile.ticket_set.filter(is_open=True).order_by("-id")[:10].values("id", "title"))

    return {
        "posts": [
            {
                "id": post.id,
                "slug": post.slug,
                "title": post.title,
                "summary": post.summary,
                "publish_on": post.publish_on.isoformat(),
                "authors": list(post.authors.values_list("user__username", flat=True)),
                "url": reverse("blog_post", args=[post.id, post.slug]),
            }
            for post in posts
        ],
        "new_problems": [serialize_problem_list_item(problem) for problem in problems],
        "recent_comments": [serialize_comment_summary(comment) for comment in comments],
        "current_contests": [serialize_contest_list_item(contest, user) for contest in current_contests],
        "future_contests": [serialize_contest_list_item(contest, user) for contest in future_contests],
        "stats": {
            "users": Profile.objects.count(),
            "problems": Problem.get_public_problems().count(),
            "submissions": Submission.objects.aggregate(max_id=Max("id"))["max_id"] or 0,
            "judges_online": Judge.objects.filter(online=True).count(),
        },
        "own_open_tickets": own_open_tickets,
    }
