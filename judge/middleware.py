import logging
from ipaddress import ip_address
from urllib.parse import quote as urlquote

from django.conf import settings
from django.contrib.sessions.models import Session
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.urls import Resolver404, resolve, reverse
from django_redis import get_redis_connection

logger = logging.getLogger("judge.request")


def _extract_ip(raw_ip: str) -> str:
    """Bỏ phần :port nếu có và xác thực IP hợp lệ (IPv4/IPv6)."""
    if not raw_ip:
        return ""

    candidate = raw_ip.strip()

    # 1) Trường hợp chuẩn [IPv6]:port
    if candidate.startswith("[") and "]" in candidate:
        candidate = candidate[1 : candidate.index("]")]

    # 2) Parse trực tiếp trước (hỗ trợ IPv4/IPv6 không kèm port)
    try:
        return str(ip_address(candidate))
    except ValueError:
        pass

    # 3) Fallback cho IPv4:port hoặc host:port
    if ":" in candidate and candidate.count(":") == 1:
        host, _, port = candidate.rpartition(":")
        if port.isdigit():
            candidate = host

    try:
        return str(ip_address(candidate))
    except ValueError:
        return ""


def _is_trusted_proxy(remote_ip: str) -> bool:
    """
    Kiểm tra IP proxy có nằm trong danh sách trusted không.
    Nếu chưa cấu hình TRUSTED_PROXY_IPS thì giữ hành vi cũ: coi như trusted.
    """
    trusted = getattr(settings, "TRUSTED_PROXY_IPS", None)
    if trusted is None:
        return True
    if not trusted:
        return False
    return remote_ip in set(trusted)


def get_client_ip(request) -> str:
    """
    Lấy IP thật của client khi có Cloudflare hoặc reverse proxy.
    Ưu tiên:
    1. CF-Connecting-IP  (Cloudflare)
    2. X-Forwarded-For    (proxy chuỗi IP)
    3. X-Real-IP          (nếu Nginx set)
    4. REMOTE_ADDR        (fallback)
    """
    remote = _extract_ip(request.META.get("REMOTE_ADDR", ""))
    trust_forwarded = _is_trusted_proxy(remote)

    cf_ip = request.META.get("HTTP_CF_CONNECTING_IP")
    if trust_forwarded and cf_ip:
        ip = _extract_ip(cf_ip.strip())
        if ip:
            return ip

    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if trust_forwarded and xff:
        first_ip = xff.split(",")[0].strip()
        ip = _extract_ip(first_ip)
        if ip:
            return ip

    real_ip = request.META.get("HTTP_X_REAL_IP")
    if trust_forwarded and real_ip:
        ip = _extract_ip(real_ip)
        if ip:
            return ip

    return remote


class BlockedIpMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ip = get_client_ip(request)
        if ip and (ip in settings.BLOCKED_IPS or ip.startswith("43.")):
            raise Http404()

        response = self.get_response(request)
        return response


class RateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        try:
            self.r = get_redis_connection("default")
        except NotImplementedError:
            self.r = None
            # logger.warning("RateLimitMiddleware disabled: default cache backend does not expose a Redis connection")

        self.window = int(getattr(settings, "RATE_LIMIT_WINDOW_SECONDS", 10))
        self.limit_anonymous = int(getattr(settings, "RATE_LIMIT_LIMIT_ANONYMOUS", 80))
        self.limit_authenticated = int(getattr(settings, "RATE_LIMIT_LIMIT_AUTHENTICATED", 240))
        self.prefix = getattr(settings, "RATE_LIMIT_PREFIX", "rl")
        self.exempt_prefixes = tuple(
            getattr(
                settings,
                "RATE_LIMIT_EXEMPT_PATH_PREFIXES",
                (
                    "/ws/",
                    "/channels/",
                ),
            )
        )
        self.exempt_substrings = tuple(
            getattr(
                settings,
                "RATE_LIMIT_EXEMPT_PATH_SUBSTRINGS",
                (
                    "/submission/exists/",
                    "/submission/source/",
                    "/version/",
                ),
            )
        )

    def __call__(self, request):
        resp = self._check_rate(request)
        if resp:
            return resp
        return self.get_response(request)

    def _check_rate(self, request):
        if self.r is None:
            return None

        path = request.path_info or ""
        if any(path.startswith(prefix) for prefix in self.exempt_prefixes):
            return None
        if any(token in path for token in self.exempt_substrings):
            return None

        scope, principal, limit = self._resolve_scope_and_limit(request)
        if not principal:
            return None

        key = f"{self.prefix}:{scope}:{principal}"

        pipe = self.r.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        count, ttl = pipe.execute()

        # Lần đầu -> set TTL
        if count == 1:
            self.r.expire(key, self.window)
            ttl = self.window

        if count > limit:
            return self._too_many(ttl)

        return None

    def _resolve_scope_and_limit(self, request):
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return "user", str(user.id), self.limit_authenticated

        ip = get_client_ip(request)
        return "ip", ip, self.limit_anonymous

    def _too_many(self, retry_after):
        retry_after = max(1, int(retry_after or 1))
        resp = JsonResponse(
            {
                "detail": "Bạn thao tác quá nhanh, vui lòng thử lại sau.",
                "retry_after_seconds": retry_after,
            },
            status=429,
        )
        resp["Retry-After"] = str(retry_after)
        return resp


class LogRequestsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = "AnonymousUser" if request.user.is_anonymous else request.user.username
        ip = get_client_ip(request)
        # Log the user access URL
        info = f"User {user} in IP:{ip} accessed {request.path} - {request.method}"
        logger.info(info)

        response = self.get_response(request)
        return response


# One session_key to one Person anytime
class OneSessionPerUser(object):
    def __init__(self, get_response) -> None:
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            current_session_key = request.user.logged_in_user.session_key

            if current_session_key and current_session_key != request.session.session_key:
                Session.objects.filter(session_key=current_session_key).delete()

            request.user.logged_in_user.session_key = request.session.session_key
            request.user.logged_in_user.save()

        return self.get_response(request)


class ShortCircuitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            callback, args, kwargs = resolve(
                request.path_info,
                getattr(request, "urlconf", None),
            )
        except Resolver404:
            callback, args, kwargs = None, None, None

        if getattr(callback, "short_circuit_middleware", False):
            return callback(request, *args, **kwargs)
        return self.get_response(request)


class DMOJLoginMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            request.profile = request.user.profile
            logout_path = reverse("auth_logout")
            # webauthn_path = reverse('webauthn_assert')
            change_password_path = reverse("password_change")
            change_password_done_path = reverse("password_change_done")
            # has_2fa = profile.is_totp_enabled or profile.is_webauthn_enabled
            # if (has_2fa and not request.session.get('2fa_passed', False) and
            #         request.path not in (login_2fa_path, logout_path, webauthn_path) and
            #         not request.path.startswith(settings.STATIC_URL)):
            #     return HttpResponseRedirect(login_2fa_path + '?next=' + urlquote(request.get_full_path()))
            if (
                request.session.get("password_pwned", False)
                and request.path not in (change_password_path, change_password_done_path, logout_path)
                and not request.path.startswith(settings.STATIC_URL)
            ):
                return HttpResponseRedirect(
                    change_password_path + "?next=" + urlquote(request.get_full_path()),
                )
        else:
            request.profile = None
        return self.get_response(request)


class DMOJImpersonationMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_impersonate:
            request.no_profile_update = True
            request.profile = request.user.profile
        return self.get_response(request)


class ContestMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        profile = request.profile
        if profile:
            profile.update_contest()
            request.participation = profile.current_contest
            request.in_contest = request.participation is not None
        else:
            request.in_contest = False
            request.participation = None
        return self.get_response(request)
