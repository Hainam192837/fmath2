from judge.jinja2.markdown import markdown


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
                **serialize_contest_problem(contest, contest_problem, index),
            }
            for index, contest_problem in enumerate(problems)
        ]
        if can_see_problems
        else [],
    }


def serialize_contest_problem(contest, contest_problem, index: int | None = None):
    problem = contest_problem.problem
    if index is None:
        index = contest_problem.order - 1

    label = None
    if hasattr(contest, "get_label_for_problem"):
        label = contest.get_label_for_problem(index)

    return {
        "label": label,
        "code": problem.code,
        "name": problem.name,
        "title": problem.name,
        "order": contest_problem.order,
        "points": int(contest_problem.points),
        "partial": contest_problem.partial,
        "time_limit": problem.time_limit,
        "memory_limit": problem.memory_limit,
        "max_submissions": contest_problem.max_submissions or None,
    }


def serialize_leaderboard_entry(rank, entry):
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
