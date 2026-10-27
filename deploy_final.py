r"""Update the existing AppSail build, deploy, verify one forecast, and package source.

Run on your laptop: .\.venv\Scripts\python.exe deploy_final.py
Uses the existing Catalyst CLI login and private variables already saved in Catalyst.
Never prints, packages, or passes credentials on the command line.
"""
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent
PROJECT = "89751000000013051"
ORG = "60093489724"
URL = "https://gridpulse-50047201220.development.catalystappsail.in"
BUILD = "2026-10-27-final1"
PUBLIC_SETTINGS = {
    "FORECAST_BACKEND": "quickml",
    "QUICKML_ENDPOINT_URL": "https://api.catalyst.zoho.in/quickml/v1/project/89751000000013051/endpoints/predict",
    "QUICKML_ORG_ID": ORG, "QUICKML_ENVIRONMENT": "Development",
    "QUICKML_FEATURE_MODE": "engineered", "QUICKML_REQUEST_MODE": "single",
    "QUICKML_REQUEST_KEY": "data", "QUICKML_RESPONSE_PATH": "result",
    "QUICKML_MAX_WORKERS": "4", "QUICKML_TIMEOUT_SECONDS": "60",
    "ZOHO_TOKEN_URL": "https://accounts.zoho.in/oauth/v2/token",
}
SOURCE_DIRS = {"gridpulse", "static", "tests", "docs", "examples", "quickml_data", "original_starter", "LICENSES", "presentation"}
SOURCE_FILES = {"app.py", "predict.py", "train.py", "evaluate.py", "prepare_quickml.py",
                "quickml_smoke.py", "quickml_diagnose.py", "setup_zoho_auth.py", "verify.py",
                "build_appsail.py", "deploy_final.py", "README.md", "BUILD_GUIDE.md",
                "SUBMISSION.md", "requirements.txt", "requirements-cloud.txt", "package.json",
                "test_eval.py", "train_telemetry.csv", "sample_test_input.csv", ".env.example", ".gitignore"}


def package_source():
    destination = ROOT / "GridPulse_Submission.zip"
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT)
            if "__pycache__" in rel.parts or path.suffix in {".pyc", ".joblib"}:
                continue
            if any(part == ".env" or part.startswith(".env.") and part != ".env.example" for part in rel.parts):
                continue
            if len(rel.parts) == 1 and rel.name in SOURCE_FILES or rel.parts[0] in SOURCE_DIRS or rel.as_posix() in {"models/feature_medians.json", "models/metrics.json"}:
                archive.write(path, rel.as_posix())
    return destination


def request_json(path, payload=None):
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers.update({"Content-Type": "application/json", "Prefer": "respond-async"})
    request = Request(URL+path, data=json.dumps(payload).encode() if payload is not None else None,
                      headers=headers, method="POST" if payload is not None else "GET")
    try:
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    except HTTPError as error:
        try:
            obj = json.loads(error.read(2000))
            message = obj.get("error", "HTTP request failed")
        except (ValueError, AttributeError):
            message = "HTTP request failed"
        raise RuntimeError(f"Hosted app HTTP {error.code}: {message}") from None
    except (URLError, TimeoutError, OSError):
        raise RuntimeError("Could not reach the hosted app for verification.") from None


def main():
    cli = shutil.which("catalyst.cmd" if os.name == "nt" else "catalyst")
    if cli is None:
        raise RuntimeError("Catalyst CLI is not on PATH. Reopen PowerShell after installing zcatalyst-cli.")
    project_root = ROOT / "catalyst-upload"
    stage = project_root / "build"
    if not (project_root / ".catalystrc").exists():
        raise RuntimeError("Use the existing C:\\GridPulse folder, containing catalyst-upload and its CLI project setup.")
    if not (stage / "numpy").is_dir() or not (stage / "pandas").is_dir():
        print("Preparing Linux dependencies...", flush=True)
        subprocess.run([sys.executable, str(ROOT/"build_appsail.py"), "--vendor"], cwd=ROOT, check=True)
        with ZipFile(ROOT/"dist/GridPulse_AppSail.zip") as archive:
            archive.extractall(stage)
    print("Updating the deployment files...", flush=True)
    for name in ("app.py", "predict.py", "train_telemetry.csv", "sample_test_input.csv", "requirements-cloud.txt"):
        shutil.copy2(ROOT/name, stage/name)
    for name in ("gridpulse", "static", "LICENSES"):
        shutil.copytree(ROOT/name, stage/name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (stage/"models").mkdir(exist_ok=True)
    for name in ("feature_medians.json", "metrics.json"):
        shutil.copy2(ROOT/"models"/name, stage/"models"/name)
    if any(path.name == ".env" for path in stage.rglob(".env")):
        raise RuntimeError("Remove the private .env file from catalyst-upload/build; credentials belong in Catalyst settings.")
    command = "env " + " ".join(key+"="+value for key, value in PUBLIC_SETTINGS.items())
    command += " python3 -u app.py --host 0.0.0.0 --port 9000"
    print("Deploying to the existing GridPulse project. Select Python 3.11 if prompted.", flush=True)
    subprocess.run([cli, "deploy", "appsail", "--dc", "in", "--org", ORG, "--project", PROJECT,
                    "--name", "gridpulse", "--build-path", str(stage), "--command", command],
                   cwd=project_root, check=True)
    print("Checking the deployed build...", flush=True)
    for attempt in range(12):
        try:
            health = request_json("/health")
            if health.get("build") == BUILD:
                break
        except (RuntimeError, ValueError):
            pass
        time.sleep(2)
    else:
        raise RuntimeError("The new build is not visible yet. Check the AppSail deployment status.")
    with (ROOT/"examples/demo_telemetry.csv").open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        for key in ("ambient_temp_c", "humidity_pct", "solar_irradiance_wm2"):
            row[key] = float(row[key])
    print("Verifying one real 24-hour QuickML forecast. This uses 24 prediction calls.", flush=True)
    reply = request_json("/api/forecast", {"rows": rows})
    started = time.monotonic()
    if "job_id" in reply:
        while time.monotonic()-started < 240:
            job = request_json("/api/forecast-jobs/"+reply["job_id"])
            if job.get("status") == "failed":
                raise RuntimeError(job.get("error", "Cloud forecast failed"))
            if job.get("status") == "complete":
                result = job["result"]
                break
            print("Forecast running...", flush=True)
            time.sleep(2)
        else:
            raise RuntimeError("Cloud forecast did not finish in four minutes.")
    else:
        result = reply
    outputs = result.get("rows", [])
    checks = {"quickml_backend": result.get("backend") == "quickml", "24_predictions": len(outputs) == 24,
              "timestamps_preserved": [r.get("timestamp") for r in outputs] == [r["timestamp"] for r in rows],
              "dispatch_rules": True, "overload_rules": True}
    for row in outputs:
        demand, hour = float(row["target_demand_kw"]), int(row["timestamp"][11:13])
        mode = "renewable_storage" if demand > 160 or 18 <= hour <= 22 else "main_grid"
        checks["dispatch_rules"] &= row.get("grid_mode") == mode
        checks["overload_rules"] &= row.get("critical_overload") == (demand >= 200)
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "url": URL, "build": BUILD,
              "checks": checks, "passed": all(checks.values()), "summary": result.get("summary")}
    (ROOT/"docs/LIVE_VERIFICATION.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    if not report["passed"]:
        raise RuntimeError("Cloud output failed verification. Check docs/LIVE_VERIFICATION.json.")
    output = package_source()
    print("\nQUICKML VERIFIED: 24 predictions, timestamps and dispatch rules passed.")
    print("Submit URL:", URL)
    print("Submit source ZIP:", output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print("Deployment/verification stopped:", str(error), file=sys.stderr)
        print("Source package:", package_source(), file=sys.stderr)
        print("Live QuickML forecast is NOT verified; do not report it as working yet.", file=sys.stderr)
        raise SystemExit(1)
