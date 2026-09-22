from .achievement import router as achievement_router
from .auth import router as auth_router
from .bootstrap import router as bootstrap_router
from .contests import router as contests_router
from .home import router as home_router
from .organizations import router as organizations_router
from .problems import router as problems_router
from .submissions import router as submissions_router
from .users import router as users_router

__all__ = [
    "achievement_router",
    "auth_router",
    "bootstrap_router",
    "contests_router",
    "home_router",
    "organizations_router",
    "problems_router",
    "submissions_router",
    "users_router",
]
