"""All settings come from environment variables (or a .env file). Nothing secret is hardcoded."""
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    # Business
    buyer_name: str = "Acme Industries Pvt Ltd"
    max_attempts: int = 3
    reminder_days: int = 3
    token_ttl_days: int = 14
    confidence_threshold: float = 0.75  # below this an extracted value needs a human

    four_eyes_overrides: bool = True  # an override needs a second admin to approve it
    session_hours: int = 8
    session_idle_minutes: int = 30
    login_max_failures: int = 5
    login_lockout_minutes: int = 15

    # Infrastructure
    env: str = "dev"  # "dev" or "prod"
    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'app.db'}"
    storage_dir: Path = BACKEND_DIR / "storage"
    frontend_origin: str = "http://localhost:5173"
    public_app_url: str = "http://localhost:5173"  # used to build vendor portal links
    storage_backend: str = "local"  # "local" or "s3" (any S3-compatible store: AWS, R2, Supabase)
    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    s3_region: str = "auto"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_server_side_encryption: bool = True  # AWS SSE header; set false for Supabase / R2 (they encrypt at rest anyway)
    run_worker: bool = True  # run the queue worker inside the web process
    demo_stage_delay_ms: int = 300  # makes the live view watchable when the mock LLM answers instantly

    # Email. SMTP (e.g. Gmail + app password) or Resend; without either, messages only go to the outbox.
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    resend_api_key: str = ""
    brevo_api_key: str = ""
    email_redirect_to: str = ""  # demo: send every email to this one address instead of the real recipient
    email_from: str = "Acme Procurement <onboarding@example.com>"
    internal_alert_email: str = "procurement@example.com"

    # External verification providers: "none" or "sandbox"
    gst_verifier: str = "sandbox"
    bank_verifier: str = "sandbox"

    # Crypto (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    fernet_key: str = ""
    hmac_key: str = ""

    # LLM
    llm_mode: str = "openai"  # "openai" or "mock"
    openai_api_key: str = ""
    openai_model_vision: str = "gpt-5.4"
    openai_model_text: str = "gpt-5.4-mini"
    llm_timeout_seconds: float = 45.0

    # Changing this value resets the demo data once on the next start (then it's remembered).
    reset_demo_nonce: str = ""

    # Demo users (created by `python -m app.seed`; never hardcoded)
    demo_admin_email: str = ""
    demo_admin_password: str = ""
    demo_checker_email: str = ""
    demo_checker_password: str = ""
    demo_viewer_email: str = ""
    demo_viewer_password: str = ""

    @field_validator("database_url")
    @classmethod
    def use_psycopg3(cls, v: str) -> str:
        # Neon/Supabase hand out postgres:// URLs; point SQLAlchemy at the psycopg (v3) driver.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"


settings = Settings()
