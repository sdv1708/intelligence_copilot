"""The ASGI application.

Run it with:

    .venv/Scripts/python.exe -m uvicorn api.main:app --reload

In development the React app runs on its own Vite server and talks to this one
across origins, which is what the CORS block below is for. In production the
built bundle is served from here — same origin, no CORS, one port, one process.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from api import deps
from api.errors import handle_copilot_error
from api.routes import ROUTERS
from core.exceptions import CopilotError
from core.logging_config import configure_logging, get_logger

logger = get_logger(__name__)

# Vite's default port, and the one `web/vite.config.ts` pins.
DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the shared runtime before the first request, tear it down after.

    Loading the embedding model here rather than lazily means the process is
    slow to start and then uniformly fast, instead of fast to start and then
    stalling for whoever's request happens to be first.
    """
    configure_logging()
    deps.startup()
    try:
        yield
    finally:
        deps.shutdown()


app = FastAPI(
    title="Executive Intelligence Copilot",
    description="Ingests meeting materials and generates executive briefs.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(DEV_ORIGINS),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(CopilotError, handle_copilot_error)

for router in ROUTERS:
    app.include_router(router)


def mount_frontend() -> bool:
    """Serve the built React app, if it has been built.

    Returns whether anything was mounted, so a caller can tell the difference
    between "no frontend" and "frontend is fine". Absent in development — Vite
    serves it — so this is not an error, and the API is fully usable without it.
    """
    if not (FRONTEND_DIST / "index.html").is_file():
        logger.info(
            "No built frontend at %s; serving the API only. "
            "Run `npm run build` in web/ to bundle it.",
            FRONTEND_DIST,
        )
        return False

    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="assets",
    )

    @app.exception_handler(StarletteHTTPException)
    async def spa_fallback(request, exc):  # type: ignore[no-untyped-def]
        """Send unmatched GETs to `index.html` so client-side routes work.

        Scoped to 404s on non-`/api` paths: an unknown API route must stay a
        404 with a JSON body, not silently return the HTML shell, or every
        frontend typo would look like a successful request returning nonsense.
        """
        wants_page = (
            exc.status_code == 404
            and request.method == "GET"
            and not request.url.path.startswith("/api")
        )
        if wants_page:
            return FileResponse(FRONTEND_DIST / "index.html")

        return JSONResponse(
            status_code=exc.status_code, content={"detail": exc.detail}
        )

    logger.info("Serving the built frontend from %s", FRONTEND_DIST)
    return True


mount_frontend()
