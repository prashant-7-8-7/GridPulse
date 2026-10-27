r"""Diagnose one GridPulse QuickML request without printing credentials.

Run beside app.py: .\.venv\Scripts\python.exe quickml_diagnose.py
Makes at most ONE prediction request, plus an OAuth refresh if configured.
Does not edit .env, retry predictions, or use the local model.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError
from urllib.parse import quote, quote_plus, urlparse


ROOT = Path(__file__).resolve().parent
EXPECTED_ENDPOINT = "https://api.catalyst.zoho.in/quickml/v1/project/89751000000013051/endpoints/predict"
ERROR_FIELDS = {"code", "error_code", "errorcode", "message", "error_message",
                "errormessage", "error_description", "error", "detail", "status"}
CONTAINERS = {"data", "error", "errors", "details", "response", "result"}


def redact(value, secrets=()):
    text = str(value)
    for secret in sorted({s for s in secrets if isinstance(s, str) and s}, key=len, reverse=True):
        for variant in {secret, quote(secret, safe=""), quote_plus(secret)}:
            text = text.replace(variant, "[REDACTED]")
    text = re.sub(r"https?://\S+", "[URL REDACTED]", text, flags=re.I)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[EMAIL REDACTED]", text)
    text = re.sub(r"[A-Za-z0-9_./+=-]{32,}", "[LONG VALUE REDACTED]", text)
    # Escape terminal controls and keep each field on one bounded ASCII line.
    text = " ".join(text.split())
    text = text.encode("ascii", "backslashreplace").decode("ascii")
    text = re.sub(r"[\x00-\x1f\x7f]", "?", text)
    return text[:600]


def error_summary(body, secrets=()):
    if len(body) > 65536:
        return ["Error response was too large; its contents were omitted."]
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeError):
        return ["Zoho returned a non-JSON error page; its contents were omitted."]
    lines = []

    def walk(value, path="", depth=0):
        if depth > 4 or len(lines) >= 10:
            return
        if isinstance(value, list):
            for item in value[:3]:
                walk(item, path, depth + 1)
        elif isinstance(value, dict):
            for key, item in value.items():
                normalized = str(key).lower()
                if normalized in ERROR_FIELDS and isinstance(item, (str, int, float, bool)):
                    lines.append(path + normalized + ": " + redact(item, secrets))
                elif normalized in CONTAINERS and isinstance(item, (dict, list)):
                    walk(item, path + normalized + ".", depth + 1)
                if len(lines) >= 10:
                    break

    walk(payload)
    return lines or ["JSON error had no recognized code/message fields; other fields were omitted."]


class InspectingOpener:
    def __init__(self, client):
        self.client = client
        self.inner = client.opener
        self.prediction_calls = 0

    def open(self, request, **kwargs):
        is_prediction = request.full_url == self.client.endpoint
        label = "Prediction" if is_prediction else "OAuth refresh"
        if is_prediction:
            self.prediction_calls += 1
            if self.prediction_calls > 1:
                raise RuntimeError("Diagnostic stopped before a second prediction request.")
        try:
            response = self.inner.open(request, **kwargs)
        except HTTPError as error:
            print(f"{label}: HTTP {error.code}", flush=True)
            secrets = [self.client.key, self.client.token]
            secrets.extend(value for name, value in os.environ.items()
                           if re.search(r"TOKEN|SECRET|PASSWORD|ENDPOINT_KEY|CLIENT_ID", name, re.I))
            auth = request.get_header("Authorization", "")
            secrets.extend([auth, auth.removeprefix("Zoho-oauthtoken ")])
            try:
                body = error.read(65537)
                for line in error_summary(body, secrets):
                    print("  " + line, flush=True)
            except OSError:
                print("  Error details could not be read.", flush=True)
            finally:
                error.close()
            raise
        print(f"{label}: HTTP {response.status}", flush=True)
        return response


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--console-sample", type=Path,
                        help="Optional complete Sample Request JSON copied from this endpoint's console.")
    args = parser.parse_args()
    inherited = set(os.environ)
    # Load the project's existing .env through exactly the same path as predict.py.
    import pandas as pd
    from gridpulse.config import backend
    from gridpulse.forecasting import medians
    from gridpulse.quickml import QuickMLClient
    from gridpulse.schema import features, validate

    if backend() != "quickml":
        raise RuntimeError("FORECAST_BACKEND must be quickml. Run from C:\\GridPulse after authentication setup.")
    client = QuickMLClient()
    if client.endpoint.rstrip("/") != EXPECTED_ENDPOINT:
        raise RuntimeError("QUICKML_ENDPOINT_URL does not match the GridPulse India endpoint shown earlier. Check it locally.")
    if client.mode != "single" or client.request_key != "data":
        raise RuntimeError("For this endpoint set QUICKML_REQUEST_MODE=single and QUICKML_REQUEST_KEY=data in .env.")
    if os.getenv("QUICKML_FEATURE_MODE", "engineered") != "engineered":
        raise RuntimeError("For this endpoint set QUICKML_FEATURE_MODE=engineered in .env.")
    print("GridPulse QuickML diagnostic (one prediction; no configuration edits)")
    print("Endpoint host: api.catalyst.zoho.in")
    print("Environment: " + client.environment)
    print("Request: single record inside data; response path: " + redact(client.response_path))
    print("OAuth refresh credentials: " + ("present" if os.getenv("QUICKML_REFRESH_TOKEN") else "absent; using saved access token"))
    print("Token service: " + redact(urlparse(os.getenv("ZOHO_TOKEN_URL", "https://accounts.zoho.in/oauth/v2/token")).hostname))
    relevant = sorted(name for name in inherited if name.startswith(("QUICKML_", "ZOHO_")) or name == "FORECAST_BACKEND")
    if relevant:
        print("Shell variables override .env (names only): " + ", ".join(relevant))
    if args.console_sample:
        if args.console_sample.stat().st_size > 65536:
            raise ValueError("Sample Request file must be at most 64 KB.")
        payload = json.loads(args.console_sample.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict) or not payload["data"]:
            raise ValueError('Sample Request must be a JSON object containing a nonempty "data" object.')
        record = payload["data"]
    else:
        frame = pd.read_csv(ROOT / "sample_test_input.csv").iloc[:1]
        clean, _ = validate(frame, medians())
        record = features(clean).to_dict(orient="records")[0]
    print(f"Feature count: {len(record)}")
    client.opener = InspectingOpener(client)
    result = client.predict([record])
    print(f"QuickML verified: {float(result[0]):.6f} kW")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nDiagnostic cancelled.", file=sys.stderr)
        raise SystemExit(1)
    except (ValueError, RuntimeError, OSError, ImportError, KeyError) as error:
        secrets = [value for name, value in os.environ.items()
                   if re.search(r"TOKEN|SECRET|PASSWORD|ENDPOINT_KEY|CLIENT_ID", name, re.I)]
        print("Diagnostic stopped: " + redact(str(error), secrets), file=sys.stderr)
        raise SystemExit(1)
