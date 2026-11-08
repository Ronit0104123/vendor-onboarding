import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import BACKEND_DIR, settings
from app.ratelimit import limiter
from app.routers import auth, demo, portal, runs, vendors
from app.security.crypto import check_keys_configured
from app.worker import worker_loop

logging.basicConfig(level=logging.INFO, format='{"t":"%(asctime)s","lvl":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
log = logging.getLogger("app")
FRONTEND_DIST = BACKEND_DIR.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    check_keys_configured()
    from app.migrate import upgrade
    upgrade()
    stop = asyncio.Event()
    task = asyncio.create_task(worker_loop(stop)) if settings.run_worker else None
    yield
    stop.set()
    if task:
        await task


app = FastAPI(title="Vendor Onboarding", lifespan=lifespan,
              docs_url=None if settings.is_prod else "/api/docs", redoc_url=None, openapi_url=None if settings.is_prod else "/api/openapi.json")
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=800)
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin], allow_credentials=True,
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-CSRF-Token"])

APP_CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
           "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
           "frame-ancestors 'none'")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    h = response.headers
    h.setdefault("Content-Security-Policy",
                 "default-src 'none'; frame-ancestors 'none'" if request.url.path.startswith("/api") else APP_CSP)
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "no-referrer"
    h["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=(), payment=()"
    h["Cross-Origin-Opener-Policy"] = "same-origin"
    if settings.is_prod:
        h["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    if request.url.path.startswith("/api"):
        h.setdefault("Cache-Control", "no-store")
    elif request.url.path.startswith(("/assets/", "/fonts/")):
        h["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@app.exception_handler(RateLimitExceeded)
async def rate_limited(request: Request, exc: RateLimitExceeded):
    return JSONResponse({"detail": "Too many requests. Please wait a minute and try again."}, status_code=429)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    fields = {".".join(str(p) for p in e["loc"][1:]): e["msg"] for e in exc.errors()}
    return JSONResponse({"detail": {"message": "Some fields are invalid.", "fields": fields}}, status_code=422)


@app.exception_handler(Exception)
async def unexpected(request: Request, exc: Exception):
    ref = uuid.uuid4().hex[:8]
    log.exception("unhandled error ref=%s path=%s", ref, request.url.path)
    return JSONResponse({"detail": f"Something went wrong on our side. Reference {ref}."}, status_code=500)


@app.get("/health")
@app.get("/api/health")
def health():
    return {"ok": True}


for r in (auth.router, vendors.router, runs.router, portal.router, demo.router):
    app.include_router(r)

# Optional: serve the built frontend from the same origin (single-service deploys).
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        candidate = (FRONTEND_DIST / path).resolve()
        if path and FRONTEND_DIST.resolve() in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html", headers={"Cache-Control": "no-cache"})
