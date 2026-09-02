import json
import zipfile
from collections import defaultdict
from functools import partial
from operator import attrgetter, itemgetter
from typing import Any

from django import forms
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db import transaction
from django.db.models import Case, Count, FloatField, IntegerField, Value, When
from django.db.models.expressions import CombinedExpression
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.views.generic import DetailView, FormView, View
from django.views.generic.detail import SingleObjectMixin

from judge.models import (
    Contest,
    ContestMoss,
    ContestParticipation,
    ContestProblem,
    ContestSubmission,
    Profile,
    Submission,
    SubmissionSource,
)
from judge.models.runtime import Language
from judge.tasks import run_moss
from judge.utils.celery import redirect_to_task_status
from judge.utils.problems import _get_result_data
from judge.utils.stats import get_bar_chart, get_pie_chart
from judge.utils.views import TitleMixin, generic_message

from .base import ContestMixin

EXTS = (".c", ".cpp", ".java", ".py", ".pas")

LANGS = {
    "c": "C",
    "cpp": "CPP17",
    "java": "JAVA8",
    "py": "PY3",
    "pas": "PAS",
}


class ContestStats(TitleMixin, ContestMixin, DetailView):
    template_name = "contest/stats.html"

    def get_title(self):
        return _("%s Statistics") % self.object.name

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if not (self.object.ended or self.can_edit):
            raise Http404()

        queryset = Submission.objects.filter(contest_object=self.object)
        ac_count = Count(Case(When(result="AC", then=Value(1)), output_field=IntegerField()))
        ac_rate = CombinedExpression(ac_count / Count("problem"), "*", Value(100.0), output_field=FloatField())

        status_count_queryset = list(
            queryset.values("problem__code", "result")
            .annotate(count=Count("result"))
            .values_list("problem__code", "result", "count"),
        )
        labels, codes = [], []
        contest_problems = self.object.contest_problems.order_by("order").values_list(
            "problem__name",
            "problem__code",
        )
        if contest_problems:
            labels, codes = zip(*contest_problems)
        num_problems = len(labels)
        status_counts = [[] for _ in range(num_problems)]
        for problem_code, result, count in status_count_queryset:
            if problem_code in codes:
                status_counts[codes.index(problem_code)].append((result, count))

        result_data = defaultdict(partial(list, [0] * num_problems))
        for i in range(num_problems):
            for category in _get_result_data(defaultdict(int, status_counts[i]))["categories"]:
                result_data[category["code"]][i] = category["count"]

        stats = {
            "problem_status_count": {
                "labels": labels,
                "datasets": [
                    {
                        "label": name,
                        "backgroundColor": settings.DMOJ_STATS_SUBMISSION_RESULT_COLORS[name],
                        "data": data,
                    }
                    for name, data in result_data.items()
                ],
            },
            "problem_ac_rate": get_bar_chart(
                queryset.values("contest__problem__order", "problem__name")
                .annotate(ac_rate=ac_rate)
                .order_by("contest__problem__order")
                .values_list("problem__name", "ac_rate"),
            ),
            "language_count": get_pie_chart(
                queryset.values("language__name")
                .annotate(count=Count("language__name"))
                .filter(count__gt=0)
                .order_by("-count")
                .values_list("language__name", "count"),
            ),
            "language_ac_rate": get_bar_chart(
                queryset.values("language__name")
                .annotate(ac_rate=ac_rate)
                .filter(ac_rate__gt=0)
                .values_list("language__name", "ac_rate"),
            ),
        }

        context["stats"] = mark_safe(json.dumps(stats))
        return context


class ContestMossMixin(ContestMixin, PermissionRequiredMixin):
    permission_required = "judge.moss_contest"

    def get_object(self, queryset=None):
        contest = super().get_object(queryset)
        if settings.MOSS_API_KEY is None or not contest.is_editable_by(self.request.user):
            raise Http404()
        return contest


class ContestMossView(ContestMossMixin, TitleMixin, DetailView):
    template_name = "contest/moss.html"

    def get_title(self):
        return _("%s MOSS Results") % self.object.name

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        problems = list(
            map(
                attrgetter("problem"),
                self.object.contest_problems.order_by("order").select_related("problem"),
            ),
        )
        languages = list(map(itemgetter(0), ContestMoss.LANG_MAPPING))

        results = ContestMoss.objects.filter(contest=self.object)
        moss_results = defaultdict(list)
        for result in results:
            moss_results[result.problem].append(result)

        for result_list in moss_results.values():
            result_list.sort(key=lambda x: languages.index(x.language))

        context["languages"] = languages
        context["has_results"] = results.exists()
        context["moss_results"] = [(problem, moss_results[problem]) for problem in problems]
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        status = run_moss.delay(self.object.key)
        return redirect_to_task_status(
            status,
            message=_("Running MOSS for %s...") % (self.object.name,),
            redirect=reverse("contest_moss", args=(self.object.key,)),
        )


class ContestMossDelete(ContestMossMixin, SingleObjectMixin, View):
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        ContestMoss.objects.filter(contest=self.object).delete()
        return HttpResponseRedirect(reverse("contest_moss", args=(self.object.key,)))


class ContestDataForm(forms.Form):
    upload = forms.FileField(label="Contest data", required=True, validators=[lambda f: f.name.endswith(".zip")])
    clear = forms.BooleanField(label="Clear all data", required=False)


class ContestDataView(LoginRequiredMixin, PermissionRequiredMixin, TitleMixin, FormView):
    template_name = "contest/contest_data.html"
    form_class = ContestDataForm
    contest: Contest | None
    success_url = "/contest/{}"

    def get_success_url(self):
        return self.success_url.format(self.contest.key)

    def has_permission(self):
        return self.request.user.is_superuser

    def get_contest(self):
        return get_object_or_404(Contest, key=self.kwargs["contest"])

    def get_title(self):
        return "Contest data"

    def get_data(self, upload):
        data = {}
        with zipfile.ZipFile(upload, "r") as zip_ref:
            for file in zip_ref.namelist():
                if not file.endswith(EXTS):
                    continue
                temp = file.split("/")
                if len(temp) != 2:
                    continue
                id = temp[0].split("_")[0]
                try:
                    id = int(id)
                except ValueError:
                    continue
                try:
                    source = zip_ref.open(file).read().decode("utf-8")
                except UnicodeDecodeError:
                    from sys import stderr

                    print(file, file=stderr)
                    continue

                ext = file.split(".")[-1]
                if id not in data:
                    data[id] = {}
                basename = temp[1].upper().split(".")[0]
                if len(basename) != 1:
                    continue
                order = ContestProblem.get_order(basename)
                data[id][order] = (source, LANGS[ext])
        return data

    def post(self, request: HttpRequest, *args: str, **kwargs: Any) -> HttpResponse:
        try:
            self.contest = self.get_contest()
        except Http404:
            return generic_message(
                request,
                _("Contest not found"),
                _("The contest you are looking for does not exist."),
                status=404,
            )
        return super().post(request, *args, **kwargs)

    def form_valid(self, form: Any) -> HttpResponse:
        data = self.get_data(form.cleaned_data["upload"])

        user_ids = list(map(int, data.keys()))
        users = Profile.objects.filter(pk__in=user_ids).order_by("pk")
        problems = ContestProblem.objects.filter(contest=self.contest).order_by("order")
        languages = Language.objects.all()

        with transaction.atomic():
            if form.cleaned_data["clear"]:
                Submission.objects.filter(contest_object=self.contest).delete()
                self.contest.users.all().delete()
            else:
                Submission.objects.filter(user__in=users, contest_object=self.contest).delete()
                ContestParticipation.objects.filter(user__in=users, contest=self.contest).delete()

            participations = ContestParticipation.objects.bulk_create(
                [ContestParticipation(user=user, contest=self.contest) for user in users]
            )

            for participation in participations:
                for problem in problems:
                    if problem.order not in data[participation.user.pk]:
                        continue
                    source, lang = data[participation.user.pk][problem.order]

                    submission = Submission.objects.create(
                        user=participation.user,
                        problem=problem.problem,
                        language=languages.get(key=lang),
                        contest_object=self.contest,
                        date=self.contest.start_time,
                    )

                    SubmissionSource.objects.create(
                        submission=submission,
                        source=source,
                    )

                    ContestSubmission.objects.create(
                        submission=submission,
                        problem=problem,
                        participation=participation,
                    )

        self.contest.update_user_count()
        return super().form_valid(form)
