from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext as _

from judge.models import Contest, ContestParticipation
from judge.utils.opengraph import generate_opengraph
from judge.utils.views import generic_message


def _find_contest(request, key, private_check=True):
    try:
        contest = Contest.objects.get(key=key)
        if private_check and not contest.is_accessible_by(request.user):
            raise ObjectDoesNotExist()
    except ObjectDoesNotExist:
        return generic_message(
            request,
            _("No such contest"),
            _('Could not find a contest with the key "%s".') % key,
            status=404,
        ), False
    return contest, True


class ContestListMixin(object):
    def get_queryset(self):
        return Contest.get_visible_contests(self.request.user)


class PrivateContestError(Exception):
    def __init__(self, name, is_private, is_organization_private, orgs):
        self.name = name
        self.is_private = is_private
        self.is_organization_private = is_organization_private
        self.orgs = orgs


class ContestMixin(object):
    context_object_name = "contest"
    model = Contest
    slug_field = "key"
    slug_url_kwarg = "contest"

    @cached_property
    def is_editor(self):
        if not self.request.user.is_authenticated:
            return False
        return self.request.profile.id in self.object.editor_ids

    @cached_property
    def is_tester(self):
        if not self.request.user.is_authenticated:
            return False
        return self.request.profile.id in self.object.tester_ids

    @cached_property
    def can_edit(self):
        return self.object.is_editable_by(self.request.user)

    def get_context_data(self, **kwargs):
        context = super(ContestMixin, self).get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            try:
                context["live_participation"] = self.request.profile.contest_history.get(
                    contest=self.object,
                    virtual=ContestParticipation.LIVE,
                )
            except ContestParticipation.DoesNotExist:
                context["live_participation"] = None
                context["has_joined"] = False
            else:
                context["has_joined"] = True
        else:
            context["live_participation"] = None
            context["has_joined"] = False

        context["now"] = timezone.now()
        context["is_editor"] = self.is_editor
        context["is_tester"] = self.is_tester
        context["can_edit"] = self.can_edit

        metadata = (None, None)
        if not self.object.og_image or not self.object.summary:
            metadata = generate_opengraph(
                "generated-meta-contest:%d" % self.object.id,
                self.object.description,
                "contest",
            )
        context["meta_description"] = self.object.summary or metadata[0]
        context["og_image"] = self.object.og_image or metadata[1]
        context["has_moss_api_key"] = settings.MOSS_API_KEY is not None
        context["logo_override_image"] = self.object.logo_override_image
        if not context["logo_override_image"] and self.object.organizations.count() == 1:
            context["logo_override_image"] = self.object.organizations.first().logo_override_image

        return context

    def get_object(self, queryset=None):
        contest = super(ContestMixin, self).get_object(queryset)

        profile = self.request.profile
        if (
            profile is not None
            and ContestParticipation.objects.filter(
                id=profile.current_contest_id,
                contest_id=contest.id,
            ).exists()
        ):
            return contest
        if contest.is_accessible_by(self.request.user):
            return contest
        try:
            contest.access_check(self.request.user)
        except Contest.PrivateContest:
            raise PrivateContestError(
                contest.name,
                contest.is_private,
                contest.is_organization_private,
                contest.organizations.all(),
            )
        except Contest.Inaccessible:
            raise Http404()
        else:
            return contest

    def dispatch(self, request, *args, **kwargs):
        try:
            return super(ContestMixin, self).dispatch(request, *args, **kwargs)
        except Http404:
            key = kwargs.get(self.slug_url_kwarg, None)
            if key:
                return generic_message(
                    request,
                    _("No such contest"),
                    _('Could not find a contest with the key "%s".') % key,
                )
            return generic_message(
                request,
                _("No such contest"),
                _("Could not find such contest."),
            )
        except PrivateContestError as e:
            return render(
                request,
                "contest/private.html",
                {
                    "error": e,
                    "title": _('Access to contest "%s" denied') % e.name,
                },
                status=403,
            )
