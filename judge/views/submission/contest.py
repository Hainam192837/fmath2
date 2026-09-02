from django.core.exceptions import ImproperlyConfigured
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext as _

from judge.models import Contest

from .base import filter_submissions_by_visible_problems
from .problem import UserProblemSubmissions
from .user import AllUserSubmissions


class ForceContestMixin(object):
    @property
    def in_contest(self):
        return True

    @property
    def contest(self):
        return self._contest

    def access_check(self, request):
        super(ForceContestMixin, self).access_check(request)

        if not request.user.has_perm("judge.see_private_contest"):
            if not self.contest.is_visible:
                raise Http404()
            if self.contest.start_time is not None and self.contest.start_time > timezone.now():
                raise Http404()

    def get_problem_number(self, problem):
        return self.contest.contest_problems.select_related("problem").get(problem=problem).order

    def get(self, request, *args, **kwargs):
        if "contest" not in kwargs:
            raise ImproperlyConfigured(_("Must pass a contest"))
        self._contest = get_object_or_404(Contest, key=kwargs["contest"])
        return super(ForceContestMixin, self).get(request, *args, **kwargs)


class UserAllContestSubmissions(ForceContestMixin, AllUserSubmissions):
    def get_title(self):
        if self.is_own:
            return _("My submissions in %(contest)s") % {"contest": self.contest.name}
        return _("%(user)s's submissions in %(contest)s") % {
            "user": self.username,
            "contest": self.contest.name,
        }

    def access_check(self, request):
        super().access_check(request)
        if not self.contest.users.filter(user_id=self.profile.id).exists():
            raise Http404()
        if not self.is_own and not self.contest.can_see_full_scoreboard(self.request.user):
            raise Http404()

    def get_content_title(self):
        if self.is_own:
            return format_html(
                _('My submissions in <a class="content_title" href="{1}">{0}</a>'),
                self.contest.name,
                reverse("contest_view", args=[self.contest.key]),
            )
        return format_html(
            _('<a class="content_title" href="{1}">{0}</a>\'s submissions in <a href="{3}">{2}</a>'),
            self.username,
            reverse("user_page", args=[self.username]),
            self.contest.name,
            reverse("contest_view", args=[self.contest.key]),
        )

    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.user.is_authenticated or self.request.profile.id not in self.contest.editor_ids:
            filter_submissions_by_visible_problems(queryset, self.request.user)
        return queryset


class UserContestSubmissions(ForceContestMixin, UserProblemSubmissions):
    def get_title(self):
        if self.problem.is_accessible_by(self.request.user):
            return "%s's submissions for %s in %s" % (self.username, self.problem_name, self.contest.name)
        return "%s's submissions for problem %s in %s" % (
            self.username,
            self.get_problem_number(self.problem),
            self.contest.name,
        )

    def access_check(self, request):
        super(UserContestSubmissions, self).access_check(request)
        if not self.contest.users.filter(user_id=self.profile.id).exists():
            raise Http404()

    def get_content_title(self):
        if self.problem.is_accessible_by(self.request.user):
            return format_html(
                _('<a href="{1}">{0}</a>\'s submissions for <a href="{3}">{2}</a> in <a href="{5}">{4}</a>'),
                self.username,
                reverse("user_page", args=[self.username]),
                self.problem_name,
                reverse("problem_detail", args=[self.problem.code]),
                self.contest.name,
                reverse("contest_view", args=[self.contest.key]),
            )
        return format_html(
            _('<a href="{1}">{0}</a>\'s submissions for problem {2} in <a href="{4}">{3}</a>'),
            self.username,
            reverse("user_page", args=[self.username]),
            self.get_problem_number(self.problem),
            self.contest.name,
            reverse("contest_view", args=[self.contest.key]),
        )
