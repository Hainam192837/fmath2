import io
import os
import shutil
import tempfile
import zipfile
from collections import namedtuple
from datetime import timedelta
from functools import partial
from itertools import chain
from operator import attrgetter

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext as _
from django.views.generic import View
from django.views.generic.detail import DetailView, SingleObjectMixin
from PIL import Image, ImageDraw, ImageFont

from judge.models import ContestParticipation, Profile
from judge.utils.ranker import ranker
from judge.utils.timedelta import nice_repr
from judge.utils.views import TitleMixin

from .base import ContestMixin, _find_contest

HAS_SELENIUM = False
if settings.USE_SELENIUM:
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service

        HAS_SELENIUM = True
    except ImportError:
        HAS_SELENIUM = False

ContestRankingProfile = namedtuple(
    "ContestRankingProfile",
    "id user css_class username points cumtime tiebreaker organization participation "
    "participation_rating problem_cells result_cell",
)

BestSolutionData = namedtuple("BestSolutionData", "code points time state is_pretested")

RANKING_IMAGE_PAGE_SIZE = 40
RANKING_IMAGE_PANEL_COUNT = 2
RANKING_IMAGE_CANVAS_WIDTH = 1600
RANKING_IMAGE_CANVAS_HEIGHT = 2200
RANKING_IMAGE_LANDSCAPE_WIDTH = 2200
RANKING_IMAGE_LANDSCAPE_HEIGHT = 1600
RANKING_IMAGE_SAFE_AREA = 96

RANKING_IMAGE_BG = "#e2e8f0"
RANKING_IMAGE_CARD_BG = "#ffffff"
RANKING_IMAGE_MUTED = "#64748b"
RANKING_IMAGE_TEXT = "#0f172a"
RANKING_IMAGE_BORDER = "#cbd5e1"
RANKING_IMAGE_HEADER_BG = "#e2e8f0"
RANKING_IMAGE_ALT_ROW = "#f8fafc"
RANKING_IMAGE_DISQUALIFIED = "#fee2e2"
RANKING_IMAGE_BRAND = "#1d4ed8"
RANKING_IMAGE_LOGO_PATH = os.path.join(settings.RESOURCES, "icons", "logo.png")


def _ranking_font(size, bold=False):
    candidates = []
    if bold:
        candidates.extend(
            [
                "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
                "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            ]
        )
    else:
        candidates.extend(
            [
                "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
                "/usr/share/fonts/TTF/DejaVuSans.ttf",
            ]
        )

    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _text_width(draw, text, font):
    left, _, right, _ = draw.textbbox((0, 0), str(text), font=font)
    return right - left


def _truncate_text(draw, text, font, max_width):
    text = str(text or "")
    if not text:
        return ""
    if _text_width(draw, text, font) <= max_width:
        return text

    suffix = "..."
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        candidate = text[:mid].rstrip() + suffix
        if _text_width(draw, candidate, font) <= max_width:
            low = mid
        else:
            high = mid - 1
    return text[:low].rstrip() + suffix


def _wrap_text(draw, text, font, max_width, max_lines):
    words = str(text or "").split()
    if not words:
        return [""]

    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = current + " " + word
        if _text_width(draw, candidate, font) <= max_width:
            current = candidate
            continue
        lines.append(current)
        current = word
        if len(lines) == max_lines - 1:
            break

    if len(lines) < max_lines:
        lines.append(current)

    remaining_words = words[len(" ".join(lines).split()) :]
    if remaining_words:
        lines[-1] = _truncate_text(draw, lines[-1] + " " + " ".join(remaining_words), font, max_width)
    else:
        lines[-1] = _truncate_text(draw, lines[-1], font, max_width)
    return lines[:max_lines]


def _draw_text(draw, position, text, font, fill, anchor=None):
    kwargs = {"font": font, "fill": fill}
    if anchor:
        kwargs["anchor"] = anchor
    draw.text(position, str(text or ""), **kwargs)


def _ranking_image_rows_per_panel():
    return RANKING_IMAGE_PAGE_SIZE // RANKING_IMAGE_PANEL_COUNT


def _ranking_image_panel_count(row_count):
    return 1 if row_count <= 20 else RANKING_IMAGE_PANEL_COUNT


def _ranking_image_canvas_size(panel_count):
    if panel_count > 1:
        return RANKING_IMAGE_LANDSCAPE_WIDTH, RANKING_IMAGE_LANDSCAPE_HEIGHT
    return RANKING_IMAGE_CANVAS_WIDTH, RANKING_IMAGE_CANVAS_HEIGHT


def _format_ranking_cumtime(value):
    if value in (None, ""):
        return "---"
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return "---"
    return nice_repr(timedelta(seconds=max(seconds, 0)), "noday").replace(":", ".")


def _build_ranking_image_row(rank, user):
    return {
        "rank": rank,
        "user": user,
        "cumtime_formatted": _format_ranking_cumtime(user.cumtime),
    }


def make_contest_ranking_profile(contest, participation, contest_problems):
    def display_user_problem(contest_problem):
        try:
            return contest.format.display_user_problem(participation, contest_problem)
        except (KeyError, TypeError, ValueError):
            return {"has_data": False}

    user = participation.user
    return ContestRankingProfile(
        id=user.id,
        user=user.user,
        css_class=user.css_class,
        username=user.username,
        points=participation.score,
        cumtime=participation.cumtime,
        tiebreaker=participation.tiebreaker,
        organization=user.organization,
        participation_rating=participation.rating.rating if hasattr(participation, "rating") else None,
        problem_cells=[display_user_problem(contest_problem) for contest_problem in contest_problems],
        result_cell=contest.format.display_participation_result(participation),
        participation=participation,
    )


def base_contest_ranking_list(contest, problems, queryset):
    return [
        make_contest_ranking_profile(contest, participation, problems)
        for participation in queryset.select_related("user__user", "rating").defer(
            "user__about", "user__organizations__about"
        )
    ]


def contest_ranking_list(contest, problems):
    return base_contest_ranking_list(
        contest,
        problems,
        contest.users.filter(virtual=0)
        .prefetch_related("user__organizations")
        .order_by("is_disqualified", "-score", "cumtime", "tiebreaker"),
    )


def get_contest_ranking_list(
    request,
    contest,
    participation=None,
    ranking_list=contest_ranking_list,
    show_current_virtual=True,
    ranker=ranker,
):
    problems = list(
        contest.contest_problems.select_related("problem").defer("problem__description").order_by("order"),
    )

    users = ranker(ranking_list(contest, problems), key=attrgetter("points", "cumtime", "tiebreaker"))

    if show_current_virtual:
        if participation is None and request.user.is_authenticated:
            participation = request.profile.current_contest
            if participation is None or participation.contest_id != contest.id:
                participation = None
        if participation is not None and participation.virtual:
            users = chain([("-", make_contest_ranking_profile(contest, participation, problems))], users)
    return users, problems


def contest_ranking_ajax(request, contest, participation=None):
    contest, exists = _find_contest(request, contest)
    if not exists:
        return HttpResponseBadRequest("Invalid contest", content_type="text/plain")

    if not contest.can_see_full_scoreboard(request.user):
        raise Http404()

    users, problems = get_contest_ranking_list(request, contest, participation)
    return render(
        request,
        "contest/ranking-table.html",
        {
            "users": users,
            "problems": problems,
            "contest": contest,
            "has_rating": contest.ratings.exists(),
        },
    )


class ContestRankingBase(LoginRequiredMixin, ContestMixin, TitleMixin, DetailView):
    template_name = "contest/ranking.html"
    tab = None

    def get_title(self):
        raise NotImplementedError()

    def get_content_title(self):
        return self.object.name

    def get_ranking_list(self):
        raise NotImplementedError()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if not self.object.can_see_own_scoreboard(self.request.user):
            raise Http404()

        users, problems = self.get_ranking_list()
        context["users"] = users
        context["problems"] = problems
        context["tab"] = self.tab
        return context


class ContestRanking(ContestRankingBase):
    tab = "ranking"

    def get_title(self):
        return _("%s Rankings") % self.object.name

    def get_ranking_list(self):
        if not self.object.can_see_full_scoreboard(self.request.user):
            queryset = self.object.users.filter(user=self.request.profile, virtual=ContestParticipation.LIVE)
            return get_contest_ranking_list(
                self.request,
                self.object,
                ranking_list=partial(base_contest_ranking_list, queryset=queryset),
                ranker=lambda users, key: ((_("???"), user) for user in users),
            )

        return get_contest_ranking_list(self.request, self.object)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["has_rating"] = self.object.ratings.exists()
        return context


class ContestParticipationList(ContestRankingBase):
    tab = "participation"

    def get_title(self):
        if self.profile == self.request.profile:
            return _("Your participation in %(contest)s") % {"contest": self.object.name}
        return _("%(username)s's participation in %(contest)s") % {
            "username": self.profile.username,
            "contest": self.object.name,
        }

    def get_ranking_list(self):
        if not self.object.can_see_full_scoreboard(self.request.user) and self.profile != self.request.profile:
            raise Http404()

        queryset = self.object.users.filter(user=self.profile, virtual__gte=0).order_by("-virtual")
        live_link = format_html(
            '<a href="{2}#!{1}">{0}</a>',
            _("Live"),
            self.profile.username,
            reverse("contest_ranking", args=[self.object.key]),
        )

        return get_contest_ranking_list(
            self.request,
            self.object,
            show_current_virtual=False,
            ranking_list=partial(base_contest_ranking_list, queryset=queryset),
            ranker=lambda users, key: ((user.participation.virtual or live_link, user) for user in users),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["has_rating"] = False
        context["now"] = timezone.now()
        context["rank_header"] = _("Participation")
        return context

    def get(self, request, *args, **kwargs):
        if "user" in kwargs:
            self.profile = get_object_or_404(Profile, user__username=kwargs["user"])
        else:
            self.profile = self.request.profile
        return super().get(request, *args, **kwargs)


class ContestParticipationDisqualify(ContestMixin, SingleObjectMixin, View):
    def get_object(self, queryset=None):
        contest = super().get_object(queryset)
        if not contest.is_editable_by(self.request.user):
            raise Http404()
        return contest

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        try:
            participation = self.object.users.get(pk=request.POST.get("participation"))
        except ObjectDoesNotExist:
            pass
        else:
            participation.set_disqualified(not participation.is_disqualified)
        return HttpResponseRedirect(reverse("contest_ranking", args=(self.object.key,)))


class ContestRankingImageView(ContestRankingBase):
    tab = "ranking"

    def get_title(self):
        return _("%s Ranking Image") % self.object.name

    def get_ranking_list(self):
        if not self.object.can_see_full_scoreboard(self.request.user):
            raise Http404()
        return get_contest_ranking_list(self.request, self.object, show_current_virtual=False)

    def _get_page_number(self):
        try:
            page_number = int(self.request.GET.get("page", 1))
        except (TypeError, ValueError):
            raise Http404()
        if page_number < 1:
            raise Http404()
        return page_number

    def _get_requested_page_number(self):
        raw_page = self.request.GET.get("page")
        if raw_page in (None, ""):
            return None
        try:
            page_number = int(raw_page)
        except (TypeError, ValueError):
            raise Http404()
        if page_number < 1:
            raise Http404()
        return page_number

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        users = list(context["users"])
        page_number = self._get_requested_page_number() or 1
        page_size = RANKING_IMAGE_PAGE_SIZE
        total_pages = max((len(users) + page_size - 1) // page_size, 1)
        if page_number > total_pages:
            raise Http404()

        start = (page_number - 1) * page_size
        end = start + page_size
        page_users = users[start:end]

        context["ranking_image_all_users"] = users
        context["users"] = page_users
        context["ranking_image_panel_count"] = _ranking_image_panel_count(len(page_users))
        panels, rows_per_panel = self._build_panels(page_users)
        context["ranking_image_panels"] = panels
        context["ranking_image_rows_per_panel"] = rows_per_panel
        canvas_width, canvas_height = _ranking_image_canvas_size(context["ranking_image_panel_count"])
        context["ranking_image_page"] = page_number
        context["ranking_image_total_pages"] = total_pages
        context["ranking_image_page_size"] = page_size
        context["ranking_image_start_rank"] = start + 1 if page_users else 0
        context["ranking_image_end_rank"] = start + len(page_users)
        context["ranking_image_empty_rows"] = range(max(page_size - len(page_users), 0))
        context["ranking_image_canvas_width"] = canvas_width
        context["ranking_image_canvas_height"] = canvas_height
        context["ranking_image_safe_area"] = RANKING_IMAGE_SAFE_AREA
        context["has_rating"] = self.object.ratings.exists()
        return context

    def render_to_response(self, context, **response_kwargs):
        if self._get_requested_page_number() is None:
            return self._render_all_pages_response(context)

        image = self._render_image(context)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        filename = "%s_ranking_p%s.png" % (self.object.key, context["ranking_image_page"])
        response = HttpResponse(buffer.getvalue(), content_type="image/png")
        response["Content-Disposition"] = 'attachment; filename="%s"' % filename
        return response

    def _render_all_pages_response(self, context):
        total_pages = context["ranking_image_total_pages"]
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for page_number in range(1, total_pages + 1):
                page_context = self._build_page_context(context, page_number)
                image = self._render_image(page_context)
                image_buffer = io.BytesIO()
                image.save(image_buffer, format="PNG")
                archive.writestr("%s_ranking_p%s.png" % (self.object.key, page_number), image_buffer.getvalue())

        response = HttpResponse(archive_buffer.getvalue(), content_type="application/zip")
        response["Content-Disposition"] = 'attachment; filename="%s_ranking_images.zip"' % self.object.key
        return response

    def _build_page_context(self, context, page_number):
        users = context["ranking_image_all_users"]
        page_size = RANKING_IMAGE_PAGE_SIZE
        total_pages = max((len(users) + page_size - 1) // page_size, 1)
        start = (page_number - 1) * page_size
        end = start + page_size
        page_users = users[start:end]
        page_context = dict(context)
        page_context["users"] = page_users
        page_context["ranking_image_panel_count"] = _ranking_image_panel_count(len(page_users))
        panels, rows_per_panel = self._build_panels(page_users)
        page_context["ranking_image_panels"] = panels
        page_context["ranking_image_rows_per_panel"] = rows_per_panel
        canvas_width, canvas_height = _ranking_image_canvas_size(page_context["ranking_image_panel_count"])
        page_context["ranking_image_page"] = page_number
        page_context["ranking_image_total_pages"] = total_pages
        page_context["ranking_image_start_rank"] = start + 1 if page_users else 0
        page_context["ranking_image_end_rank"] = start + len(page_users)
        page_context["ranking_image_empty_rows"] = range(max(page_size - len(page_users), 0))
        page_context["ranking_image_canvas_width"] = canvas_width
        page_context["ranking_image_canvas_height"] = canvas_height
        return page_context

    def _build_panels(self, page_users):
        panel_count = _ranking_image_panel_count(len(page_users))
        rows_per_panel = max((len(page_users) + panel_count - 1) // panel_count, 1) if page_users else 1
        panels = []
        for panel_index in range(panel_count):
            start = panel_index * rows_per_panel
            end = start + rows_per_panel
            rows = [_build_ranking_image_row(rank, user) for rank, user in page_users[start:end]]
            panels.append(
                {
                    "rows": rows,
                    "empty_rows": range(max(rows_per_panel - len(rows), 0)),
                }
            )
        return panels, rows_per_panel

    def _render_image(self, context):
        if HAS_SELENIUM:
            try:
                return self._build_image_with_selenium(context)
            except Exception:
                pass
        return self._build_image(context)

    def _build_image_with_selenium(self, context):
        temp_dir = tempfile.mkdtemp(prefix="contest-ranking-image-")
        browser = None
        try:
            html_path = os.path.join(temp_dir, "ranking.html")
            html = render_to_string(
                "contest/ranking-image-export.html",
                context=context,
                request=self.request,
            )
            with open(html_path, "w", encoding="utf-8") as handle:
                handle.write(html)

            options = webdriver.ChromeOptions()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-gpu")
            options.add_argument("--hide-scrollbars")
            options.add_argument("--force-device-scale-factor=1")
            options.add_argument(
                "--window-size=%d,%d"
                % (context["ranking_image_canvas_width"], context["ranking_image_canvas_height"])
            )
            if settings.SELENIUM_CUSTOM_CHROME_PATH:
                options.binary_location = settings.SELENIUM_CUSTOM_CHROME_PATH

            service = Service(settings.SELENIUM_CHROMEDRIVER_PATH)
            browser = webdriver.Chrome(service=service, options=options)
            browser.get("file://%s" % html_path)
            png = browser.get_screenshot_as_png()
            return Image.open(io.BytesIO(png)).convert("RGB")
        finally:
            if browser is not None:
                browser.quit()
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _build_image(self, context):
        canvas_width = context["ranking_image_canvas_width"]
        canvas_height = context["ranking_image_canvas_height"]
        safe = context["ranking_image_safe_area"]
        image = Image.new("RGB", (canvas_width, canvas_height), RANKING_IMAGE_BG)
        draw = ImageDraw.Draw(image)

        title_font = _ranking_font(56, bold=True)
        badge_font = _ranking_font(24, bold=True)
        chip_font = _ranking_font(20, bold=True)
        header_font = _ranking_font(22, bold=True)
        name_font = _ranking_font(30, bold=True)
        meta_font = _ranking_font(18, bold=False)
        value_font = _ranking_font(30, bold=True)
        footer_font = _ranking_font(18, bold=False)

        draw.rounded_rectangle((32, 32, canvas_width - 32, canvas_height - 32), radius=40, fill=RANKING_IMAGE_CARD_BG)
        draw.rounded_rectangle(
            (safe, safe, canvas_width - safe, canvas_height - safe),
            radius=28,
            outline=RANKING_IMAGE_BORDER,
            width=3,
            fill="#f8fafc",
        )

        left = safe + 36
        top = safe + 34
        right = canvas_width - safe - 36

        draw.rounded_rectangle((left, top, left + 290, top + 52), radius=26, fill="#dbeafe")
        _draw_text(draw, (left + 22, top + 14), _("Contest Ranking"), badge_font, RANKING_IMAGE_BRAND)

        title_lines = _wrap_text(draw, self.object.name, title_font, right - left - 280, 2)
        title_y = top + 76
        for line in title_lines:
            _draw_text(draw, (left, title_y), line, title_font, RANKING_IMAGE_TEXT)
            title_y += 62

        chip_y = top + 210
        start_rank = context["ranking_image_start_rank"]
        end_rank = context["ranking_image_end_rank"]
        chips = [
            _("Ranks %(start)s-%(end)s") % {"start": start_rank, "end": end_rank} if start_rank else _("No ranks"),
            _("Page %(page)s/%(total)s")
            % {"page": context["ranking_image_page"], "total": context["ranking_image_total_pages"]},
            _("Max %(count)s rows with safe frame") % {"count": RANKING_IMAGE_PAGE_SIZE},
        ]
        chip_x = left
        for chip in chips:
            chip_width = _text_width(draw, chip, chip_font) + 36
            draw.rounded_rectangle(
                (chip_x, chip_y, chip_x + chip_width, chip_y + 42), radius=21, fill=RANKING_IMAGE_CARD_BG
            )
            draw.rounded_rectangle(
                (chip_x, chip_y, chip_x + chip_width, chip_y + 42), radius=21, outline=RANKING_IMAGE_BORDER, width=1
            )
            _draw_text(draw, (chip_x + 18, chip_y + 10), chip, chip_font, RANKING_IMAGE_MUTED)
            chip_x += chip_width + 12

        brand_box_width = 208
        brand_left = right - brand_box_width
        draw.rounded_rectangle((brand_left, top, right, top + 116), radius=24, fill="#eff6ff")
        _draw_text(draw, (brand_left + 18, top + 18), settings.SITE_NAME, chip_font, RANKING_IMAGE_TEXT)
        _draw_text(draw, (brand_left + 18, top + 56), self.object.key, meta_font, RANKING_IMAGE_MUTED)
        if os.path.exists(RANKING_IMAGE_LOGO_PATH):
            logo = Image.open(RANKING_IMAGE_LOGO_PATH).convert("RGBA").resize((68, 68))
            image.paste(logo, (right - 86, top + 24), logo)

        table_top = safe + 340
        table_left = left
        table_right = right
        row_height = 72
        head_height = 64
        footer_top = canvas_height - safe - 88

        panel_gap = 28
        panel_count = context["ranking_image_panel_count"]
        total_gap = panel_gap * (panel_count - 1)
        panel_width = (table_right - table_left - total_gap) // panel_count

        rows_per_panel = context["ranking_image_rows_per_panel"]

        def draw_panel(panel_left, panel_top, panel_right, panel_rows):
            draw.rounded_rectangle(
                (panel_left, panel_top, panel_right, footer_top - 18),
                radius=26,
                fill=RANKING_IMAGE_CARD_BG)
            draw.rounded_rectangle(
                (panel_left, panel_top, panel_right, panel_top + head_height),
                radius=26,
                fill=RANKING_IMAGE_HEADER_BG
            )
            draw.rectangle(
                (panel_left, panel_top + 26, panel_right, panel_top + head_height),
                fill=RANKING_IMAGE_HEADER_BG
            )

            rank_w = 112
            score_w = 104
            time_w = 170
            user_w = panel_right - panel_left - rank_w - score_w - time_w
            col_x = [
                panel_left,
                panel_left + rank_w,
                panel_left + rank_w + user_w,
                panel_left + rank_w + user_w + score_w,
                panel_right,
            ]

            _draw_text(
                draw,
                (panel_left + 18, panel_top + 20),
                _("Rank"),
                header_font,
                RANKING_IMAGE_MUTED)
            _draw_text(
                draw,
                (col_x[1] + 16, panel_top + 20),
                _("Contestant"),
                header_font,
                RANKING_IMAGE_MUTED)
            _draw_text(
                draw,
                (col_x[2] + score_w - 18, panel_top + 20),
                _("Score"),
                header_font,
                RANKING_IMAGE_MUTED,
                anchor="ra")
            _draw_text(
                draw,
                (col_x[3] + time_w - 18, panel_top + 20),
                _("Time"),
                header_font,
                RANKING_IMAGE_MUTED,
                anchor="ra")

            y = panel_top + head_height
            for index in range(rows_per_panel):
                row_box = (panel_left, y, panel_right, y + row_height)
                row_entry = panel_rows[index] if index < len(panel_rows) else None
                if row_entry is not None:
                    rank_info = row_entry["rank"]
                    user = row_entry["user"]
                    fill = RANKING_IMAGE_DISQUALIFIED if user.participation.is_disqualified else (
                        RANKING_IMAGE_ALT_ROW if index % 2 == 0 else RANKING_IMAGE_CARD_BG
                    )
                else:
                    rank_info = None
                    user = None
                    fill = "#f8fafc"

                draw.rectangle(row_box, fill=fill)
                draw.line((panel_left, y, panel_right, y), fill=RANKING_IMAGE_BORDER, width=1)

                if user is not None:
                    rank_label = _truncate_text(draw, rank_info, value_font, rank_w - 24)
                    _draw_text(
                        draw,
                        (panel_left + rank_w // 2, y + 23),
                        rank_label,
                        value_font,
                        RANKING_IMAGE_TEXT,
                        anchor="ma"
                    )

                    fullname = user.participation.user.name or user.username
                    username = "@%s" % user.username
                    cumtime = row_entry["cumtime_formatted"]

                    _draw_text(
                        draw,
                        (col_x[1] + 16, y + 12),
                        _truncate_text(draw, fullname, name_font, user_w - 24),
                        name_font,
                        RANKING_IMAGE_TEXT,
                    )
                    _draw_text(
                        draw,
                        (col_x[1] + 16, y + 43),
                        _truncate_text(draw, username, meta_font, user_w - 24),
                        meta_font,
                        RANKING_IMAGE_MUTED,
                    )
                    _draw_text(draw,
                               (col_x[2] + score_w - 18, y + 23),
                               user.points, value_font,
                               RANKING_IMAGE_TEXT,
                               anchor="ra")
                    _draw_text(draw,
                               (col_x[3] + time_w - 18, y + 23),
                               cumtime,
                               value_font,
                               "#334155",
                               anchor="ra")
                y += row_height

            draw.line((panel_left, y, panel_right, y), fill=RANKING_IMAGE_BORDER, width=1)

        current_left = table_left
        panels = context["ranking_image_panels"]
        for panel_index, panel in enumerate(panels):
            current_right = table_right if panel_index == panel_count - 1 else current_left + panel_width
            draw_panel(current_left, table_top, current_right, panel["rows"])
            current_left = current_right + panel_gap

        footer_text = _("Layout rule: one image = at most %(count)s ranking rows with fixed safe margins.") % {
            "count": RANKING_IMAGE_PAGE_SIZE
        }
        footer_meta = _("Page %(page)s/%(total)s")
        footer_meta = footer_meta % {
            "page": context["ranking_image_page"],
            "total": context["ranking_image_total_pages"],
        }
        _draw_text(draw, (left, footer_top + 18), footer_text, footer_font, RANKING_IMAGE_MUTED)
        _draw_text(draw, (right, footer_top + 18), footer_meta, footer_font, RANKING_IMAGE_MUTED, anchor="ra")
        return image
