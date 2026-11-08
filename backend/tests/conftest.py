import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="vo-test-"))
# Must be set before any app import. Tests never need a real key or network.
os.environ.update({
    "LLM_MODE": "mock", "DATABASE_URL": os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp / 'test.db'}"), "STORAGE_DIR": str(_tmp / "storage"),
    "RUN_WORKER": "false", "DEMO_STAGE_DELAY_MS": "0", "ENV": "dev", "RESEND_API_KEY": "", "OPENAI_API_KEY": "",
    "FERNET_KEY": "", "HMAC_KEY": "",
    "DEMO_ADMIN_EMAIL": "maker@test.example", "DEMO_ADMIN_PASSWORD": "maker-pass-123",
    "DEMO_CHECKER_EMAIL": "checker@test.example", "DEMO_CHECKER_PASSWORD": "checker-pass-123",
    "DEMO_VIEWER_EMAIL": "viewer@test.example", "DEMO_VIEWER_PASSWORD": "viewer-pass-123",
})

import asyncio  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import seed  # noqa: E402
from app.main import app  # noqa: E402
from app.ratelimit import limiter  # noqa: E402
from app.worker import drain  # noqa: E402

PASSWORDS = {"maker@test.example": "maker-pass-123", "checker@test.example": "checker-pass-123",
             "viewer@test.example": "viewer-pass-123"}


@pytest.fixture(scope="session", autouse=True)
def seeded_db():
    seed.reset()
    seed.upgrade()
    with seed.SessionLocal() as db:
        seed.seed_users(db)
    asyncio.run(seed.seed_history())
    limiter.enabled = False
    yield


def run_queue():
    asyncio.run(drain())


class Api:
    """A logged-in browser: keeps the session cookie and sends the CSRF header."""

    def __init__(self, email: str | None = None):
        self.client = TestClient(app)
        self.csrf = ""
        if email:
            r = self.client.post("/api/auth/login", json={"email": email, "password": PASSWORDS[email]})
            assert r.status_code == 200, r.text
            self.csrf = r.json()["csrf_token"]

    def get(self, url, **kw):
        return self.client.get(url, **kw)

    def post(self, url, **kw):
        headers = {"X-CSRF-Token": self.csrf, **kw.pop("headers", {})}
        return self.client.post(url, headers=headers, **kw)


@pytest.fixture
def admin():
    return Api("maker@test.example")


@pytest.fixture
def checker():
    return Api("checker@test.example")


@pytest.fixture
def viewer():
    return Api("viewer@test.example")
