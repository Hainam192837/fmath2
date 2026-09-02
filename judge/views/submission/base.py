import datetime
import json

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch, Q
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.generic import DetailView, ListView

from judge.models import Contest, ContestSubmission, Language, Problem, ProblemTranslation, Submission
from judge.utils.problems import get_result_data, user_completed_ids, user_editable_ids, user_tester_ids
from judge.utils.raw_sql import use_straight_join
from judge.utils.views import DiggPaginatorMixin, TitleMixin


def submission_related(queryset):
    return (
        queryset.select_related("user__user", "problem", "language")
        .only(
            "id",
            "user__user__username",
            "user__display_rank",
            "user__rating",
            "problem__name",
            "problem__code",
            "problem__is_public",
            "language__short_name",
            "language__key",
            "date",
            "time",
            "memory",
            "points",
            "result",
            "status",
            "case_points",
            "case_total",
            "current_testcase",
            "contest_object",
            "locked_after",
            "problem__submission_source_visibility_mode",
        )
        .prefetch_related(
            "contest_object__authors",
            "contest_object__curators",
            Prefetch("contest", queryset=ContestSubmission.objects.select_related("problem")),
        )
    )


class SubmissionMixin(object):
    model = Submission
    context_object_name = "submission"
    pk_url_kwarg = "submission"


class SubmissionDetailBase(LoginRequiredMixin, TitleMixin, SubmissionMixin, DetailView):
    def get_object(self, queryset=None):
        submission = super(SubmissionDetailBase, self).get_object(queryset)
        if not submission.can_see_detail(self.request.user):
            raise PermissionDenied()
        return submission

    def get_title(self) -> str:
        submission: Submission = self.object
        name = submission.problem_name
        return _(f"Submission of {name} by {submission.user.user.username}")

    def get_content_title(self):
        submission: Submission = self.object
        problem_name = submission.problem_name
        problem_link = submission.problem_link
        return mark_safe(
            escape(_("Submission of %(problem)s by %(user)s"))
            % {
                "problem": format_html('<a href="{0}" class="text-blue-500">{1}</a>', problem_link, problem_name),
                "user": format_html(
                    '<a href="{0}" class="text-blue-500">{1}</a>',
                    reverse("user_page", args=[submission.user.user.username]),
                    submission.user.user.username,
                ),
            }
        )


def filter_submissions_by_visible_problems(queryset, user):
    problems = Problem.get_visible_problems(user).distinct().values_list("id", flat=True)
    queryset = queryset.filter(problem_id__in=problems)


class SubmissionsListBase(DiggPaginatorMixin, TitleMixin, ListView):
    model = Submission
    paginate_by = 50
    show_problem = True
    title = gettext_lazy("All submissions")
    content_title = gettext_lazy("All submissions")
    tab = "all_submissions_list"
    nav_tag = "submission"
    template_name = "submission/list.html"
    context_object_name = "submissions"
    first_page_href = None

    def get_result_data(self):
        result = self._get_result_data()
        for category in result["categories"]:
            category["name"] = _(category["name"])
        return result

    def _get_result_data(self, queryset=None):
        if queryset is None:
            queryset = self.get_queryset()
        return get_result_data(queryset.order_by())

    def access_check(self, request):
        pass

    @cached_property
    def in_contest(self):
        return self.request.user.is_authenticated and self.request.profile.current_contest is not None

    @cached_property
    def contest(self):
        return self.request.profile.current_contest.contest

    def _get_queryset(self):
        past_30days = timezone.now() - datetime.timedelta(days=30)
        if self.request.user.is_authenticated and self.request.user.is_superuser:
            queryset = Submission.objects.all()
        else:
            queryset = Submission.objects.filter(date__gt=past_30days)
        use_straight_join(queryset)
        queryset = submission_related(queryset.order_by("-id"))
        if self.show_problem:
            queryset = queryset.prefetch_related(
                Prefetch(
                    "problem__translations",
                    queryset=ProblemTranslation.objects.filter(language=self.request.LANGUAGE_CODE),
                    to_attr="_trans",
                )
            )
        if self.in_contest:
            queryset = queryset.filter(contest_object=self.contest)
            if not self.contest.can_see_full_scoreboard(self.request.user):
                queryset = queryset.filter(user=self.request.profile)
        else:
            queryset = queryset.select_related("contest_object").defer("contest_object__description")

            if not self.request.user.has_perm("judge.see_private_contest"):
                contest_filter = Q(scoreboard_visibility=Contest.SCOREBOARD_VISIBLE) | Q(end_time__lt=timezone.now())
                submission_filter = Q(contest_object__isnull=True)

                if self.request.user.is_authenticated:
                    contest_filter |= Q(authors=self.request.profile) | Q(curators=self.request.profile)
                    submission_filter |= Q(user=self.request.profile)

                contest_queryset = Contest.objects.filter(contest_filter).distinct()
                queryset = queryset.filter(submission_filter | Q(contest_object__in=contest_queryset))

        if self.selected_languages:
            languages = Language.objects.filter(key__in=self.selected_languages)
            queryset = queryset.filter(language__in=languages)
        if self.selected_statuses and len(self.selected_statuses) > 0:
            queryset = queryset.filter(result__in=self.selected_statuses)

        return queryset

    def get_queryset(self):
        queryset = self._get_queryset()
        if not self.in_contest:
            filter_submissions_by_visible_problems(queryset, self.request.user)

        return queryset

    def get_my_submissions_page(self):
        return None

    def get_all_submissions_page(self):
        return reverse("all_submissions")

    def get_searchable_status_codes(self):
        hidden_codes = ["SC"]
        if not self.request.user.is_superuser and not self.request.user.is_staff:
            hidden_codes += ["IE"]
        return [(key, value) for key, value in Submission.RESULT if key not in hidden_codes]

    def get_context_data(self, **kwargs):
        context = super(SubmissionsListBase, self).get_context_data(**kwargs)
        authenticated = self.request.user.is_authenticated
        context["dynamic_update"] = False
        context["dynamic_contest_id"] = self.in_contest and self.contest.id
        context["show_problem"] = self.show_problem
        context["completed_problem_ids"] = user_completed_ids(self.request.profile) if authenticated else []
        context["editable_problem_ids"] = user_editable_ids(self.request.profile) if authenticated else []
        context["tester_problem_ids"] = user_tester_ids(self.request.profile) if authenticated else []

        context["all_languages"] = Language.objects.all().values_list("key", "name")
        context["selected_languages"] = self.selected_languages

        context["all_statuses"] = self.get_searchable_status_codes()
        context["selected_statuses"] = self.selected_statuses

        context["results_json"] = mark_safe(json.dumps(self.get_result_data()))
        context["results_colors_json"] = mark_safe(json.dumps(settings.DMOJ_STATS_SUBMISSION_RESULT_COLORS))

        context["page_suffix"] = suffix = ("?" + self.request.GET.urlencode()) if self.request.GET else ""
        context["first_page_href"] = (self.first_page_href or ".") + suffix
        context["my_submissions_link"] = self.get_my_submissions_page()
        context["all_submissions_link"] = self.get_all_submissions_page()
        context["tab"] = self.tab
        return context

    def get(self, request, *args, **kwargs):
        check = self.access_check(request)
        if check is not None:
            return check

        self.selected_languages = set(request.GET.getlist("language_code"))
        self.selected_statuses = set(request.GET.getlist("status"))

        if "results" in request.GET:
            return JsonResponse(self.get_result_data())

        return super(SubmissionsListBase, self).get(request, *args, **kwargs)
