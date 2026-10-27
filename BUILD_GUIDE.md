# Build and learn GridPulse step by step

This package is a working local first version of the single problem statement in your kit. Follow the stages in order. The final stages connect it to mandatory Zoho services; they are not complete until you perform them in your account.

## Stage 1: Get the local application running

1. Install 64-bit Python 3.11 or 3.12 if it is not installed. Check using `py --list` in PowerShell.
2. Extract the ZIP into a normal writable folder such as `C:\Projects\GridPulse`. Confirm `app.py`, `train.py` and `requirements.txt` are directly inside that folder. Do not work inside the unopened ZIP. A normal folder avoids the protected-directory problems encountered in earlier projects.
3. Open that folder in VS Code, then open a PowerShell terminal. The terminal should be in the folder containing `app.py`.
4. Run these commands one at a time:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe train.py
.\.venv\Scripts\python.exe test_eval.py
.\.venv\Scripts\python.exe app.py
```

If you only have Python 3.12, use `py -3.12` on the first line. Keep using `.\.venv\Scripts\python.exe` for the other commands. If `py` is unavailable but `python --version` shows 3.11/3.12, use `python -m venv .venv`.

Expected result: training prints model comparisons; the official self-test ends with `SUCCESS`; the server prints a URL. Open **http://127.0.0.1:8000** in your browser.

No activation, CUDA, model download, API key, database, Node installation or GPU setup is needed for this stage. Dependencies are downloaded from PyPI once; the local application then runs offline.

## Stage 2: Verify what the dashboard does

1. The default 24-hour plan uses the first complete day of historical weather from the official sample CSV. Check peak demand, overload count and the source timeline.
2. Click a chart point or timeline hour. The selected dispatch signal and end-of-hour simulated SOC should change together.
3. Click **Play simulation**, then pause it. This replays the forecast; it is not live sensor telemetry.
4. Open **Telemetry**. Edit one temperature, then choose **Forecast these rows**. The updated forecast must use the edited inputs.
5. Download the sample CSV from Telemetry. Upload it using **Upload CSV** on Overview. This is a valid 24-row file. Do not upload all 1,000 sample rows into the dashboard; that file is for the CLI.
6. Open **Adjust battery settings**. Try a capacity of 100 kWh. The simulator should report a shortage, while the exact required grid signal remains unchanged.
7. Download the dispatch CSV. It includes hour, predicted demand, mode, overload and simulated battery results.

Bad-input check: change a humidity value to 120 and run the forecast. You should receive a clear validation error. Change it back to a number between 0 and 100 before continuing.

## Stage 3: Understand and verify the rules

Read `gridpulse/controller.py`. The only decisions are:

```python
storage = demand_kw > 160 or 18 <= hour <= 22
critical = demand_kw >= 200
```

The decision uses the unrounded number. Run the tests in a second terminal, or stop the server with Ctrl+C first:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Expected result: all tests pass. The controller checks include exactly 160, just above 160, exactly 200, 17:00, 18:00, 22:00 and 23:00.

## Stage 4: Understand the forecasting model

Read `gridpulse/schema.py`, then `train.py`, then `gridpulse/forecasting.py`.

The supplied training rows are chronological. Local validation uses the first 3,200 to fit models and the last 800 to compare them. Gradient boosting performed best in the checked environment. The final saved model is refit on all 4,000 rows. The 1,000 sample-test rows have weather only, so they cannot provide an accuracy score.

Generate the exact evaluator output:

```powershell
.\.venv\Scripts\python.exe predict.py --input sample_test_input.csv --output predictions.csv
```

Open `predictions.csv`: two columns, 1,000 predictions, same timestamps/order as the input. No target labels were used as prediction inputs. No dummy fallback remains.

## Stage 5: Train inside Zoho QuickML

1. Open the hackathon onboarding link in `original_starter/PROBLEM_STATEMENT.md` or the official QuickML docs linked in the cloud guide.
2. Check your event-provided access/free quota first. The local app is free; Zoho use is limited by your account allowance.
3. Run:

```powershell
.\.venv\Scripts\python.exe prepare_quickml.py
```

4. Follow [docs/QUICKML_AND_CATALYST.md](docs/QUICKML_AND_CATALYST.md). It explains which CSV to upload, target selection, engineered/raw feature consistency, model publication, authentication and endpoint-shape settings.
5. Use a small single-row live check first. Then verify the 24-hour dashboard using the QuickML backend. Run the 1,000-row official self-test only after confirming the account's inference allowance and supported request batching.

Do not replace the required QuickML model with the local sklearn model for submission. The local version is your development baseline.

## Stage 6: Publish on Catalyst AppSail

Use the cloud guide's dependency-bundling command and deployment settings. The app starts with `python3 -u app.py` and reads the platform's `X_ZOHO_CATALYST_LISTEN_PORT` automatically.

Set `FORECAST_BACKEND=quickml`, `HOST=0.0.0.0`, and all QuickML secrets in server environment settings. Do not put credentials in browser JavaScript, a public repository, a submission ZIP or screenshots. Make a live request after deployment and confirm the visible badge says **QuickML · verified this run**.

## Stage 7: Prepare the final submission

- Public Catalyst application URL, accessible to judges without your own login session.
- Source ZIP or public GitHub repository, preserving the required `predict.py` and original `test_eval.py`.
- Working published QuickML endpoint, correct environment and stable authentication that will still work during judging.
- README explaining the setup and environment variables, without actual secrets.
- A successful official self-test while `FORECAST_BACKEND=quickml`.

The files do not state a verified submission deadline. Use the event page/organizer's current deadline rather than guessing from this kit.

## Common fixes

| Symptom | Fix |
|---|---|
| `.venv\Scripts\python.exe` not found | Check your folder and complete the venv creation command first |
| Python 3.11 not installed | Use the installed 3.12 interpreter, or install Python 3.11 64-bit |
| `ModuleNotFoundError` | Use the same `.venv` interpreter for pip, training and starting the app |
| Local model missing | Run `train.py`, then restart the server |
| Port already in use | Stop the old server, or run `app.py --port 8001` and open that port |
| Browser shows an old error after fixing setup | Restart the app, then refresh the browser |
| Browser fails to reach the API | Open the URL printed by the running app; do not double-click `static/index.html` |
| Dashboard rejects sample CSV | Use a 24-row template; run the 1,000-row file through `predict.py` |
| QuickML HTTP 401/403 | Check OAuth scope, token expiry, region, org, endpoint key and Development/Production environment |
| QuickML HTTP 400 / response-shape error | Compare feature names and the exact sample request/response in your endpoint console |
| Cloud says a Python library is missing | Upload the `--vendor` build, not the source-only ZIP or Windows native packages |
| A published page still says Local model | Set the cloud backend to quickml, restart the deployment and make a successful forecast |
