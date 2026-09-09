import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routes import (
    auth,
    inspection_forms,
    inspections,
    job_types,
    messages,
    notifications,
    org,
    projects,
    segment_work,
    structures,
    sync,
    tasks,
    trails,
    work_logs,
)
from app.web import console

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)

app = FastAPI(
    title="Trailkeeper",
    description="Self-hosted trail-maintenance collaboration - API",
    version="0.1.0",
)

if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router)
app.include_router(org.router)
app.include_router(projects.router)
app.include_router(trails.router)
app.include_router(tasks.router)
app.include_router(work_logs.router)
app.include_router(messages.router)
app.include_router(notifications.router)
app.include_router(job_types.router)
app.include_router(segment_work.router)
app.include_router(structures.router)
app.include_router(inspection_forms.router)
app.include_router(inspections.router)
app.include_router(sync.router)
app.include_router(console.router)


@app.exception_handler(console.NeedsLogin)
def _needs_login_redirect(request: Request, exc: console.NeedsLogin) -> RedirectResponse:
    return RedirectResponse("/login", status_code=303)


# The React map console (console/ built by Vite → here). It's a deploy
# artifact, not committed; absent in a fresh checkout until `npm run build`.
_console_spa = Path(__file__).parent / "web" / "static" / "console"
if (_console_spa / "index.html").is_file():
    app.mount(
        "/console", StaticFiles(directory=_console_spa, html=True), name="console-spa"
    )


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}


@app.get("/version", tags=["meta"])
def version() -> dict:
    return {"name": "Trailkeeper", "version": app.version}
