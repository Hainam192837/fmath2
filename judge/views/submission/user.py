from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.translation import gettext as _

from judge.models import Profile

from .base import SubmissionsListBase


class UserMixin(object):
    def get(self, request, *args, **kwargs):
        if "user" not in kwargs:
            raise ImproperlyConfigured("Must pass a user")
        self.profile = get_object_or_404(Profile, user__username=kwargs["user"])
        self.username = kwargs["user"]
        return super(UserMixin, self).get(request, *args, **kwargs)


class ConditionalUserTabMixin(object):
    @cached_property
    def is_own(self):
        return self.request.user.is_authenticated and self.request.profile == self.profile

    def get_context_data(self, **kwargs):
        context = super(ConditionalUserTabMixin, self).get_context_data(**kwargs)
        if self.is_own:
            context["tab"] = "my_submissions_tab"
        else:
            context["tab"] = "user_submissions_tab"
            context["tab_username"] = self.profile.user.username
        return context


class AllUserSubmissions(ConditionalUserTabMixin, UserMixin, SubmissionsListBase):
    def get_queryset(self):
        return super(AllUserSubmissions, self).get_queryset().filter(user_id=self.profile.id)

    def get_title(self):
        if self.is_own:
            return _("All my submissions")
        return _("All submissions by %s") % self.username

    def get_content_title(self):
        if self.is_own:
            return format_html("All my submissions")
        return format_html(
            'All submissions by <a class="content_title" href="{1}">{0}</a>',
            self.username,
            reverse("user_page", args=[self.username]),
        )

    def get_my_submissions_page(self):
        if self.request.user.is_authenticated:
            return reverse("all_user_submissions", kwargs={"user": self.request.user.username})

    def get_context_data(self, **kwargs):
        context = super(AllUserSubmissions, self).get_context_data(**kwargs)
        context["dynamic_update"] = context["page_obj"].number == 1
        context["dynamic_user_id"] = self.profile.id
        return context
