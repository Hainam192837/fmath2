from django.conf import settings
from django.core.cache import cache
from ninja import Router

from judge.models import Achievement, SchoolYear

router = Router(tags=["achievement"])


def _get_achievement_cache_timeout() -> int:
    return int(getattr(settings, "API_ACHIEVEMENT_CACHE_TIMEOUT", 300))


@router.get("/years", auth=None)
def list_schoolyears(request):
    cache_key = "api_app_v3:achievement:years"
    data = cache.get(cache_key)
    if data is not None:
        return data

    schoolyears = SchoolYear.objects.all().order_by("-start")
    data = [
        {
            "id": schoolyear.id,
            "start": schoolyear.start.year,
            "finish": schoolyear.finish.year,
        }
        for schoolyear in schoolyears
    ]
    cache.set(cache_key, data, _get_achievement_cache_timeout())
    return data


@router.get("/achievements/featured", auth=None)
def list_featured_achievements(request):
    cache_key = "api_app_v3:achievement:featured"
    data = cache.get(cache_key)
    if data is not None:
        return data

    achievements = Achievement.objects.filter(featured=True) \
                                      .select_related("year").order_by("-year__start", "rank")
    data = [
        {
            "id": achievement.id,
            "name": achievement.name,
            "award": achievement.award,
            "contest": achievement.contest,
            "level": achievement.level,
            "year": str(achievement.year) if achievement.year else None,
            "rank": achievement.rank,
            "avatar": achievement.avatar.url if achievement.avatar else None,
        }
        for achievement in achievements
    ]
    cache.set(cache_key, data, _get_achievement_cache_timeout())
    return data


@router.get("/achievements", auth=None)
def list_achievements(request):
    cache_key = "api_app_v3:achievement:all"
    data = cache.get(cache_key)
    if data is not None:
        return data

    achievements = Achievement.objects.select_related("year").order_by("-year__start", "rank")
    data = [
        {
            "id": achievement.id,
            "name": achievement.name,
            "award": achievement.award,
            "contest": achievement.contest,
            "level": achievement.level,
            "year": str(achievement.year) if achievement.year else None,
            "rank": achievement.rank,
            "avatar": achievement.avatar.url if achievement.avatar else None,
        }
        for achievement in achievements
    ]
    cache.set(cache_key, data, _get_achievement_cache_timeout())
    return data
