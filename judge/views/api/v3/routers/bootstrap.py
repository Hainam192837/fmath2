from django.http import JsonResponse
from ninja import Router

from judge.views.api.v3.permissions import get_profile_or_none
from judge.views.api.v3.schemas.bootstrap import BootstrapSchema
from judge.views.api.v3.serializers.users import serialize_profile_summary
from judge.views.api.v3.utils import build_nav_tree, get_nav_tabs, get_site_config

router = Router(tags=["frontend"])


@router.get("/bootstrap", response=BootstrapSchema)
def bootstrap(request):
    profile = get_profile_or_none(request)
    data = {
        "site": get_site_config(request),
        "nav_tabs": get_nav_tabs(request),
        "nav_tree": build_nav_tree(request),
        "user": serialize_profile_summary(profile) if profile else None,
    }
    response = JsonResponse(data)
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response
