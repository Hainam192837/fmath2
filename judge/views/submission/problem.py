from django.core.exceptions import ImproperlyConfigured
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext as _

from judge.models import Problem

from .base import SubmissionsListBase
from .user import ConditionalUserTabMixin, UserMixin


class ProblemSubmissionsBase(SubmissionsListBase):
    show_problem = False
    dynamic_update = True
    check_contest_in_access_check = True

    def get_queryset(self):
        if self.in_contest and not self.contest.contest_problems.filter(problem_id=self.problem.id).exists():
            raise Http404()
        return super(ProblemSubmissionsBase, self)._get_queryset().filter(problem_id=self.problem.id)

    def get_title(self):
        return _("All submissions for %s") % self.problem_name

    def get_content_title(self):
        return format_html(
            'All submissions for <a class="content_title" href="{1}">{0}</a>',
            self.problem_name,
            reverse("problem_detail", args=[self.problem.code]),
        )

    def access_check_contest(self, request):
        if self.in_contest and not self.contest.can_see_own_scoreboard(request.user):
            raise Http404()

    def access_check(self, request):
        if self.in_contest and request.user.is_authenticated and request.profile.id in self.contest.editor_ids:
            return

        if not self.problem.is_accessible_by(request.user):
            raise Http404()

        if self.check_contest_in_access_check:
            self.access_check_contest(request)

    def get(self, request, *args, **kwargs):
        if "problem" not in kwargs:
            raise ImproperlyConfigured(_("Must pass a problem"))
        self.problem = get_object_or_404(Problem, code=kwargs["problem"])
        self.problem_name = self.problem.translated_name(self.request.LANGUAGE_CODE)
        return super(ProblemSubmissionsBase, self).get(request, *args, **kwargs)

    def get_all_submissions_page(self):
        return reverse("chronological_submissions", kwargs={"problem": self.problem.code})

    def get_context_data(self, **kwargs):
        context = super(ProblemSubmissionsBase, self).get_context_data(**kwargs)
        if self.dynamic_update:
            context["dynamic_update"] = context["page_obj"].number == 1
            context["dynamic_problem_id"] = self.problem.id
        context["best_submissions_link"] = reverse("ranked_submissions", kwargs={"problem": self.problem.code})
        return context


class ProblemSubmissions(ProblemSubmissionsBase):
    def get_my_submissions_page(self):
        if self.request.user.is_authenticated:
            return reverse(
                "user_submissions", kwargs={"problem": self.problem.code, "user": self.request.user.username}
            )


class UserProblemSubmissions(ConditionalUserTabMixin, UserMixin, ProblemSubmissions):
    check_contest_in_access_check = False

    def access_check(self, request):
        super(UserProblemSubmissions, self).access_check(request)

        if not self.is_own:
            self.access_check_contest(request)

    def get_queryset(self):
        return super(UserProblemSubmissions, self).get_queryset().filter(user_id=self.profile.id)

    def get_title(self):
        if self.is_own:
            return _("My submissions for %(problem)s") % {"problem": self.problem_name}
        return _("%(user)s's submissions for %(problem)s") % {"user": self.username, "problem": self.problem_name}

    def get_content_title(self):
        if self.request.user.is_authenticated and self.request.profile == self.profile:
            return format_html(
                """My submissions for <a class="content_title" href="{3}">{2}</a>""",
                self.username,
                reverse("user_page", args=[self.username]),
                self.problem_name,
                reverse("problem_detail", args=[self.problem.code]),
            )
        return format_html(
            """<a class="content_title" href="{1}">
                                {0}</a>'s submissions for <a class="content_title" href="{3}">{2}</a>""",
            self.username,
            reverse("user_page", args=[self.username]),
            self.problem_name,
            reverse("problem_detail", args=[self.problem.code]),
        )

    def get_context_data(self, **kwargs):
        context = super(UserProblemSubmissions, self).get_context_data(**kwargs)
        context["dynamic_user_id"] = self.profile.id
        return context
