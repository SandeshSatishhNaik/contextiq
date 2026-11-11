"""Central configuration. Values come from environment variables (.env supported)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
MODEL_DIR = ROOT / "app" / "ml" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def _load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


class Settings:
    # PayPal: "mock" (offline, PayPal-shaped responses), "sandbox" or "live"
    paypal_env: str = os.getenv("PAYPAL_ENV", "mock").lower()
    paypal_client_id: str = os.getenv("PAYPAL_CLIENT_ID", "")
    paypal_client_secret: str = os.getenv("PAYPAL_CLIENT_SECRET", "")
    paypal_webhook_id: str = os.getenv("PAYPAL_WEBHOOK_ID", "")
    currency: str = os.getenv("DEFAULT_CURRENCY", "USD")

    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'contextiq.db'}")
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")

    # Optional GenAI reasoning layer (Anthropic Messages API). Without a key,
    # ContextIQ uses deterministic templates for explanations.
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    llm_model_small: str = os.getenv("LLM_MODEL_SMALL", "claude-haiku-5-5")
    llm_model_large: str = os.getenv("LLM_MODEL_LARGE", "claude-sonnet-5-5")

    # Security gateway limits (policy as code)
    step_up_amount: float = float(os.getenv("STEP_UP_AMOUNT", "500"))
    new_payee_step_up_amount: float = float(os.getenv("NEW_PAYEE_STEP_UP_AMOUNT", "200"))
    qr_ttl_seconds: int = int(os.getenv("QR_TTL_SECONDS", "300"))
    approval_ttl_seconds: int = int(os.getenv("APPROVAL_TTL_SECONDS", "600"))
    server_secret: str = os.getenv("SERVER_SECRET", "dev-only-change-me")

    @property
    def paypal_base_url(self) -> str:
        return {
            "sandbox": "https://api-m.sandbox.paypal.com",
            "live": "https://api-m.paypal.com",
        }.get(self.paypal_env, "https://mock.paypal.local")


settings = Settings()
