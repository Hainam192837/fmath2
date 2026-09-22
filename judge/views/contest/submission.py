import json

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ImproperlyConfigured
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.generic import ListView

from judge.models import Contest, Language, Submission
from judge.models.contest import ContestProblem
from judge.utils.problems import get_result_data, user_completed_ids, user_editable_ids, user_tester_ids
from judge.utils.raw_sql import use_straight_join
from judge.utils.views import DiggPaginatorMixin, TitleMixin
from judge.views.submission import ConditionalUserTabMixin, UserMixin, submission_related


class ContestSubmissionsListBase(LoginRequiredMixin, DiggPaginatorMixin, TitleMixin, ListView):
    model = Submission
    paginate_by = 50
    show_problem = False
    title = gettext_lazy("All submissions")
    content_title = gettext_lazy("All submissions")
    template_name = "submission/list.html"
    context_object_name = "submissions"
    first_page_href = None

    def get_result_data(self):
        result = get_result_data(self.get_queryset().order_by())
        for category in result["categories"]:
            category["name"] = _(category["name"])
        return result

    @cached_property
    def contest(self):
        return get_object_or_404(Contest, key=self.kwargs["contest"])

    def get_base_queryset(self):
        queryset = Submission.objects.all()
        use_straight_join(queryset)
        queryset = submission_related(queryset.order_by("-id")).filter(contest_object=self.contest)
        if not self.contest.can_see_full_scoreboard(self.request.user):
            queryset = queryset.filter(user=self.request.profile)
        if self.selected_languages:
            queryset = queryset.filter(language__key__in=self.selected_languages)
        if self.selected_statuses:
            queryset = queryset.filter(result__in=self.selected_statuses)
        return queryset

    def get_my_submissions_page(self):
        return None

    def get_all_submissions_page(self):
        return reverse(
            "contest_problem_submissions",
            kwargs={"contest": self.contest.key, "problem": self.contest_problem.order},
        )

    def get_searchable_status_codes(self):
        hidden_codes = ["SC"]
        if not self.request.user.is_superuser and not self.request.user.is_staff:
            hidden_codes.append("IE")
        return [(key, value) for key, value in Submission.RESULT if key not in hidden_codes]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        authenticated = self.request.user.is_authenticated
        context["dynamic_update"] = context["page_obj"].number == 1
        context["dynamic_contest_id"] = self.contest.id
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
        return context

    def get(self, request, *args, **kwargs):
        self.selected_languages = set(request.GET.getlist("language_code"))
        self.selected_statuses = set(request.GET.getlist("status"))

        if "results" in request.GET:
            return JsonResponse(self.get_result_data())

        return super().get(request, *args, **kwargs)


class ContestProblemSubmissionsBase(ContestSubmissionsListBase):
    tab = "submissions"

    def get(self, request, *args, **kwargs):
        if "problem" not in kwargs:
            raise ImproperlyConfigured(_("Must pass a problem"))

        self.contest_problem = get_object_or_404(
            ContestProblem,
            contest__key=kwargs["contest"],
            order=kwargs["problem"],
        )
        self.problem = self.contest_problem.problem
        self.problem_name = self.contest_problem.temporary_name
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if (
            self.request.user.is_authenticated
            and self.request.profile.current_contest is not None
            and self.request.profile.current_contest.contest_id == self.contest.id
            and not self.contest.contest_problems.filter(problem_id=self.problem.id).exists()
        ):
            raise Http404()

        if (
            not self.request.user.is_authenticated or self.request.profile.id not in self.contest.editor_ids
        ) and not self.problem.is_accessible_by(self.request.user):
            raise Http404()

        if (
            self.request.user.is_authenticated
            and self.request.profile.current_contest is not None
            and self.request.profile.current_contest.contest_id == self.contest.id
            and not self.contest.can_see_own_scoreboard(self.request.user)
        ):
            raise Http404()

        return self.get_base_queryset().filter(problem_id=self.problem.id)

    def get_title(self):
        return _("All submissions for %s") % self.problem_name

    def get_content_title(self):
        return format_html(
            'All submissions for <a class="content_title" href="{1}">{0}</a>',
            self.problem_name,
            self.contest_problem.get_absolute_url(),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["dynamic_problem_id"] = self.problem.id
        context["tab"] = self.tab
        return context


class ContestProblemSubmissions(ContestProblemSubmissionsBase):
    def get_my_submissions_page(self):
        if self.request.user.is_authenticated:
            return reverse(
                "user_contest_problem_submissions",
                kwargs={
                    "contest": self.contest.key,
                    "problem": self.contest_problem.order,
                    "user": self.request.user.username,
                },
            )


class UserContestProblemSubmissions(ConditionalUserTabMixin, UserMixin, ContestProblemSubmissions):
    def get_queryset(self):
        queryset = super().get_queryset()
        if self.profile != self.request.profile and not self.contest.can_see_full_scoreboard(self.request.user):
            raise Http404()
        return queryset.filter(user_id=self.profile.id)

    def get_title(self):
        if self.is_own:
            return _("My submissions for %(problem)s") % {"problem": self.problem_name}
        return _("%(user)s's submissions for %(problem)s") % {
            "user": self.username,
            "problem": self.problem_name,
        }

    def get_content_title(self):
        if self.is_own:
            return format_html(
                'My submissions for <a class="content_title" href="{1}">{0}</a>',
                self.problem_name,
                self.contest_problem.get_absolute_url(),
            )
        return format_html(
            '<a class="content_title" href="{1}">{0}</a>\'s submissions for '
            '<a class="content_title" href="{3}">{2}</a>',
            self.username,
            reverse("user_page", args=[self.username]),
            self.problem_name,
            self.contest_problem.get_absolute_url(),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["dynamic_user_id"] = self.profile.id
        return context
