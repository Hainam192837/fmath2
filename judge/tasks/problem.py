import logging

from celery import shared_task
from django.utils.translation import gettext as _

from judge.models import Problem
from judge.utils.celery import Progress

__all__ = ("update_problem_stats",)

logger = logging.getLogger("judge.celery")


@shared_task(bind=True)
def update_problem_stats(self, problem_id=None):
    if problem_id is None:
        problems = Problem.objects.all().defer("description")
        total = problems.count()
        updated_count = 0
        with Progress(self, total, stage=_("Updating problem stats")) as p:
            for problem in problems.iterator():
                problem.update_stats()
                updated_count += 1
                logger.info("Updated problem stats for problem_id=%s (%s/%s)", problem.id, updated_count, total)

                if updated_count % 10 == 0:
                    p.done = updated_count

        return updated_count

        try:
            problem = Problem.objects.get(id=problem_id)
        except Problem.DoesNotExist:
            return 0

        with Progress(self, 1, stage=_("Updating problem stats")) as p:
            problem.update_stats()
            logger.info("Updated problem stats for problem_id=%s", problem.id)
            p.done = 1
            problem.refresh_from_db(fields=["user_count", "ac_rate", "threshold_user_count"])

        return 1
