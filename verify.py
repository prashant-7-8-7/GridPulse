"""Repeatable LOCAL checks. This does not claim QuickML access or cloud deployment."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parent


def verify():
    env=dict(os.environ,FORECAST_BACKEND="local")
    commands=[
        [sys.executable,"-m","unittest","discover","-s","tests","-v"],
        [sys.executable,"test_eval.py"],
        [sys.executable,"predict.py","--input","sample_test_input.csv","--output","examples/sample_predictions.csv"],
        [sys.executable,"build_appsail.py"],
    ]
    checks=[]
    for cmd in commands:
        print("Running:"," ".join(cmd),flush=True)
        run=subprocess.run(cmd,cwd=ROOT,env=env,capture_output=True,text=True)
        output=run.stdout+run.stderr
        print(output,flush=True)
        checks.append({"command":" ".join(["python",*cmd[1:]]),"exit_code":run.returncode,"output":output})
        if run.returncode:
            raise SystemExit("A check failed; see output above.")
    import pandas as pd
    import numpy as np
    source=pd.read_csv(ROOT/"sample_test_input.csv")
    prediction=pd.read_csv(ROOT/"examples/sample_predictions.csv")
    assert prediction.columns.tolist()==["timestamp","target_demand_kw"]
    assert prediction.timestamp.tolist()==source.timestamp.tolist()
    assert np.isfinite(prediction.target_demand_kw).all()
    with ZipFile(ROOT/"dist/GridPulse_AppSail.zip") as z:
        names=z.namelist()
        assert "app.py" in names and "static/index.html" in names
        assert not any(".env" in Path(n).parts or ".venv" in Path(n).parts or n.endswith(".joblib") for n in names)
    starter=(ROOT/"original_starter/test_eval.py").read_bytes()
    assert starter==(ROOT/"test_eval.py").read_bytes()
    report={"checked_at_utc":datetime.now(timezone.utc).isoformat(),"backend":"local","checks":checks,
            "sample_rows":len(prediction),"preserves_all_sample_timestamps_and_order":True,
            "starter_self_test_unchanged_sha256":hashlib.sha256(starter).hexdigest(),
            "source_appsail_zip_excludes_secrets_and_local_binary":True,
            "cloud_endpoint_verified":None,"cloud_deployed":None,
            "cloud_status_note":"Not checked by this local script. See SUBMISSION.md and docs/LIVE_VERIFICATION.json for separate cloud checks.",
            "browser_qa":"Not performed by this script. At initial delivery, layout/navigation were inspected, but the managed preview runtime reported missing scientific Python dependencies; populated browser charts and interactions were not fully verified there. HTTP/API ingestion was verified in the installed primary Python runtime.",
            "cloud_build_note":"Source-only AppSail ZIP checked. Linux dependency vendoring and deployment need internet access and the user's Zoho account."}
    output_path=ROOT/"docs/VALIDATION.json"
    output_path.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("LOCAL VERIFICATION PASSED. Report:",output_path)
    print("These checks are local only. Use deploy_final.py for the separate hosted QuickML verification.")


if __name__=="__main__":verify()
