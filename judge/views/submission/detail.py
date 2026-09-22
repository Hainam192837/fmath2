from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.http import Http404, HttpResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from judge.highlight_code import highlight_code
from judge.models import Log, Submission
from judge.utils.problem_data import get_problem_testcases_data

from .base import SubmissionDetailBase
from .testcases import combine_statuses, group_test_cases


class SubmissionSource(SubmissionDetailBase):
    template_name = "submission/source.html"

    def get_queryset(self):
        return super().get_queryset().select_related("source")

    def get_context_data(self, **kwargs):
        context = super(SubmissionSource, self).get_context_data(**kwargs)
        submission = self.object
        Log.objects.create(
            user=self.request.user.profile,
            title="View source code",
            message='View source code of submission\'s problem "%s"' % (submission.problem),
            object_id=submission.pk,
            object_title=submission,
        )
        context["raw_source"] = submission.source.source.rstrip("\n")
        context["highlighted_source"] = highlight_code(submission.source.source, submission.language.pygments)
        return context


@method_decorator(never_cache, name="dispatch")
class SubmissionStatus(SubmissionDetailBase):
    template_name = "submission/status.html"

    def get_context_data(self, **kwargs):
        context = super(SubmissionStatus, self).get_context_data(**kwargs)
        submission = self.object

        context["batches"], statuses, context["max_execution_time"] = group_test_cases(submission.test_cases.all())
        context["statuses"] = combine_statuses(statuses, submission)
        context["can_view_test"] = submission.problem.is_testcase_accessible_by(self.request.user)
        if context["can_view_test"]:
            context["cases_data"] = get_problem_testcases_data(submission.problem)
        else:
            context["cases_data"] = {}

        context["time_limit"] = submission.problem.time_limit
        try:
            lang_limit = submission.problem.language_limits.get(language=submission.language)
        except ObjectDoesNotExist:
            pass
        else:
            context["time_limit"] = lang_limit.time_limit
        return context


@method_decorator(never_cache, name="dispatch")
class SubmissionTestCaseQuery(SubmissionStatus):
    template_name = "submission/status-testcases.html"

    def get(self, request, *args, **kwargs):
        if "id" not in request.GET or not request.GET["id"].isdigit():
            return HttpResponseBadRequest()
        self.kwargs[self.pk_url_kwarg] = kwargs[self.pk_url_kwarg] = int(request.GET["id"])
        return super(SubmissionTestCaseQuery, self).get(request, *args, **kwargs)


class SubmissionSourceRaw(SubmissionSource):
    def get(self, request, *args, **kwargs):
        if not (self.request.user.is_authenticated and (self.request.user.is_superuser or self.request.user.is_staff)):
            return Http404()
        submission = self.get_object()
        return HttpResponse(submission.source.source, content_type="text/plain")


@require_POST
def abort_submission(request, submission):
    submission = get_object_or_404(Submission, id=int(submission))
    if not request.user.has_perm("judge.abort_any_submission") and (
        submission.rejudged_date is not None or request.profile != submission.user
    ):
        raise PermissionDenied()
    submission.abort()
    return HttpResponseRedirect(reverse("submission_status", args=(submission.id,)))
