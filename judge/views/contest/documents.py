import logging
import os
import shutil
from operator import itemgetter

import pandas
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse
from django.template.loader import get_template
from django.utils import translation
from django.views.generic import View
from django.views.generic.detail import DetailView, SingleObjectMixin

from judge.models import Contest, ContestParticipation
from judge.models.contest import SampleContest
from judge.models.problem import ProblemTranslation
from judge.pdf_problems import HAS_PDF, DefaultPdfMaker
from judge.utils.views import add_file_response

from .base import ContestMixin


class ContestRawView(ContestMixin, DetailView):
    languages = set(map(itemgetter(0), settings.LANGUAGES))
    template_name = "contest/raw.html"

    def get_context_data(self, **kwargs):
        language = kwargs.get("language", self.request.LANGUAGE_CODE)

        if language not in self.languages:
            raise Http404()

        contest = self.get_object()
        problems = [contest_problem.problem for contest_problem in contest.contest_problems.order_by("order")]

        list_trans = ()
        for problem in problems:
            try:
                trans = problem.translations.get(language=language)
            except ProblemTranslation.DoesNotExist:
                trans = None
            list_trans += ((problem, trans),)

        context = super().get_context_data(**kwargs)
        context["problems"] = [
            (
                problem,
                problem.name if trans is None else trans.name,
                problem.description if trans is None else trans.description,
            )
            for problem, trans in list_trans
        ]
        context["url"] = self.request.build_absolute_uri()
        context["math_engine"] = "jax"
        return context


class ContestPdfView(LoginRequiredMixin, ContestMixin, SingleObjectMixin, View):
    logger = logging.getLogger("judge.problem.pdf")
    languages = set(map(itemgetter(0), settings.LANGUAGES))

    def get(self, request, *args, **kwargs):
        if not HAS_PDF:
            raise Http404()

        language = kwargs.get("language", self.request.LANGUAGE_CODE)
        if language not in self.languages:
            raise Http404()

        contest = self.get_object()
        problems = [contest_problem.problem for contest_problem in contest.contest_problems.order_by("order")]

        list_trans = ()
        for problem in problems:
            try:
                trans = problem.translations.get(language=language)
            except ProblemTranslation.DoesNotExist:
                trans = None
            list_trans += ((problem, trans),)

        cache = os.path.join(settings.PDF_CONTEST_CACHE, "%s.%s.pdf" % (contest.key, language))

        if not os.path.exists(cache):
            self.logger.info("Rendering: %s.%s.pdf", contest.key, language)
            with DefaultPdfMaker() as maker, translation.override(language):
                maker.html = (
                    get_template("contest/raw.html")
                    .render(
                        {
                            "contest": contest,
                            "problems": [
                                (
                                    problem,
                                    problem.name if trans is None else trans.name,
                                    problem.description if trans is None else trans.description,
                                )
                                for problem, trans in list_trans
                            ],
                            "url": request.build_absolute_uri(),
                            "math_engine": maker.math_engine,
                        }
                    )
                    .replace('"//', '"https://')
                    .replace("'//", "'https://")
                )
                maker.title = contest.name

                assets = ["full_style.css", "pygment-github.css"]
                icons = ["logo.svg"]
                if maker.math_engine == "jax":
                    assets.append("mathjax_config.js")
                for file in assets:
                    maker.load(file, settings.RESOURCES / file)
                for file in icons:
                    maker.load(file, settings.RESOURCES / "icons" / file)
                maker.make()
                if not maker.success:
                    self.logger.error("Failed to render PDF for %s", contest.key)
                    return HttpResponse(maker.log, status=500, content_type="text/plain")
                shutil.move(maker.pdffile, cache)

        response = HttpResponse()
        if hasattr(settings, "DMOJ_PDF_CONTEST_INTERNAL"):
            url_path = "%s/%s.%s.pdf" % (settings.DMOJ_PDF_CONTEST_INTERNAL, contest.key, language)
        else:
            url_path = None

        add_file_response(request, response, url_path, cache)
        response["Content-Type"] = "application/pdf"
        response["Content-Disposition"] = "inline; filename=%s.%s.pdf" % (contest.key, language)
        return response


class SampleContestPDF(SingleObjectMixin, View):
    slug_field = "pk"
    slug_url_kwarg = "pk"
    context_object_name = "contest"
    model = SampleContest
    logger = logging.getLogger("judge.problem.pdf")
    languages = set(map(itemgetter(0), settings.LANGUAGES))

    def get(self, request, *args, **kwargs):
        if not HAS_PDF:
            raise Http404()

        language = kwargs.get("language", self.request.LANGUAGE_CODE)
        if language not in self.languages:
            raise Http404()

        contest = self.get_object()
        problems = [problem.problem for problem in contest.contest_problems.all().order_by("order")]

        list_trans = ()
        for problem in problems:
            try:
                trans = problem.translations.get(language=language)
            except ProblemTranslation.DoesNotExist:
                trans = None
            list_trans += ((problem, trans),)

        cache = os.path.join(settings.PDF_CONTEST_CACHE, "%s.%s.pdf" % (contest.key, language))

        from judge.signals import unlink_if_exists

        if os.path.exists(cache):
            unlink_if_exists(cache)

        if not os.path.exists(cache):
            self.logger.info("Rendering: %s.%s.pdf", contest.key, language)
            with DefaultPdfMaker() as maker, translation.override(language):
                maker.html = (
                    get_template("contest/raw.html")
                    .render(
                        {
                            "contest": contest,
                            "problems": [
                                (
                                    problem,
                                    problem.name if trans is None else trans.name,
                                    problem.description if trans is None else trans.description,
                                )
                                for problem, trans in list_trans
                            ],
                            "url": request.build_absolute_uri(),
                            "math_engine": maker.math_engine,
                        }
                    )
                    .replace('"//', '"https://')
                    .replace("'//", "'https://")
                )
                maker.title = contest.name

                assets = ["style.css", "pygment-github.css"]
                if maker.math_engine == "jax":
                    assets.append("mathjax_config.js")
                for file in assets:
                    maker.load(file, os.path.join(settings.RESOURCES, file))
                maker.make()
                if not maker.success:
                    self.logger.error("Failed to render PDF for %s", contest.key)
                    return HttpResponse(maker.log, status=500, content_type="text/plain")
                shutil.move(maker.pdffile, cache)

        response = HttpResponse()
        if hasattr(settings, "DMOJ_PDF_CONTEST_INTERNAL"):
            url_path = "%s/%s.%s.pdf" % (settings.DMOJ_PDF_CONTEST_INTERNAL, contest.key, language)
        else:
            url_path = None

        add_file_response(request, response, url_path, cache)
        response["Content-Type"] = "application/pdf"
        response["Content-Disposition"] = "inline; filename=%s.%s.pdf" % (contest.key, language)
        return response


def exportExcel(request, contest):
    contest_object = Contest.objects.get(key=contest)
    response = HttpResponse()
    response["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    response["Content-Disposition"] = "attachment; filename=%s_rank.xlsx" % contest_object.key
    keys = ["Rank", "Fullname", "Username"]
    contest_problems = contest_object.contest_problems.all()
    for contest_problem in contest_problems:
        keys.append(contest_problem.temporary_name)
    keys.append("Total Point")

    data = {key: [] for key in keys}
    participations = ContestParticipation.objects.filter(
        contest=contest_object,
        virtual=ContestParticipation.LIVE,
    ).order_by("-score")

    index = 0
    for participation in participations:
        index += 1
        data["Rank"].append(index)
        data["Fullname"].append(participation.user.name if participation.user.name else participation.user.username)
        data["Username"].append(participation.user.username)
        format_data = participation.format_data or {}
        for contest_problem in contest_problems:
            result = format_data.get(str(contest_problem.id))
            if result:
                data[contest_problem.temporary_name].append(str(result["points"]))
            else:
                data[contest_problem.temporary_name].append("---")
        data["Total Point"].append(str(participation.score))

    df = pandas.DataFrame(data)
    with pandas.ExcelWriter(response, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Sheet1", index=False)

    return response
