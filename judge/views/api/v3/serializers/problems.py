from judge.models import Judge, Submission


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
