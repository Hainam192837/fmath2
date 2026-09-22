from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.db.models import Max
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, UpdateView
from django.views.generic.detail import BaseDetailView, DetailView
from reversion import revisions

from judge.comments import CommentedDetailView
from judge.forms import ContestCloneForm, ContestCreateForm, ContestProblemFrontendInlineFormSet
from judge.models import Contest, ContestParticipation, ContestProblem, ContestSubmission, Organization
from judge.utils.views import SingleObjectFormView, TitleMixin, generic_message

from .base import ContestMixin


class ContestEditorMessagesMixin:
    def add_editor_errors(self, form, problem_formset):
        errors = []

        for error in form.non_field_errors():
            errors.append(str(error))

        for field_name, field_errors in form.errors.items():
            if field_name == "__all__":
                continue
            label = form.fields[field_name].label
            for error in field_errors:
                errors.append(_("%(field)s: %(error)s") % {"field": label, "error": error})

        for error in problem_formset.non_form_errors():
            errors.append(_("Problem stack: %(error)s") % {"error": error})

        for index, problem_errors in enumerate(problem_formset.errors, start=1):
            for field_name, field_errors in problem_errors.items():
                if field_name == "__all__":
                    for error in field_errors:
                        errors.append(_("Problem %(index)s: %(error)s") % {"index": index, "error": error})
                    continue

                label = problem_formset.form.base_fields[field_name].label
                for error in field_errors:
                    errors.append(
                        _("Problem %(index)s, %(field)s: %(error)s")
                        % {"index": index, "field": label, "error": error}
                    )

        seen = set()
        for error in errors:
            if error in seen:
                continue
            seen.add(error)
            messages.error(self.request, error)


class ContestDetail(ContestMixin, TitleMixin, CommentedDetailView):
    template_name = "contest/contest.html"

    def get_comment_page(self):
        return "c:%s" % self.object.key

    def get_title(self):
        if self.object.is_joinable_by(self.request.user):
            return self.object.full_name
        return self.object.name

    def get_context_data(self, **kwargs):
        context = super(ContestDetail, self).get_context_data(**kwargs)
        context["contest_problems"] = (
            ContestProblem.objects.filter(contest=self.object).order_by("order").defer("problem__description")
        )
        return context


class ContestClone(ContestMixin, PermissionRequiredMixin, TitleMixin, SingleObjectFormView):
    title = _("Clone Contest")
    template_name = "contest/clone.html"
    form_class = ContestCloneForm
    permission_required = "judge.clone_contest"

    def form_valid(self, form):
        contest = self.object

        tags = contest.tags.all()
        organizations = contest.organizations.all()
        private_contestants = contest.private_contestants.all()
        view_contest_scoreboard = contest.view_contest_scoreboard.all()
        contest_problems = list(contest.contest_problems.all())
        old_key = contest.key

        contest.pk = None
        contest.is_visible = False
        contest.user_count = 0
        contest.locked_after = None
        contest.key = form.cleaned_data["key"]
        contest.is_rated = False
        contest.rate_all = False
        contest.rating_ceiling = 1000
        contest.fastio = False
        contest.is_limit_language = False
        contest.access_code = ""
        with revisions.create_revision(atomic=True):
            contest.save()
            contest.tags.set(tags)
            contest.organizations.set(organizations)
            contest.private_contestants.set(private_contestants)
            contest.view_contest_scoreboard.set(view_contest_scoreboard)
            contest.authors.add(self.request.profile)

            for problem in contest_problems:
                problem.contest = contest
                problem.pk = None
            ContestProblem.objects.bulk_create(contest_problems)

            revisions.set_user(self.request.user)
            revisions.set_comment(_("Cloned contest from %s") % old_key)

        return HttpResponseRedirect(reverse("contest_update", args=(contest.key,)))


class ContestCreate(ContestEditorMessagesMixin, LoginRequiredMixin, PermissionRequiredMixin, TitleMixin, CreateView):
    title = _("Create Contest")
    template_name = "contest/create.html"
    form_class = ContestCreateForm
    permission_required = "judge.add_contest"
    problem_formset_prefix = "problem_formset"

    def get_organization(self):
        organization_id = self.request.GET.get("organization")
        if not organization_id:
            return None
        try:
            organization_id = int(organization_id)
        except (TypeError, ValueError):
            return None

        organization = get_object_or_404(Organization, pk=organization_id)
        if not organization.admins.filter(id=self.request.profile.id).exists():
            return None
        return organization

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["profile"] = self.request.profile
        kwargs["organization"] = self.get_organization()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["selected_organization"] = self.get_organization()
        context["page_heading"] = _("Create contest")
        context["submit_label"] = _("Create contest")
        if "problem_formset" not in context:
            context["problem_formset"] = self.get_problem_formset()
        return context

    def get_problem_formset(self):
        if self.request.method == "POST":
            return ContestProblemFrontendInlineFormSet(
                self.request.POST,
                instance=self.object,
                prefix=self.problem_formset_prefix,
            )
        return ContestProblemFrontendInlineFormSet(instance=self.object, prefix=self.problem_formset_prefix)

    def form_valid(self, form):
        self.object = form.save(commit=False)
        problem_formset = ContestProblemFrontendInlineFormSet(
            self.request.POST,
            instance=self.object,
            prefix=self.problem_formset_prefix,
        )
        if not problem_formset.is_valid():
            self.add_editor_errors(form, problem_formset)
            return self.render_to_response(self.get_context_data(form=form, problem_formset=problem_formset))

        with revisions.create_revision(atomic=True):
            self.object.save()
            form.save_m2m()
            problem_formset.instance = self.object
            problem_formset.save()
            self.object.authors.add(self.request.profile)
            revisions.set_user(self.request.user)
            revisions.set_comment(_("Created from site"))
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse("contest_view", args=(self.object.key,))

    def form_invalid(self, form):
        problem_formset = self.get_problem_formset()
        self.add_editor_errors(form, problem_formset)
        return self.render_to_response(self.get_context_data(form=form, problem_formset=problem_formset))


class ContestUpdate(ContestEditorMessagesMixin, LoginRequiredMixin, TitleMixin, UpdateView):
    title = _("Update Contest")
    template_name = "contest/create.html"
    form_class = ContestCreateForm
    slug_field = "key"
    slug_url_kwarg = "contest"
    queryset = Contest.objects.all()
    problem_formset_prefix = "problem_formset"

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.object.is_editable_by(request.user):
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["profile"] = self.request.profile
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["selected_organization"] = None
        context["page_heading"] = _("Update contest")
        context["submit_label"] = _("Save contest")
        if "problem_formset" not in context:
            context["problem_formset"] = self.get_problem_formset()
        return context

    def get_problem_formset(self):
        if self.request.method == "POST":
            return ContestProblemFrontendInlineFormSet(
                self.request.POST,
                instance=self.object,
                prefix=self.problem_formset_prefix,
            )
        return ContestProblemFrontendInlineFormSet(instance=self.object, prefix=self.problem_formset_prefix)

    def form_valid(self, form):
        self.object = form.save(commit=False)
        problem_formset = ContestProblemFrontendInlineFormSet(
            self.request.POST,
            instance=self.object,
            prefix=self.problem_formset_prefix,
        )
        if not problem_formset.is_valid():
            self.add_editor_errors(form, problem_formset)
            return self.render_to_response(self.get_context_data(form=form, problem_formset=problem_formset))

        with revisions.create_revision(atomic=True):
            self.object.save()
            form.save_m2m()
            problem_formset.instance = self.object
            problem_formset.save()
            revisions.set_user(self.request.user)
            revisions.set_comment(_("Updated from site"))
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse("contest_view", args=(self.object.key,))

    def form_invalid(self, form):
        problem_formset = self.get_problem_formset()
        self.add_editor_errors(form, problem_formset)
        return self.render_to_response(self.get_context_data(form=form, problem_formset=problem_formset))


@login_required
@require_POST
def contest_problem_rejudge(request, contest, problem_id):
    contest_obj = get_object_or_404(Contest, key=contest)
    if not contest_obj.is_editable_by(request.user) or not request.user.has_perm("judge.rejudge_submission"):
        raise PermissionDenied()

    contest_problem = get_object_or_404(ContestProblem, contest=contest_obj, pk=problem_id)
    queryset = ContestSubmission.objects.filter(problem=contest_problem).select_related("submission")
    judged = queryset.count()
    for model in queryset:
        model.submission.judge(rejudge=True)

    messages.success(
        request,
        ngettext(
            "%d submission was successfully scheduled for rejudging.",
            "%d submissions were successfully scheduled for rejudging.",
            judged,
        )
        % judged,
    )
    return HttpResponseRedirect(reverse("contest_update", args=(contest_obj.key,)))


class ContestAccessDenied(Exception):
    pass


class ContestAccessCodeForm(forms.Form):
    access_code = forms.CharField(max_length=255)

    def __init__(self, *args, **kwargs):
        super(ContestAccessCodeForm, self).__init__(*args, **kwargs)
        self.fields["access_code"].widget.attrs.update({"autocomplete": "off"})


class ContestJoin(LoginRequiredMixin, ContestMixin, BaseDetailView):
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return self.ask_for_access_code()

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        try:
            return self.join_contest(request)
        except ContestAccessDenied:
            if request.POST.get("access_code"):
                return self.ask_for_access_code(ContestAccessCodeForm(request.POST))
            return HttpResponseRedirect(request.path)

    def join_contest(self, request, access_code=None):
        contest = self.object

        if not contest.can_join and not (self.is_editor or self.is_tester):
            return generic_message(
                request,
                _("Contest not ongoing"),
                _('"%s" is not currently ongoing.') % contest.name,
            )

        profile = request.profile
        if profile.current_contest is not None:
            return generic_message(
                request,
                _("Already in contest"),
                _('You are already in a contest: "%s".') % profile.current_contest.contest.name,
            )

        if not request.user.is_superuser and contest.banned_users.filter(id=profile.id).exists():
            return generic_message(
                request,
                _("Banned from joining"),
                _(
                    "You have been declared persona non grata for this contest. "
                    "You are permanently barred from joining this contest."
                ),
            )

        requires_access_code = not self.can_edit and contest.access_code and access_code != contest.access_code
        if contest.ended:
            if requires_access_code:
                raise ContestAccessDenied()

            while True:
                virtual_id = max(
                    (
                        ContestParticipation.objects.filter(contest=contest, user=profile).aggregate(
                            virtual_id=Max("virtual")
                        )["virtual_id"]
                        or 0
                    )
                    + 1,
                    1,
                )
                try:
                    participation = ContestParticipation.objects.create(
                        contest=contest,
                        user=profile,
                        virtual=virtual_id,
                        real_start=timezone.now(),
                    )
                except IntegrityError:
                    pass
                else:
                    break
        else:
            spectate = ContestParticipation.SPECTATE
            live = ContestParticipation.LIVE
            if not self.is_editor and requires_access_code:
                raise ContestAccessDenied()
            try:
                participation = ContestParticipation.objects.get(
                    contest=contest,
                    user=profile,
                    virtual=(spectate if self.is_editor or self.is_tester else live),
                )
            except ContestParticipation.DoesNotExist:
                if requires_access_code:
                    raise ContestAccessDenied()

                participation = ContestParticipation.objects.create(
                    contest=contest,
                    user=profile,
                    virtual=(spectate if self.is_editor or self.is_tester else live),
                    real_start=timezone.now(),
                )
            else:
                if participation.ended:
                    participation = ContestParticipation.objects.get_or_create(
                        contest=contest,
                        user=profile,
                        virtual=spectate,
                        defaults={"real_start": timezone.now()},
                    )[0]

        profile.current_contest = participation
        profile.save()
        contest._updating_stats_only = True
        contest.update_user_count()
        return HttpResponseRedirect(reverse("contest_problem_list", args=(contest.key,)))

    def ask_for_access_code(self, form=None):
        contest = self.object
        wrong_code = False
        if form:
            if form.is_valid():
                if form.cleaned_data["access_code"] == contest.access_code:
                    return self.join_contest(self.request, form.cleaned_data["access_code"])
                wrong_code = True
        else:
            form = ContestAccessCodeForm()
        return render(
            self.request,
            "contest/access_code.html",
            {
                "form": form,
                "wrong_code": wrong_code,
                "title": _('Enter access code for "%s"') % contest.name,
            },
        )


@login_required
@require_POST
def contestLeave(request, contest):
    profile = request.profile
    if profile.current_contest is None or profile.current_contest.contest.key != contest:
        return generic_message(
            request,
            _("No such contest"),
            _('You are not in contest "%s".') % contest,
            404,
        )

    contest = Contest.objects.get(key=contest)
    if not contest.forbidden_leave:
        profile.remove_contest()
    else:
        return generic_message(
            request,
            _("Contest is forbidden to leave"),
            _('You are not allowed to leave contest "%s" at this time.') % contest,
            403,
        )
    return HttpResponseRedirect(reverse("contest_view", args=(contest.key,)))


class ContestLeave(LoginRequiredMixin, ContestMixin, DetailView):
    def post(self, request, *args, **kwargs):
        contest = self.get_object()

        profile = request.profile
        if profile.current_contest is None or profile.current_contest.contest_id != contest.id:
            return generic_message(
                request,
                _("No such contest"),
                _('You are not in contest "%s".') % contest.key,
                404,
            )

        profile.remove_contest()
        return HttpResponseRedirect(reverse("contest_view", args=(contest.key,)))


class ContestManageView(ContestMixin, TitleMixin, DetailView):
    template_name = "contest/manage.html"
    tab = "manage"

    def get_title(self):
        return _("Contest Management")
