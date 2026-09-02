from calendar import SUNDAY, Calendar
from collections import defaultdict, namedtuple
from datetime import date, datetime, time, timedelta
from operator import attrgetter

from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.db.models import F, Max, Min, Q
from django.http import Http404, HttpResponse
from django.template.defaultfilters import date as date_filter
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.generic import TemplateView
from django.views.generic.detail import DetailView

from judge.models import Contest, ContestParticipation, ContestTag
from judge.models.profile import Organization
from judge.utils.views import DiggPaginatorMixin, QueryStringSortMixin, SafeListView, TitleMixin

from .base import ContestListMixin


class ContestList(QueryStringSortMixin, DiggPaginatorMixin, TitleMixin, ContestListMixin, SafeListView):
    model = Contest
    paginate_by = 20
    template_name = "contest/list.html"
    title = gettext_lazy("Contests")
    nav_tag = "contest"
    context_object_name = "past_contests"
    all_sorts = frozenset(("name", "user_count", "start_time"))
    default_desc = frozenset(("name", "user_count"))
    default_sort = "-start_time"

    @cached_property
    def _now(self):
        return timezone.now()

    def _get_queryset(self):
        query = (
            super()
            .get_queryset()
            .prefetch_related(
                "tags",
                "organizations",
                "authors",
                "curators",
                "testers",
            )
        )
        if self.selected_org:
            query = query.exclude(is_private=True).filter(organizations=self.selected_org)
        if not self.request.user.is_superuser:
            query = query.exclude(Q(is_exam_contest=True))
        return query

    def get_queryset(self):
        return self._get_queryset().order_by(self.order, "key").filter(end_time__lt=self._now)

    def get_context_data(self, **kwargs):
        context = super(ContestList, self).get_context_data(**kwargs)
        present, active, future = [], [], []
        current_participation = None
        for contest in self._get_queryset().exclude(end_time__lt=self._now):
            if (contest.pre_time and contest.pre_time > self._now) or (
                not contest.pre_time and contest.start_time > self._now
            ):
                future.append(contest)
            else:
                present.append(contest)

        if self.request.user.is_authenticated:
            current_participation_id = self.request.profile.current_contest_id
            if current_participation_id is not None:
                current_participation = (
                    ContestParticipation.objects.filter(pk=current_participation_id)
                    .select_related("contest")
                    .prefetch_related(
                        "contest__tags",
                        "contest__organizations",
                        "contest__authors",
                        "contest__curators",
                        "contest__testers",
                    )
                    .first()
                )
            for participation in (
                ContestParticipation.objects.filter(
                    virtual=0,
                    user=self.request.profile,
                    contest_id__in=present,
                )
                .select_related("contest")
                .prefetch_related(
                    "contest__tags",
                    "contest__organizations",
                    "contest__authors",
                    "contest__curators",
                    "contest__testers",
                )
                .annotate(key=F("contest__key"))
            ):
                if not participation.ended:
                    if current_participation is not None and participation.pk == current_participation.pk:
                        continue
                    active.append(participation)
                    present.remove(participation.contest)

        active.sort(key=attrgetter("end_time", "key"))
        present.sort(key=attrgetter("end_time", "key"))
        future.sort(key=attrgetter("start_time"))
        context["current_participation"] = current_participation
        context["active_participations"] = active
        context["current_contests"] = present
        context["future_contests"] = future
        if not self.request.user.is_staff:
            context["list_organizations"] = Organization.objects.filter(is_hidden=False)
        else:
            context["list_organizations"] = Organization.objects.all()
        if self.selected_org:
            context["organizations"] = int(self.selected_org)
        context["now"] = self._now
        context["first_page_href"] = "."
        context["page_suffix"] = "#past-contests"
        context.update(self.get_sort_context())
        context.update(self.get_sort_paginate_context())
        return context

    def setup_contest_list(self, request):
        self.selected_org = None
        self.all_sorts = set(self.all_sorts)
        if "organizations" in request.GET:
            try:
                self.selected_org = request.GET.get("organizations")
            except ValueError:
                pass

    def get(self, request, *args, **kwargs):
        self.setup_contest_list(request)
        return super().get(request, *args, **kwargs)


ContestDay = namedtuple("ContestDay", "date weekday is_pad is_today starts ends oneday")


class ContestCalendar(TitleMixin, ContestListMixin, TemplateView):
    firstweekday = SUNDAY
    weekday_classes = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
    template_name = "contest/calendar.html"

    def get(self, request, *args, **kwargs):
        try:
            self.year = int(kwargs["year"])
            self.month = int(kwargs["month"])
        except (KeyError, ValueError):
            raise ImproperlyConfigured(_("ContestCalendar requires integer year and month"))
        self.today = timezone.now().date()
        return self.render()

    def render(self):
        context = self.get_context_data()
        return self.render_to_response(context)

    def get_contest_data(self, start, end):
        end += timedelta(days=1)
        contests = self.get_queryset().filter(
            Q(start_time__gte=start, start_time__lt=end) | Q(end_time__gte=start, end_time__lt=end),
        )
        starts, ends, oneday = (defaultdict(list) for _ in range(3))
        for contest in contests:
            start_date = timezone.localtime(contest.start_time).date()
            end_date = timezone.localtime(contest.end_time - timedelta(seconds=1)).date()
            if start_date == end_date:
                oneday[start_date].append(contest)
            else:
                starts[start_date].append(contest)
                ends[end_date].append(contest)
        return starts, ends, oneday

    def get_table(self):
        calendar = Calendar(self.firstweekday).monthdatescalendar(self.year, self.month)
        starts, ends, oneday = self.get_contest_data(
            timezone.make_aware(datetime.combine(calendar[0][0], time.min)),
            timezone.make_aware(datetime.combine(calendar[-1][-1], time.min)),
        )
        return [
            [
                ContestDay(
                    date=day,
                    weekday=self.weekday_classes[weekday],
                    is_pad=day.month != self.month,
                    is_today=day == self.today,
                    starts=starts[day],
                    ends=ends[day],
                    oneday=oneday[day],
                )
                for weekday, day in enumerate(week)
            ]
            for week in calendar
        ]

    def get_context_data(self, **kwargs):
        context = super(ContestCalendar, self).get_context_data(**kwargs)

        try:
            month = date(self.year, self.month, 1)
        except ValueError:
            raise Http404()
        else:
            context["title"] = _("Contests in %(month)s") % {"month": date_filter(month, _("F Y"))}

        dates = Contest.objects.aggregate(min=Min("start_time"), max=Max("end_time"))
        min_month = (self.today.year, self.today.month)
        if dates["min"] is not None:
            min_month = dates["min"].year, dates["min"].month
        max_month = (self.today.year, self.today.month)
        if dates["max"] is not None:
            max_month = max((dates["max"].year, dates["max"].month), (self.today.year, self.today.month))

        month = (self.year, self.month)
        if month < min_month or month > max_month:
            raise Http404()

        context["now"] = timezone.now()
        context["calendar"] = self.get_table()
        context["curr_month"] = date(self.year, self.month, 1)

        if month > min_month:
            context["prev_month"] = date(
                self.year - (self.month == 1),
                12 if self.month == 1 else self.month - 1,
                1,
            )
        else:
            context["prev_month"] = None

        if month < max_month:
            context["next_month"] = date(
                self.year + (self.month == 12),
                1 if self.month == 12 else self.month + 1,
                1,
            )
        else:
            context["next_month"] = None
        return context


class CachedContestCalendar(ContestCalendar):
    def render(self):
        key = "contest_cal:%d:%d" % (self.year, self.month)
        cached = cache.get(key)
        if cached is not None:
            return HttpResponse(cached)
        response = super(CachedContestCalendar, self).render()
        response.render()
        cache.set(key, response.content)
        return response


class ContestTagDetailAjax(DetailView):
    model = ContestTag
    slug_field = slug_url_kwarg = "name"
    context_object_name = "tag"
    template_name = "contest/tag-ajax.html"


class ContestTagDetail(TitleMixin, ContestTagDetailAjax):
    template_name = "contest/tag.html"

    def get_title(self):
        return _("Contest tag: %s") % self.object.name
