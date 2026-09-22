from judge.views.submission import group_test_cases


def serialize_submission_list_item(submission):
    return {
        "id": submission.id,
        "problem": submission.problem.code,
        "user": submission.user.user.username,
        "date": submission.date.isoformat(),
        "language": submission.language.key if submission.language else None,
        "time": submission.time,
        "memory": submission.memory,
        "points": submission.points,
        "result": submission.result,
        "status": submission.status,
    }


def serialize_submission_detail(submission):
    cases = []
    grouped_cases, _, _ = group_test_cases(submission.test_cases.all())
    for batch in grouped_cases:
        batch_cases = [
            {
                "case_id": case.case,
                "status": case.status,
                "time": case.time,
                "memory": case.memory,
                "points": case.points,
                "total": case.total,
            }
            for case in batch["cases"]
        ]
        if batch["id"] is None:
            cases.extend(batch_cases)
        else:
            cases.append(
                {
                    "batch_id": batch["id"],
                    "cases": batch_cases,
                    "points": batch["points"],
                    "total": batch["total"],
                }
            )

    return {
        **serialize_submission_list_item(submission),
        "case_points": submission.case_points,
        "case_total": submission.case_total,
        "cases": cases,
    }


def serialize_contest_submission(submission, include_source: bool = False):
    source = None
    if include_source:
        source_obj = getattr(submission, "source", None)
        source = source_obj.source if source_obj is not None else ""

    return {
        "submission_id": submission.id,
        "language_key": submission.language.key if submission.language_id else None,
        "source": source,
        "status": submission.short_status,
        "result": submission.result,
        "status_display": str(submission.long_status),
        "points": submission.points,
        "case_points": submission.case_points,
        "case_total": submission.case_total,
        "time": submission.time,
        "memory": submission.memory,
        "is_graded": submission.is_graded,
        "is_pretested": submission.is_pretested,
        "version_update": submission.version_update,
        "submitted_at": submission.date.isoformat(),
    }


def serialize_contest_submission_source(contest_submission):
    submission = contest_submission.submission
    source_obj = getattr(submission, "source", None)

    return {
        "contest_submission_id": contest_submission.id,
        "submission_id": submission.id,
        "language_key": submission.language.key if submission.language_id else None,
        "source": source_obj.source if source_obj is not None else "",
        "version_update": submission.version_update,
        "submitted_at": submission.date.isoformat(),
    }
