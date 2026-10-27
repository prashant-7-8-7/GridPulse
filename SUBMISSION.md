# GridPulse submission

**Project:** GridPulse - Smart Energy Microgrid & Demand Forecasting Engine

**Catalyst URL:** https://gridpulse-50047201220.development.catalystappsail.in/

**Source ZIP:** `GridPulse_Submission.zip`

## Description for the submission form

GridPulse forecasts hourly microgrid demand for a 24-hour weather window using a regression model trained in Zoho Catalyst QuickML. The Python backend validates CSV and form inputs, creates consistent weather and calendar features, and calls the published QuickML endpoint. It generates main-grid or renewable-storage signals using the required demand and evening-hour rules, and flags demand at or above 200 kW. The Catalyst AppSail dashboard shows forecasts, dispatch transitions, editable telemetry, CSV exports, and an explicitly simulated battery energy balance. Credentials remain in server settings.

## Technology

Python 3.11 on Catalyst AppSail; Python 3.12 supported for Windows development;
NumPy, pandas, Zoho QuickML gradient boosting regression, HTML, CSS, vanilla
JavaScript and SVG. Local scikit-learn models support development only.

## QuickML account artifacts

- Project ID: `89751000000013051`; organization: `60093489724`.
- Pipeline: `GridPulseDemandPipeline`.
- Model: `GridPulseDemandModel`; endpoint: `GridPulseDemandAPI`.
- Target: `target_demand_kw`; 11 engineered numerical inputs.
- Displayed model V1 metrics from the supplied console screenshot: RMSE
  **8.2451 kW**, MAE **6.6181 kW**, R2 **0.9649**.
- These are QuickML's own displayed evaluation metrics. They are not hidden-test
  scores or 96.49% accuracy; the console's evaluation split was not independently
  verified. The local chronological validation scores are reported separately.

## Verified deployment

The public Catalyst deployment completed a 24-row QuickML forecast on 27 October
2026. All outputs were finite and nonnegative, timestamps remained in order, and
dispatch and overload decisions matched the problem statement. The evidence is
in `docs/LIVE_VERIFICATION.json` and `docs/live_forecast.json`.

The editable deck and presenter notes are in `presentation/`.

## Apply and verify a future update

Extract this ZIP into the existing `C:\GridPulse` folder. In PowerShell:

```powershell
cd "C:\GridPulse"
.\.venv\Scripts\python.exe deploy_final.py
```

The helper reuses the existing Linux dependency build and CLI login, copies the
updated server, CA certificates and frontend, deploys to the explicit project,
checks the release identifier, and verifies one 24-hour forecast. It sets the
non-secret endpoint configuration directly at startup, avoiding copied-value
errors. Existing private credentials remain in Catalyst environmental variables.

If successful, the helper writes `docs/LIVE_VERIFICATION.json` and creates the
updated `C:\GridPulse\GridPulse_Submission.zip`. Submit that ZIP and the URL above.
Open the URL in an incognito window and confirm the forecast is accessible without
your Zoho login. Keep the service and endpoint available through judging.

If the helper reports failure, the live workflow is not verified. Its named
network category distinguishes DNS resolution, certificate verification, TLS
connection and network timeout problems. Do not claim the submission is fully
working while a live forecast fails.

## Required evaluation interface

`predict.py` exposes `predict(input_df)` and the required CSV CLI, preserving one
numeric result and the original timestamp per input row. `test_eval.py` remains
unchanged from the official starter. Offline contract checks are not proof of
QuickML-backed evaluation. Running that check in QuickML mode uses 1,000 prediction
requests; confirm sufficient event allowance before running it or an 800-row
external validation. Do not alter the official self-test to report success.

The private judging environment must provide the endpoint key, organization,
OAuth refresh token, client ID and client secret as documented in `.env.example`.
The published endpoint URL is included as a non-secret configuration default.
No credentials or local `.env` are included in the submission archive.

## Demonstration

1. Show **QuickML - verified this run** after a successful cloud forecast.
2. Inspect the 24-hour demand chart, dispatch timeline and critical overloads.
3. Explain storage for demand **>160 kW OR hours 18 through 22 inclusive**;
   overload at **>=200 kW**, independently.
4. Edit telemetry or upload the provided 24-row template and run another forecast.
5. Export the dispatch CSV. Explain that battery SOC and switching are simulated;
   no electrical hardware is controlled.

Each full forecast makes 24 single-record predictions. Parallelism changes
latency, not the count or inference source. Background job polling prevents a
long forecast from occupying one AppSail HTTP request beyond its platform limit.
Jobs are in memory in the current instance; an instance restart discards them.
