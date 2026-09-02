from django.core.cache import cache
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache

from judge.models import Submission
from judge.utils.infinite_paginator import InfinitePaginationMixin
from judge.utils.problems import user_completed_ids, user_editable_ids, user_tester_ids

from .base import SubmissionsListBase, submission_related


@never_cache
def single_submission(request):
    request.no_profile_update = True
    if "id" not in request.GET or not request.GET["id"].isdigit():
        return HttpResponseBadRequest()
    try:
        show_problem = int(request.GET.get("show_problem", "1"))
    except ValueError:
        return HttpResponseBadRequest()

    authenticated = request.user.is_authenticated
    submission = get_object_or_404(submission_related(Submission.objects.all()), id=int(request.GET["id"]))
    if not submission.problem.is_accessible_by(request.user):
        raise Http404()

    return render(
        request,
        "submission/row.html",
        {
            "submission": submission,
            "completed_problem_ids": user_completed_ids(request.profile) if authenticated else [],
            "editable_problem_ids": user_editable_ids(request.profile) if authenticated else [],
            "tester_problem_ids": user_tester_ids(request.profile) if authenticated else [],
            "show_problem": show_problem,
            "problem_name": show_problem and submission.problem_name,
            "profile_id": request.profile.id if authenticated else 0,
        },
    )


@method_decorator(never_cache, name="dispatch")
class AllSubmissions(InfinitePaginationMixin, SubmissionsListBase):
    stats_update_interval = 3600

    @property
    def use_infinite_pagination(self):
        return not self.in_contest

    def get_my_submissions_page(self):
        if self.request.user.is_authenticated:
            return reverse("all_user_submissions", kwargs={"user": self.request.user.username})

    def get_context_data(self, **kwargs):
        context = super(AllSubmissions, self).get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context["dynamic_update"] = context["page_obj"].number == 1
        context["stats_update_interval"] = self.stats_update_interval
        return context

    def _get_result_data(self, queryset=None):
        if queryset is not None or self.in_contest or self.selected_languages or self.selected_statuses:
            return super(AllSubmissions, self)._get_result_data(queryset)

        key = "global_submission_result_data"
        result = cache.get(key)
        if result:
            return result
        result = super(AllSubmissions, self)._get_result_data(Submission.objects.all())
        cache.set(key, result, self.stats_update_interval)
        return result
