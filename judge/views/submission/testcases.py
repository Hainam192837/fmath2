from collections import namedtuple
from itertools import groupby
from operator import attrgetter


def make_batch(batch, cases):
    result = {"id": batch, "cases": cases}
    if batch:
        result["points"] = min(map(attrgetter("points"), cases))
        result["total"] = max(map(attrgetter("total"), cases))
    return result


TestCase = namedtuple("TestCase", "id status batch num_combined")


def get_statuses(batch, cases):
    cases = [TestCase(id=case.id, status=case.status, batch=batch, num_combined=1) for case in cases]
    if batch:
        return [next((case for case in cases if case.status != "AC"), cases[0])]
    else:
        return cases


def combine_statuses(status_cases, submission):
    ret = []
    if not submission.is_graded and len(status_cases) > 0 and status_cases[-1].batch is not None:
        status_cases.pop()

    for key, group in groupby(status_cases, key=attrgetter("status")):
        group = list(group)
        if len(group) > 10:
            ret.append(TestCase(id=group[0].id, status=key, batch=None, num_combined=len(group)))
        else:
            ret.extend(group)
    return ret


def group_test_cases(cases):
    result = []
    status = []
    buf = []
    max_execution_time = 0.0
    last = None
    for case in cases:
        if case.time:
            max_execution_time = max(max_execution_time, case.time)
        if case.batch != last and buf:
            result.append(make_batch(last, buf))
            status.extend(get_statuses(last, buf))
            buf = []
        buf.append(case)
        last = case.batch
    if buf:
        result.append(make_batch(last, buf))
        status.extend(get_statuses(last, buf))
    return result, status, max_execution_time
