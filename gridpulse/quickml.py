"""Explicit QuickML REST adapter; credentials never enter the browser or error text."""
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import json
import math
import os
from pathlib import Path
import socket
import ssl
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler

DEFAULT_ENDPOINT = "https://api.catalyst.zoho.in/quickml/v1/project/89751000000013051/endpoints/predict"


def setting(name, default=""):
    return os.getenv(name, default).strip().strip("\"'\u201c\u201d\u2018\u2019").strip()


def network_error(operation, error):
    reason = error.reason if isinstance(error, URLError) else error
    if isinstance(reason, ssl.SSLCertVerificationError):
        detail = "TLS_CERTIFICATE: the server certificate could not be verified"
    elif isinstance(reason, socket.gaierror):
        detail = "DNS_LOOKUP: the QuickML host could not be resolved"
    elif isinstance(reason, (TimeoutError, socket.timeout)):
        detail = "NETWORK_TIMEOUT: QuickML did not respond before the configured timeout"
    elif isinstance(reason, ssl.SSLError):
        detail = "TLS_CONNECTION: the encrypted connection could not be established"
    elif isinstance(reason, (ConnectionError, OSError)):
        detail = "NETWORK_CONNECTION: the connection was refused, interrupted, or unavailable"
    else:
        detail = "NETWORK_CONNECTION: the remote service could not be reached"
    return QuickMLError(f"{operation} failed [{detail}]. No local fallback was used.")


class QuickMLError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class QuickMLClient:
    def __init__(self):
        self.endpoint = setting("QUICKML_ENDPOINT_URL", DEFAULT_ENDPOINT) or DEFAULT_ENDPOINT
        self.key = setting("QUICKML_ENDPOINT_KEY")
        self.org = setting("QUICKML_ORG_ID", "60093489724") or "60093489724"
        environment = setting("QUICKML_ENVIRONMENT", "Development").casefold()
        self.environment = {"development": "Development", "production": "Production"}.get(environment, "")
        self.mode = setting("QUICKML_REQUEST_MODE", "single").casefold()
        self.request_key = setting("QUICKML_REQUEST_KEY", "data")
        self.response_path = setting("QUICKML_RESPONSE_PATH", "result")
        self.batch_size = int(os.getenv("QUICKML_BATCH_SIZE", "24"))
        self.timeout = float(os.getenv("QUICKML_TIMEOUT_SECONDS", "30"))
        try:
            self.max_workers = int(os.getenv("QUICKML_MAX_WORKERS", "4"))
        except ValueError:
            raise QuickMLError("QUICKML_MAX_WORKERS must be an integer between 1 and 8.") from None
        self.token = setting("QUICKML_ACCESS_TOKEN")
        self.expires_at = 0
        self.lock = threading.Lock()
        self.opener = self._new_opener()
        self.opener_thread = threading.get_ident()
        self.worker_state = threading.local()
        if urlparse(self.endpoint).scheme != "https" or not urlparse(self.endpoint).hostname:
            raise QuickMLError("Set QUICKML_ENDPOINT_URL to the HTTPS endpoint copied from QuickML.")
        if not self.key or not self.org:
            raise QuickMLError("Set QUICKML_ENDPOINT_KEY and QUICKML_ORG_ID on the server.")
        if self.mode not in {"single", "batch"} or not 1 <= self.batch_size <= 1000:
            raise QuickMLError("QuickML request mode or batch size is invalid.")
        if not math.isfinite(self.timeout) or not 1 <= self.timeout <= 120:
            raise QuickMLError("QuickML timeout must be between 1 and 120 seconds.")
        if self.environment not in {"Development", "Production"}:
            raise QuickMLError("QUICKML_ENVIRONMENT must be Development or Production.")
        if not 1 <= self.max_workers <= 8:
            raise QuickMLError("QUICKML_MAX_WORKERS must be an integer between 1 and 8.")

    @staticmethod
    def _new_opener():
        context = ssl.create_default_context()
        bundle = Path(__file__).with_name("cacert.pem")
        if bundle.exists():
            context.load_verify_locations(cafile=str(bundle))
        return build_opener(NoRedirect, HTTPSHandler(context=context))

    def _access_token(self):
        refresh = setting("QUICKML_REFRESH_TOKEN")
        if not refresh:
            if not self.token:
                raise QuickMLError("Set a QuickML OAuth access token or refresh credentials on the server.")
            return self.token
        with self.lock:
            if self.token and time.monotonic() < self.expires_at:
                return self.token
            client_id, secret = setting("ZOHO_CLIENT_ID"), setting("ZOHO_CLIENT_SECRET")
            token_url = setting("ZOHO_TOKEN_URL", "https://accounts.zoho.in/oauth/v2/token")
            parsed = urlparse(token_url)
            if parsed.scheme != "https" or parsed.hostname not in {
                "accounts.zoho.com", "accounts.zoho.in", "accounts.zoho.eu", "accounts.zoho.com.au",
                "accounts.zoho.jp", "accounts.zohocloud.ca", "accounts.zoho.sa", "accounts.zoho.com.cn"}:
                raise QuickMLError("Use the official Zoho OAuth token URL for your account region.")
            if not client_id or not secret:
                raise QuickMLError("Refresh authentication also requires ZOHO_CLIENT_ID and ZOHO_CLIENT_SECRET.")
            payload = urlencode({"refresh_token": refresh, "client_id": client_id,
                                 "client_secret": secret, "grant_type": "refresh_token"}).encode()
            req = Request(token_url, data=payload, method="POST",
                          headers={"Content-Type": "application/x-www-form-urlencoded"})
            result = self._send(req, "OAuth refresh")
            if not isinstance(result, dict) or not result.get("access_token"):
                raise QuickMLError("OAuth refresh failed. Check the region, scope, and server credentials.")
            self.token = str(result["access_token"])
            try:
                lifetime = float(result.get("expires_in", 3600))
            except (TypeError, ValueError):
                raise QuickMLError("OAuth refresh returned an invalid expiry.") from None
            if not math.isfinite(lifetime) or lifetime <= 0:
                raise QuickMLError("OAuth refresh returned an invalid expiry.")
            self.expires_at = time.monotonic() + max(0, lifetime-60)
            return self.token

    def _send(self, request, operation):
        try:
            # Each worker gets its own HTTP opener. The OAuth token cache is shared
            # and remains protected by the existing refresh lock.
            if threading.get_ident() == self.opener_thread:
                opener = self.opener
            else:
                if not hasattr(self.worker_state, "opener"):
                    self.worker_state.opener = self._new_opener()
                opener = self.worker_state.opener
            with opener.open(request, timeout=self.timeout) as response:
                body = response.read(2_000_001)
            if len(body) > 2_000_000:
                raise QuickMLError(f"{operation} response exceeded the size limit.")
            return json.loads(body)
        except HTTPError as exc:
            # Read only recognized error identifiers; never echo provider messages,
            # response bodies, request URLs, headers or access tokens.
            hints = {"INVALID_ENDPOINT_KEY": "Copy the endpoint key from GridPulseDemandAPI into Catalyst.",
                     "INVALID_OAUTHTOKEN": "Check the OAuth refresh credentials and account region.",
                     "OAUTH_SCOPE_MISMATCH": "The token needs scope QuickML.deployment.READ.",
                     "INVALID_CODE": "The OAuth refresh token is invalid or revoked.",
                     "INVALID_CLIENT": "Check the OAuth client ID, secret and account region."}
            identifier = None
            try:
                raw = exc.read(65537)
                payload = json.loads(raw) if len(raw) <= 65536 else None
                def recognized(value, depth=0):
                    if not isinstance(value, dict) or depth > 3:
                        return None
                    for key in ("code", "error_code", "error"):
                        item = value.get(key)
                        if isinstance(item, str) and item.upper() in hints:
                            return item.upper()
                    for key in ("data", "error", "response"):
                        found = recognized(value.get(key), depth+1)
                        if found:
                            return found
                    return None
                identifier = recognized(payload)
            except (ValueError, UnicodeError, OSError):
                pass
            finally:
                exc.close()
            detail = f" [{identifier}]. {hints[identifier]}" if identifier else ". Check endpoint, OAuth scope, environment and credentials."
            raise QuickMLError(f"{operation} failed (HTTP {exc.code})"+detail) from None
        except (URLError, TimeoutError, OSError) as exc:
            raise network_error(operation, exc) from None
        except (json.JSONDecodeError, UnicodeError):
            raise QuickMLError(f"{operation} returned invalid JSON.") from None

    def _extract(self, result, expected):
        try:
            value = result
            for part in self.response_path.split(".") if self.response_path else []:
                value = value[int(part)] if isinstance(value, list) else value[part]
            if not isinstance(value, list):
                value = [value]
            values = []
            for item in value:
                if isinstance(item, dict):
                    if "prediction" in item:
                        item = item["prediction"]
                    else:
                        item = item["target_demand_kw"]
                if isinstance(item, bool):
                    raise ValueError()
                values.append(float(item))
        except (KeyError, IndexError, TypeError, ValueError, OverflowError):
            raise QuickMLError("QuickML response shape does not match QUICKML_RESPONSE_PATH. Compare with the endpoint's sample response.") from None
        if len(values) != expected or not all(math.isfinite(v) and v >= 0 for v in values):
            raise QuickMLError("QuickML must return one finite, nonnegative demand value per input row.")
        return values

    def _predict_batch(self, batch):
        payload = batch[0] if self.mode == "single" else batch
        if self.request_key:
            payload = {self.request_key: payload}
        headers = {"Content-Type": "application/json", "Accept": "application/json",
                   "X-QUICKML-ENDPOINT-KEY": self.key, "CATALYST-ORG": self.org,
                   "Environment": self.environment,
                   "Authorization": "Zoho-oauthtoken " + self._access_token()}
        request = Request(self.endpoint, data=json.dumps(payload, allow_nan=False).encode(),
                          headers=headers, method="POST")
        return self._extract(self._send(request, "QuickML prediction"), len(batch))

    def predict(self, records):
        size = 1 if self.mode == "single" else self.batch_size
        batches = [records[offset:offset+size] for offset in range(0, len(records), size)]
        if not batches:
            return []
        # Check authentication and schema once before scheduling further calls.
        values = self._predict_batch(batches[0])
        remaining = batches[1:]
        if self.mode == "batch" or self.max_workers == 1 or len(remaining) < 2:
            for batch in remaining:
                values.extend(self._predict_batch(batch))
            return values
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(remaining)),
                                thread_name_prefix="gridpulse-quickml") as executor:
            queued = iter(enumerate(remaining))
            pending = {}
            ordered = [None] * len(remaining)

            def fill_workers():
                while len(pending) < self.max_workers:
                    item = next(queued, None)
                    if item is None:
                        return
                    index, batch = item
                    pending[executor.submit(self._predict_batch, batch)] = index

            try:
                fill_workers()
                while pending:
                    completed, _ = wait(pending, return_when=FIRST_COMPLETED)
                    # Surface an error before scheduling more work. Only a small
                    # fixed number of prediction requests can be outstanding.
                    for future in completed:
                        index = pending.pop(future)
                        ordered[index] = future.result()
                    fill_workers()
            except BaseException:
                for future in pending:
                    future.cancel()
                raise
            for result in ordered:
                values.extend(result)
        return values
