"""Dependency-light HTTP application for local development and Catalyst AppSail."""
import argparse
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from gridpulse.config import ROOT, backend
from gridpulse.jobs import ForecastJobs

MAX_BODY = 2_200_000
MAX_FRAMING = 65_536
BUILD_VERSION = "2026-10-27-final1"


class RequestBodyError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def read_request_body(headers, stream):
    """Read bounded fixed-length or chunked JSON, including requests through a proxy."""
    lengths = headers.get_all("Content-Length", [])
    encodings = headers.get_all("Transfer-Encoding", [])
    if len(lengths) > 1 or (lengths and encodings):
        raise RequestBodyError(400, "Ambiguous request body framing.")
    if encodings:
        if len(encodings) != 1 or encodings[0].strip().lower() != "chunked":
            raise RequestBodyError(501, "Only chunked transfer encoding is supported.")
        body = bytearray()
        framing = 0

        def read_line():
            nonlocal framing
            line = stream.readline(8193)
            framing += len(line)
            if len(line) > 8192 or framing > MAX_FRAMING:
                raise RequestBodyError(413, "Request framing is too large.")
            if not line.endswith(b"\r\n"):
                raise RequestBodyError(400, "Incomplete or invalid chunk framing.")
            return line[:-2]

        while True:
            size_text = read_line().split(b";", 1)[0].strip(b" \t")
            if not size_text or any(c not in b"0123456789abcdefABCDEF" for c in size_text):
                raise RequestBodyError(400, "Invalid chunk size.")
            significant = size_text.lstrip(b"0") or b"0"
            if len(significant) > 16:
                raise RequestBodyError(413, "Upload limit is 2 MB.")
            size = int(significant, 16)
            if size > MAX_BODY - len(body):
                raise RequestBodyError(413, "Upload limit is 2 MB.")
            if size == 0:
                while True:
                    trailer = read_line()
                    if not trailer:
                        break
                    if b":" not in trailer or trailer.startswith((b" ", b"\t")):
                        raise RequestBodyError(400, "Invalid request trailer.")
                    # Trailer fields are consumed but never used as request headers.
                break
            chunk = stream.read(size)
            if len(chunk) != size or stream.read(2) != b"\r\n":
                raise RequestBodyError(400, "Incomplete or invalid chunk data.")
            body.extend(chunk)
            framing += 2
        body = bytes(body)
    else:
        if not lengths:
            raise RequestBodyError(411, "Request body length is missing. Send Content-Length or chunked transfer encoding.")
        text = lengths[0].strip()
        if not text or any(c not in "0123456789" for c in text):
            raise RequestBodyError(400, "Invalid Content-Length.")
        significant = text.lstrip("0") or "0"
        if len(significant) > 9:
            raise RequestBodyError(413, "Upload limit is 2 MB.")
        length = int(significant)
        if length > MAX_BODY:
            raise RequestBodyError(413, "Upload limit is 2 MB.")
        body = stream.read(length)
        if len(body) != length:
            raise RequestBodyError(400, "Incomplete request body.")
    if not body:
        raise RequestBodyError(400, "Request body is empty.")
    return body


class ApplicationServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.jobs = ForecastJobs()

    def server_close(self):
        jobs = getattr(self, "jobs", None)
        if jobs is not None:
            jobs.close()
        super().server_close()


def public_status():
    selected = backend()
    metrics_path = ROOT / "models/metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else None
    refresh = all(os.getenv(k) for k in ["QUICKML_REFRESH_TOKEN", "ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET"])
    configured = all(os.getenv(k) for k in ["QUICKML_ENDPOINT_URL", "QUICKML_ENDPOINT_KEY", "QUICKML_ORG_ID"])
    ready = (ROOT / "models/local_model.joblib").exists() if selected == "local" else bool(configured and (os.getenv("QUICKML_ACCESS_TOKEN") or refresh))
    return {"application": "GridPulse", "build": BUILD_VERSION, "backend": selected, "configured": ready,
            "connection_verified": False, "local_validation": metrics,
            "message": "Local model file present" if selected == "local" and ready else
                       "Run python train.py" if selected == "local" else
                       "QuickML configured; a successful forecast verifies access" if ready else
                       "Configure QuickML server environment variables"}


def demo_rows():
    import pandas as pd
    frame = pd.read_csv(ROOT / "sample_test_input.csv")
    # First complete midnight-to-midnight day, always actual supplied test weather.
    starts = frame.index[frame.timestamp.str.endswith("00:00:00")]
    first = next(int(i) for i in starts if i+24 <= len(frame))
    return frame.iloc[first:first+24].to_dict(orient="records")


class Handler(BaseHTTPRequestHandler):
    server_version = "GridPulse"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def log_message(self, fmt, *args):
        # Do not log URLs or user-controlled payloads; secrets are never returned.
        pass

    def send_bytes(self, status, content, kind="application/json; charset=utf-8", head=False):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-GridPulse-Build", BUILD_VERSION)
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        if not head:
            self.wfile.write(content)

    def send_json(self, status, value):
        self.send_bytes(status, json.dumps(value, allow_nan=False).encode())

    def do_HEAD(self):
        self.do_GET(head=True)

    def do_GET(self, head=False):
        path = urlsplit(self.path).path
        try:
            if path in {"/api/status", "/health"}:
                data = public_status() if path == "/api/status" else {"status": "ok", "build": BUILD_VERSION}
                return self.send_bytes(200, json.dumps(data).encode(), head=head)
            if path.startswith("/api/forecast-jobs/"):
                identifier = path.removeprefix("/api/forecast-jobs/")
                if len(identifier) != 32 or any(c not in "0123456789abcdef" for c in identifier):
                    return self.send_json(404, {"error": "Forecast job not found."})
                job = self.server.jobs.get(identifier)
                if job is None:
                    return self.send_json(404, {"error": "Forecast expired or the app restarted. Run the forecast again."})
                return self.send_bytes(200, json.dumps(job, allow_nan=False).encode(), head=head)
            if path == "/api/demo":
                return self.send_bytes(200, json.dumps({"rows": demo_rows(), "source": "Historical sample weather, not live telemetry"}).encode(), head=head)
            if path == "/api/template.csv":
                import pandas as pd
                return self.send_bytes(200, pd.DataFrame(demo_rows()).to_csv(index=False).encode(), "text/csv; charset=utf-8", head=head)
            allowed = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js",
                       "/styles.css": "styles.css", "/favicon.svg": "favicon.svg"}
            if path not in allowed:
                return self.send_json(404, {"error": "Not found"})
            file = ROOT / "static" / allowed[path]
            kind = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            return self.send_bytes(200, file.read_bytes(), kind + "; charset=utf-8", head=head)
        except ImportError:
            return self.send_json(503, {"error": "Python dependencies are missing. Install requirements.txt using the same interpreter that starts app.py."})
        except (ValueError, OSError, RuntimeError):
            return self.send_json(503, {"error": "Application configuration is unavailable. Check the server setup."})

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in {"/api/forecast", "/api/forecast-csv"}:
            return self.send_json(404, {"error": "Not found"})
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self.send_json(415, {"error": "Send application/json."})
        try:
            body = json.loads(read_request_body(self.headers, self.rfile))
            if not isinstance(body, dict):
                raise ValueError("Request body must be an object.")
            from gridpulse.battery import Battery
            Battery.from_dict(body.get("battery"))
            import pandas as pd
            from gridpulse.schema import read_csv
            from gridpulse.service import run_forecast
            if path == "/api/forecast-csv":
                frame = read_csv(body.get("csv"))
            else:
                rows = body.get("rows")
                if not isinstance(rows, list) or not rows or not all(isinstance(r, dict) for r in rows):
                    raise ValueError("rows must be a list of telemetry objects.")
                frame = pd.DataFrame(rows)
            if "respond-async" in self.headers.get("Prefer", "").lower():
                from gridpulse.forecasting import medians
                from gridpulse.schema import validate
                validate(frame, medians(), hourly_window=True)
                battery = body.get("battery")
                identifier = self.server.jobs.submit(lambda: run_forecast(frame, battery))
                return self.send_json(202, {"job_id": identifier, "status": "queued"})
            self.send_json(200, run_forecast(frame, body.get("battery")))
        except RequestBodyError as exc:
            self.close_connection = True
            self.send_json(exc.status, {"error": str(exc)})
        except TimeoutError:
            self.close_connection = True
            self.send_json(408, {"error": "Request body timed out."})
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            # Schema errors are purpose-written; never include arbitrary values from payloads.
            message = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) else "Invalid JSON or telemetry structure."
            self.send_json(400, {"error": message})
        except RuntimeError as exc:
            self.send_json(503, {"error": str(exc)})
        except Exception:
            self.send_json(500, {"error": "Forecast failed. Check the server environment and trained model."})


def make_server(host="127.0.0.1", port=8000):
    return ApplicationServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=int(os.getenv("X_ZOHO_CATALYST_LISTEN_PORT", os.getenv("PORT", "8000"))))
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0" if "X_ZOHO_CATALYST_LISTEN_PORT" in os.environ else "127.0.0.1"))
    parser.add_argument("--strictPort", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    server = make_server(args.host, args.port)
    print(f"GridPulse is running at http://{args.host}:{args.port} (backend: {backend()}).", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nGridPulse stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
