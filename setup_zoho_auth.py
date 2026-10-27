r"""Configure this GridPulse project's India-region QuickML endpoint privately.

Run from an interactive PowerShell terminal using the project's Python:
    .\.venv\Scripts\python.exe setup_zoho_auth.py

Create a Self Client in Zoho's India API console first. This script prompts
locally (hidden input), sends credentials only to accounts.zoho.in over HTTPS,
and saves the resulting access/refresh tokens in .env. It never prints secrets
and does not make a QuickML prediction call. Keep .env out of Git and sharing.

Official OAuth flow:
https://www.zoho.com/developer/oauth/self-client/authorization-code-flow.html
"""
import argparse
import getpass
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parent
TOKEN_URL = "https://accounts.zoho.in/oauth/v2/token"
ENDPOINT_URL = "https://api.catalyst.zoho.in/quickml/v1/project/89751000000013051/endpoints/predict"
ORG_ID = "60093489724"
SCOPE = "QuickML.deployment.READ"


class SetupError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_settings(text):
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if sep:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values.setdefault(key.strip(), value)
    return values


def valid_secret(value):
    return (isinstance(value, str) and bool(value.strip())
            and not value.lower().startswith(("your_", "paste_", "replace_"))
            and not any(char.isspace() for char in value)
            and not any(char in value for char in "<>\"'"))


def ask_secret(label, existing=""):
    if valid_secret(existing):
        print(label + ": using the value already in .env (hidden).")
        return existing
    value = getpass.getpass(label + " (paste, then Enter; input is hidden): ").strip()
    if not valid_secret(value):
        raise SetupError("A required credential is empty or still contains placeholder characters.")
    return value


def exchange_tokens(client_id, client_secret, grant_code):
    payload = urlencode({"client_id": client_id, "client_secret": client_secret,
                         "code": grant_code, "grant_type": "authorization_code"}).encode()
    request = Request(TOKEN_URL, data=payload, method="POST",
                      headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    status = 200
    try:
        with build_opener(NoRedirect).open(request, timeout=30) as response:
            raw = response.read(65537)
    except HTTPError as exc:
        status = exc.code
        raw = exc.read(65537)
    except (URLError, TimeoutError, OSError):
        raise SetupError("Could not reach Zoho's India token server. Check the connection and account region.") from None
    if len(raw) > 65536:
        raise SetupError("Zoho returned an unexpectedly large token response.")
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError):
        raise SetupError("Zoho did not return a valid JSON token response.") from None
    if not isinstance(result, dict):
        raise SetupError("Zoho returned an unexpected token response.")
    errors = {
        "invalid_code": "The grant code expired or was already used. Generate a fresh code and rerun this script.",
        "invalid_grant": "The grant code is invalid or expired. Generate a fresh code for this Self Client.",
        "invalid_client": "Check the Self Client ID, secret, and India account region.",
        "invalid_client_secret": "The Self Client secret is invalid. Copy it from the same Self Client as the grant code.",
        "invalid_scope": "Generate a grant code with scope QuickML.deployment.READ.",
    }
    error = result.get("error")
    if error or status >= 400:
        message = errors.get(error) if isinstance(error, str) else None
        raise SetupError(message or f"Zoho rejected the token request (HTTP {status}). Check the client, code and account region.")
    if not valid_secret(result.get("access_token")) or not valid_secret(result.get("refresh_token")):
        raise SetupError("Zoho did not return both access and refresh tokens. Use the Self Client authorization-code flow.")
    return {"access_token": result["access_token"], "refresh_token": result["refresh_token"]}


def updated_text(text, updates):
    for key, value in updates.items():
        if not isinstance(value, str) or "\n" in value or "\r" in value:
            raise SetupError("An invalid multiline configuration value was rejected.")
    found = set()
    lines = []
    for original in text.splitlines():
        stripped = original.strip()
        key, sep, _ = stripped.partition("=")
        key = key.strip()
        if not stripped.startswith("#") and sep and key in updates:
            lines.append(key + "=" + updates[key])
            found.add(key)
        else:
            lines.append(original)
    for key, value in updates.items():
        if key not in found:
            lines.append(key + "=" + value)
    return "\n".join(lines) + "\n"


def save_settings(path, expected_bytes, text, updates):
    current = path.read_bytes() if path.exists() else None
    if current != expected_bytes:
        raise SetupError("The .env file changed during setup. Keep that edit, then rerun with a fresh grant code.")
    content = updated_text(text, updates)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".env.setup-", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # mkstemp uses owner-only file permissions on systems that support them.
        os.replace(temporary, path)
    except OSError:
        raise SetupError("Could not save .env. Close its editor and rerun with a fresh grant code.") from None
    finally:
        if temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.parse_args()
    if not (ROOT / "quickml_smoke.py").exists() or not (ROOT / "predict.py").exists():
        raise SetupError("Save setup_zoho_auth.py inside C:\\GridPulse, beside app.py and quickml_smoke.py.")
    if not sys.stdin.isatty():
        raise SetupError("Run this script directly in an interactive PowerShell terminal, without piping input.")
    path = ROOT / ".env"
    before = path.read_bytes() if path.exists() else None
    template = ROOT / ".env.example"
    text = before.decode("utf-8-sig") if before is not None else template.read_text(encoding="utf-8-sig") if template.exists() else ""
    existing = read_settings(text)
    print("GridPulse India-region QuickML setup")
    print("Credentials are entered locally and are not displayed.")
    print("The token exchange sends them only to https://accounts.zoho.in/oauth/v2/token.")
    endpoint_key = ask_secret("QuickML endpoint key", existing.get("QUICKML_ENDPOINT_KEY", ""))
    client_id = ask_secret("Zoho Self Client ID", existing.get("ZOHO_CLIENT_ID", ""))
    client_secret = ask_secret("Zoho Self Client secret", existing.get("ZOHO_CLIENT_SECRET", ""))
    print("\nNow open this Self Client's Generate Code tab in your browser.")
    print("Scope: " + SCOPE)
    print("Choose a code duration, generate a NEW grant code, then paste it below promptly.")
    grant_code = ask_secret("Fresh grant code")
    print("Exchanging the grant code with Zoho...")
    tokens = exchange_tokens(client_id, client_secret, grant_code)
    updates = {
        "FORECAST_BACKEND": "quickml", "QUICKML_ENDPOINT_URL": ENDPOINT_URL,
        "QUICKML_ENDPOINT_KEY": endpoint_key, "QUICKML_ORG_ID": ORG_ID,
        "QUICKML_ENVIRONMENT": "Development", "QUICKML_FEATURE_MODE": "engineered",
        "QUICKML_REQUEST_MODE": "single", "QUICKML_REQUEST_KEY": "data", "QUICKML_RESPONSE_PATH": "result",
        "QUICKML_ACCESS_TOKEN": tokens["access_token"], "QUICKML_REFRESH_TOKEN": tokens["refresh_token"],
        "ZOHO_CLIENT_ID": client_id, "ZOHO_CLIENT_SECRET": client_secret, "ZOHO_TOKEN_URL": TOKEN_URL,
    }
    save_settings(path, before, text, updates)
    print("\nSetup saved in .env. Tokens were not printed.")
    print("Request mapping: single record inside data; numerical result array.")
    print("Next run: .\\.venv\\Scripts\\python.exe quickml_smoke.py")
    print("After a successful single prediction, restart app.py to use QuickML.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SetupError as exc:
        print("Setup failed: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
    except (KeyboardInterrupt, EOFError):
        print("\nSetup cancelled; no new settings saved.", file=sys.stderr)
        raise SystemExit(1)
    except (OSError, UnicodeError):
        print("Setup failed: could not access the configuration file. Check folder permissions.", file=sys.stderr)
        raise SystemExit(1)
