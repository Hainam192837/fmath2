from django.http import JsonResponse
from ninja import Router

from judge.views.api.v3.permissions import require_authenticated
from judge.views.api.v3.schemas.home import HomeSchema
from judge.views.api.v3.serializers.home import get_home_payload

router = Router(tags=["frontend"])


@router.get("/home", response=HomeSchema)
def home(request):
    user = require_authenticated(request)
    data = get_home_payload(user)
    response = JsonResponse(data)
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response
