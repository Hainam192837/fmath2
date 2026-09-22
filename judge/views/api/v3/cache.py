from django.http import HttpResponseNotModified, JsonResponse
from django.utils.http import quote_etag

from judge.models import Metadata


def _etag_matches(if_none_match: str, etag: str) -> bool:
    if not if_none_match:
        return False
    candidates = [candidate.strip() for candidate in if_none_match.split(",")]
    weak_etag = f"W/{etag}"
    return etag in candidates or weak_etag in candidates


def build_etag(key: str, version: int | None = None) -> str:
    if version is None:
        version = Metadata.get_version(key)
    return quote_etag(f"{key}:{version}")


def build_existing_etag(key: str, version: int | None = None) -> str | None:
    if version is None:
        version = Metadata.objects.filter(key=key).values_list("version", flat=True).first()
    if version is None:
        return None
    return quote_etag(f"{key}:{version}")


def cache_control_header(max_age: int = 60, private: bool = True) -> str:
    cache_scope = "private" if private else "public"
    return f"{cache_scope}, max-age={max_age}, must-revalidate"


def etag_not_modified_response(
    request,
    *,
    etag_key: str,
    version: int | None = None,
    max_age: int = 60,
    private: bool = True,
):
    etag = build_existing_etag(etag_key, version)
    if etag is None:
        return None
    if not _etag_matches(request.headers.get("If-None-Match", ""), etag):
        return None

    response = HttpResponseNotModified()
    response["ETag"] = etag
    response["Cache-Control"] = cache_control_header(max_age=max_age, private=private)
    return response


def etag_json_response(
    request,
    data,
    *,
    etag_key: str,
    version: int | None = None,
    max_age: int = 60,
    private: bool = True,
    safe: bool = True,
):
    etag = build_etag(etag_key, version)

    if _etag_matches(request.headers.get("If-None-Match", ""), etag):
        response = HttpResponseNotModified()
    else:
        response = JsonResponse(data, safe=safe)

    response["ETag"] = etag
    response["Cache-Control"] = cache_control_header(max_age=max_age, private=private)
    return response
