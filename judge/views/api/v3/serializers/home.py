from django.db.models import Max
from django.urls import reverse
from django.utils import timezone

from judge.models import BlogPost, Comment, Contest, Judge, Problem, Profile, Submission
from judge.views.api.v3.serializers.contests import serialize_contest_list_item
from judge.views.api.v3.serializers.problems import serialize_problem_list_item


def serialize_comment_summary(comment):
    return {
        "id": comment.id,
        "author": comment.author.user.username,
        "page": comment.page,
        "page_title": comment.page_title,
        "link": comment.link,
        "time": comment.time.isoformat(),
        "score": comment.score,
    }


def get_home_payload(user):
    now = timezone.now()
    visible_contests = Contest.get_visible_contests(user).filter(is_visible=True).order_by("start_time")

    posts = (
        BlogPost.objects.filter(visible=True, publish_on__lte=now)
        .order_by("-sticky", "-publish_on")
        .prefetch_related("authors__user")[:5]
    )
    problems = Problem.get_public_problems().order_by("-date", "code")[:8]
    comments = Comment.most_recent(user, 8)

    current_contests = visible_contests.filter(start_time__lte=now, end_time__gt=now)[:8]
    future_contests = visible_contests.filter(start_time__gt=now)[:8]

    profile = user.profile if user.is_authenticated else None
    own_open_tickets = []
    if profile is not None:
        own_open_tickets = list(profile.ticket_set.filter(is_open=True).order_by("-id")[:10].values("id", "title"))

    return {
        "posts": [
            {
                "id": post.id,
                "slug": post.slug,
                "title": post.title,
                "summary": post.summary,
                "publish_on": post.publish_on.isoformat(),
                "authors": list(post.authors.values_list("user__username", flat=True)),
                "url": reverse("blog_post", args=[post.id, post.slug]),
            }
            for post in posts
        ],
        "new_problems": [serialize_problem_list_item(problem) for problem in problems],
        "recent_comments": [serialize_comment_summary(comment) for comment in comments],
        "current_contests": [serialize_contest_list_item(contest, user) for contest in current_contests],
        "future_contests": [serialize_contest_list_item(contest, user) for contest in future_contests],
        "stats": {
            "users": Profile.objects.count(),
            "problems": Problem.get_public_problems().count(),
            "submissions": Submission.objects.aggregate(max_id=Max("id"))["max_id"] or 0,
            "judges_online": Judge.objects.filter(online=True).count(),
        },
        "own_open_tickets": own_open_tickets,
    }
