from ninja import NinjaAPI

from judge.views.api.v3.auth import JWTAuth
from judge.views.api.v3.renderers import ORJSONRenderer
from judge.views.api.v3.routers import (
    achievement_router,
    auth_router,
    bootstrap_router,
    contests_router,
    home_router,
    organizations_router,
    problems_router,
    submissions_router,
    users_router,
)

api = NinjaAPI(renderer=ORJSONRenderer(), title="TMath Frontend API", version="3.0.0", auth=JWTAuth())
api.add_router("/", bootstrap_router)
api.add_router("/", home_router)
api.add_router("/", auth_router)
api.add_router("/", problems_router)
api.add_router("/", contests_router)
api.add_router("/", users_router)
api.add_router("/", organizations_router)
api.add_router("/", submissions_router)
api.add_router("/", achievement_router)
