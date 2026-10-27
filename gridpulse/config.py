"""Small, dependency-free configuration loader. Environment overrides .env."""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]


def load_env():
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or not key.strip().replace("_", "").isalnum():
            raise ValueError("Invalid .env line; use KEY=value without export.")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


load_env()


def backend():
    value = os.getenv("FORECAST_BACKEND", "local").lower()
    if value not in {"local", "quickml"}:
        raise ValueError("FORECAST_BACKEND must be local or quickml.")
    return value
