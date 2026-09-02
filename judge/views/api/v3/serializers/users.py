from judge.models import Submission


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
