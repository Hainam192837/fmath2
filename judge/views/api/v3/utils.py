from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from judge.models import MiscConfig, NavigationBar
from judge.views.api.v3.permissions import get_request_user


def get_login_return_path(request):
    path = request.get_full_path()
    return "" if path.startswith("/accounts/") else path


def get_nav_tabs(request):
    problem_link = reverse("problem_list")
    user = get_request_user(request)
    if user and user.is_authenticated and user.profile.current_contest:
        problem_link = reverse("contest_problem_list", args=[user.profile.current_contest.contest.key])

    return [
        {"key": "problem", "href": problem_link, "label": "Problems"},
        {"key": "submission", "href": reverse("all_submissions"), "label": "Submissions"},
        {"key": "user", "href": reverse("user_list"), "label": "Users"},
        {"key": "organization", "href": reverse("organization_list"), "label": "Organizations"},
        {"key": "contest", "href": reverse("contest_list"), "label": "Contests"},
        {"key": "about", "href": "/about", "label": "About"},
    ]


def build_nav_tree(request):
    user = get_request_user(request)

    def walk(node):
        if node.is_admin and not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return None
        children = []
        for child in node.get_children():
            serialized = walk(child)
            if serialized is not None:
                children.append(serialized)
        return {
            "key": node.key,
            "label": node.label,
            "path": node.path,
            "is_admin": node.is_admin,
            "children": children,
        }

    roots = NavigationBar.objects.root_nodes().prefetch_related("children")
    tree = []
    for root in roots:
        serialized = walk(root)
        if serialized is not None:
            tree.append(serialized)
    return tree


def get_misc_config_value(site_domain, language, key):
    cache_keys = [key]
    if language:
        cache_keys.insert(0, f"{key}.{language}")
    if site_domain:
        prefixed = [f"{site_domain}:{item}" for item in cache_keys]
        cache_keys = prefixed + cache_keys

    values = dict(MiscConfig.objects.filter(key__in=cache_keys).values_list("key", "value"))
    for cache_key in cache_keys:
        if cache_key in values:
            return values[cache_key]
    return ""


def get_site_config(request):
    site = getattr(request, "site", None)
    domain = getattr(site, "domain", "")
    language = getattr(request, "LANGUAGE_CODE", "")
    return {
        "name": settings.SITE_NAME,
        "long_name": settings.SITE_LONG_NAME,
        "admin_email": settings.SITE_ADMIN_EMAIL,
        "domain": domain,
        "language": language,
        "login_return_path": get_login_return_path(request),
        "meta_keywords": get_misc_config_value(domain, language, "meta_keywords"),
        "meta_description": get_misc_config_value(domain, language, "meta_description"),
        "has_webauthn": bool(settings.WEBAUTHN_RP_ID),
        "now": timezone.now().isoformat(),
    }
