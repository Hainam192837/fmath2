from ninja.errors import HttpError

from judge.models import Contest


def get_contest_or_404(contest_key: str) -> Contest:
    try:
        return Contest.objects.get(key=contest_key)
    except Contest.DoesNotExist:
        raise HttpError(404, "Contest not found")


def require_contest_access(contest: Contest, user) -> Contest:
    if not contest.is_accessible_by(user):
        raise HttpError(403, "You do not have permission to access this contest")
    return contest


def require_contest_joinable(contest: Contest, user) -> Contest:
    if not contest.is_joinable_by(user):
        raise HttpError(403, "You do not have permission to access this contest")
    return contest


def get_contest_problem_or_404(contest: Contest, problem_code: str, with_languages: bool = False):
    queryset = contest.contest_problems.select_related("problem")
    if with_languages:
        queryset = queryset.prefetch_related("problem__allowed_languages")

    contest_problem = queryset.filter(problem__code=problem_code).first()
    if contest_problem is None:
        raise HttpError(404, "Problem not found in contest")
    return contest_problem


def get_current_participation_or_403(user, contest_key: str):
    profile = user.profile
    if profile.current_contest is None or profile.current_contest.contest.key != contest_key:
        raise HttpError(403, 'You are not in contest "%s"' % contest_key)
    return profile.current_contest
