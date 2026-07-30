"""The routers, in the order `api.main` mounts them.

Order matters for one pair: `materials` declares `/api/materials/{material_id}`
and `meetings` declares `/api/meetings/{meeting_id}`. They do not collide, but
keeping the list explicit means a future route that *would* collide is visible
here rather than resolved by import order.
"""

from api.routes.briefs import router as briefs_router
from api.routes.materials import router as materials_router
from api.routes.meetings import router as meetings_router
from api.routes.qa import router as qa_router
from api.routes.status import router as status_router

ROUTERS = (
    status_router,
    meetings_router,
    materials_router,
    briefs_router,
    qa_router,
)

__all__ = ["ROUTERS"]
