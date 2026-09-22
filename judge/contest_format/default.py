from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db.models import Max
from django.template.defaultfilters import floatformat
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy

from judge.contest_format.base import BaseContestFormat
from judge.contest_format.registry import register_contest_format
from judge.utils.timedelta import nice_repr


@register_contest_format("default")
class DefaultContestFormat(BaseContestFormat):
    name = gettext_lazy("Default")

    @classmethod
    def validate(cls, config):
        if config is not None and (not isinstance(config, dict) or config):
            raise ValidationError("default contest expects no config or empty dict as config")

    def __init__(self, contest, config):
        super(DefaultContestFormat, self).__init__(contest, config)

    def empty_problem_cell_data(self):
        return {
            "has_data": False,
            "state": "unsubmitted",
        }

    def build_problem_cell_data(self, participation, contest_problem, *, points, time, state, penalty=-1, bonus=None):
        return {
            "has_data": True,
            "problem": contest_problem.order,
            "username": participation.user.user.username,
            "url": reverse(
                "user_contest_problem_submissions",
                args=[self.contest.key, contest_problem.order, participation.user.user.username],
            ),
            "penalty": penalty,
            "bonus": bonus,
            "points": points,
            "time": time,
            "state": state,
        }

    def update_participation(self, participation):
        cumtime = 0
        points = 0
        format_data = {}

        for result in participation.submissions.values("problem_id").annotate(
            time=Max("submission__date"),
            points=Max("points"),
        ):
            dt = (result["time"] - participation.start).total_seconds()
            if result["points"]:
                cumtime += dt
            format_data[str(result["problem_id"])] = {"time": dt, "points": result["points"]}
            points += result["points"]

        participation.cumtime = max(cumtime, 0)
        participation.score = round(points, self.contest.points_precision)
        participation.tiebreaker = 0
        participation.format_data = self.attach_participation_metadata(participation, format_data)
        participation.save()

    def display_user_problem(self, participation, contest_problem):
        format_data = (participation.format_data or {}).get(str(contest_problem.id))
        if format_data:
            return self.build_problem_cell_data(
                participation,
                contest_problem,
                penalty=-1,
                points=floatformat(format_data["points"]),
                time=nice_repr(timedelta(seconds=format_data["time"]), "noday"),
                state=("pretest-" if self.contest.run_pretests_only and contest_problem.is_pretested else "")
                + self.best_solution_state(format_data["points"], contest_problem.points),
            )
        return self.empty_problem_cell_data()

    def display_participation_result(self, participation):
        return format_html(
            """<td class="ranking-result-cell">
                <a class="ranking-result-link" href="{url}">
                    <span class="text-[0.95rem] font-extrabold leading-none">{points}</span>
                    <span class="solving-time">{cumtime}</span>
                </a>
            </td>""",
            url=reverse("contest_all_user_submissions", args=[self.contest.key, participation.user.user.username]),
            points=floatformat(participation.score, -self.contest.points_precision),
            cumtime=nice_repr(timedelta(seconds=participation.cumtime), "noday"),
        )

    def get_problem_breakdown(self, participation, contest_problems):
        return [(participation.format_data or {}).get(str(contest_problem.id)) for contest_problem in contest_problems]

    def get_label_for_problem(self, index):
        return str(index + 1)
