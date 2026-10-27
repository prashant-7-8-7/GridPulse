# QuickML and Catalyst deployment

Current release: the public AppSail app completed a real 24-hour QuickML forecast on 27 October 2026. See `LIVE_VERIFICATION.json` and `live_forecast.json` for the captured results. The instructions below support reproducing or updating the deployment.

## 1. Account and free usage

The brief mandates QuickML training and a public Catalyst app. The local Python code is free and needs no paid LLM. For cloud use, check event-provided access and your project's free allowance before training or making hundreds of inference calls.

Zoho currently documents a recurring free tier without a card for sign-up. Trial credits can have separate card requirements, and charges can apply beyond the allowance. Do not assume unlimited free QuickML training or inference. If your account cannot complete the mandated services within free/event credits, ask the organizers about the event allocation before incurring costs.

Official sources:

- Free tier: https://catalyst.zoho.com/free-tier/
- Pricing: https://catalyst.zoho.com/pricing.html
- QuickML pricing: https://catalyst.zoho.com/quickml.html
- Event onboarding from the starter: https://atmos26-catalyst-kit.onslate.in/ (the research tool could not retrieve this page; check it directly).

## 2. Prepare training data

From the project root:

```powershell
.\.venv\Scripts\python.exe prepare_quickml.py
```

| File in quickml_data/ | Intended use |
|---|---|
| `train_features_fit.csv` | First 3,200 rows for an initial QuickML model |
| `validation_features.csv` | 800 validation input rows for the console model tester, if supported |
| `validation_telemetry.csv` | Same validation rows in the original telemetry schema for `evaluate.py` |
| `validation_targets.csv` | True held-out demand, used only for scoring |
| `train_features_all.csv` | All 4,000 rows for the final QuickML refit |

Select `target_demand_kw` as the **regression target**. All other columns in these engineered training CSVs are numeric predictors. The local feature builder derives them from the four official input columns. The target must never be included in an inference request.

This uses the brief's allowance for consistent custom features. If organizers require the original CSV without additional derived columns, upload the original `train_telemetry.csv`, select its target, and set `QUICKML_FEATURE_MODE=raw` instead. Ensure the QuickML pipeline consistently processes its timestamp column. Do not mix a raw-trained endpoint with engineered requests, or vice versa.

The provided dataset has no missing weather values. Runtime imputation medians are derived only from the official training data, never from sample/hidden-test inputs. If you add missing values to your own data while designing a new validation experiment, fit the imputer only on that experiment's fitting partition.

## 3. Train and publish INSIDE QuickML

1. Sign in to your Zoho Catalyst account in the correct data center. Create/open the event project, named GridPulse if you like.
2. Open QuickML and import the initial fit CSV through the local-file data connector.
3. Create a regression ML pipeline. Use `target_demand_kw` as the target and the other engineered columns as features. If available, start with gradient boosted trees; compare with another regressor under the same validation arrangement. The local sklearn result is only a reference and is not transferred as a trained QuickML model.
4. Train the model. Use the console's diagnostics, and publish the selected model version as a custom ML endpoint.
5. Open the endpoint details/model tester. Copy the **Endpoint URL**, **endpoint key**, **org ID**, required headers, and the exact **sample request and response**. Copy these from your account rather than guessing an endpoint URL.
6. Check one validation feature row in the tester. Confirm one finite numerical demand prediction is returned.
7. After external access works, score on the 800 labelled validation rows using the command below. These are held-out only while the endpoint was trained on `train_features_fit.csv`.
8. Train/publish the final model on `train_features_all.csv`. If publishing creates a new URL/key/version, update the server configuration and repeat the single-row smoke check. After this full refit, the 800 validation rows are no longer held-out, so retain the earlier score and identify the model version it measured.

Official pipeline endpoint documentation: https://docs.catalyst.zoho.com/en/quickml/help/pipeline-endpoints/

## 4. Configure authentication privately

Copy `.env.example` to `.env` in the project root. Change:

```dotenv
FORECAST_BACKEND=quickml
QUICKML_ENDPOINT_URL=<paste your actual HTTPS endpoint URL>
QUICKML_ENDPOINT_KEY=<paste your actual endpoint key>
QUICKML_ORG_ID=<paste your actual org ID>
QUICKML_ENVIRONMENT=Development
QUICKML_FEATURE_MODE=engineered
QUICKML_ACCESS_TOKEN=<your current OAuth access token>
```

The angle-bracket values above are explanatory placeholders; replace the whole value. Do not paste secrets into the frontend or commit `.env`.

The documented external headers are `X-QUICKML-ENDPOINT-KEY`, `Authorization: Zoho-oauthtoken <access_token>`, `CATALYST-ORG`, and `Environment`. Generate credentials with the documented **QuickML.deployment.READ** scope. Use your account's regional Zoho API console and account server. A regular short-lived access token may expire before judges run the code.

For a lasting deployment, also set:

```dotenv
QUICKML_REFRESH_TOKEN=<refresh token for the required scope>
ZOHO_CLIENT_ID=<client ID>
ZOHO_CLIENT_SECRET=<client secret>
ZOHO_TOKEN_URL=https://accounts.zoho.in/oauth/v2/token
```

The last URL is for an India-region account. Use the official token URL for your actual region. The backend refreshes and caches tokens in memory, with a safety margin before expiry. If only an access token is configured, expired-token errors remain visible and no dummy/local predictions are substituted. Generating and granting OAuth credentials is an account action you must complete.

Restart the server after editing `.env`; real process environment variables take precedence over `.env` values. In Catalyst, enter these in server environment settings rather than uploading `.env`.

## 5. Match the endpoint's actual request/response

The adapter is configurable because the starter's generic `{data:[rows]}` example does not establish the shape of your actual published endpoint. The console sample is authoritative. No live endpoint was available to verify its exact shape here.

**This GridPulse endpoint's confirmed console shape: single record inside `data`:**

```dotenv
QUICKML_REQUEST_MODE=single
QUICKML_REQUEST_KEY=data
QUICKML_RESPONSE_PATH=result
```

Expected shape in that configuration:

```json
{"result":[123.4]}
```

If your actual response is `{"status":"success","data":{"result":[123.4]}}`, set `QUICKML_RESPONSE_PATH=data.result`. A response item can be a number, a numeric string, `{"prediction":...}`, or `{"target_demand_kw":...}`. Other shapes cause a clear error rather than a guessed prediction.

**Batch form, only if your endpoint documents/supports it**:

```dotenv
QUICKML_REQUEST_MODE=batch
QUICKML_REQUEST_KEY=data
QUICKML_RESPONSE_PATH=predictions
QUICKML_BATCH_SIZE=24
```

This optional form sends `{"data":[{...},{...}]}` and expects `{"predictions":[123.4,125.6]}` only if an endpoint explicitly supports it. It is not the configuration used by this project's endpoint. An unwrapped list uses an empty request key. An unwrapped response list uses an empty response path. Chunk outputs are concatenated in input order. Single mode makes one API call per row; the 1,000-row official check can therefore make 1,000 requests. Confirm account limits and endpoint support before running it. Four concurrent single-record requests reduce network latency without changing the number of calls. The final browser additionally uses background jobs to avoid a long AppSail HTTP request.

Official custom-ML input/response example: https://docs.catalyst.zoho.com/en/sdk/python/v1/quickml/execute-custom-ml-endpoint/

## 6. Make a small live check, then evaluate

```powershell
.\.venv\Scripts\python.exe quickml_smoke.py
```

This refuses to run under the local backend. Expected: `QuickML verified: ... -> ... kW`. It confirms one request works; it does not prove accuracy or complete deployment.

To score the initial fit-only endpoint (800 rows, with associated account usage):

```powershell
.\.venv\Scripts\python.exe evaluate.py --input quickml_data/validation_telemetry.csv --targets quickml_data/validation_targets.csv --output examples/quickml_validation.json
```

Do not report this as held-out accuracy if the endpoint was already trained on all 4,000 rows. Do not score the supplied unlabelled sample-test inputs as though they have known demand.

Run the dashboard in QuickML mode and verify that a successful run displays **QuickML · verified this run**. A configured badge alone does not prove access. After confirming inference allowance, run:

```powershell
.\.venv\Scripts\python.exe predict.py --input sample_test_input.csv --output predictions.csv
.\.venv\Scripts\python.exe test_eval.py
```

Record model version, split, RMSE, MAE, and time of the check for your presentation.

## 7. Bundle for AppSail

Catalyst manages the runtime, but its Python guide requires dependencies to be included with the uploaded build. A source ZIP containing requirements.txt alone is not proof of an executable cloud build. Windows `.venv` packages cannot simply be copied into a Linux runtime.

Run on your Windows laptop with internet access:

```powershell
.\.venv\Scripts\python.exe build_appsail.py --vendor
```

It creates **dist/GridPulse_AppSail.zip** with `app.py` at the ZIP root and Linux x86-64 CPython **3.11** wheels installed into the bundle. It includes only NumPy/Pandas and their dependencies for QuickML inference. It excludes the local sklearn model, `.env`, virtual environments and credentials. The command downloads free PyPI packages and may take several minutes. Run it again after changing application source.

The vendored build targets manylinux-compatible x86-64 Python 3.11 and includes wheels requiring a compatible Linux/glibc runtime. Use the **Python 3.11** managed runtime for this build. If the platform reports a native-library incompatibility, build dependencies in a Linux environment matching the selected AppSail runtime; do not upload Windows wheels. The vendoring download and remote deployment have not been executed here.

Running `build_appsail.py` without `--vendor` produces a source-only ZIP for inspection. That is not the complete cloud upload. `app-config.json` is unnecessary when providing settings through the console, according to the official console-deployment guide.

## 8. Deploy from the Catalyst console

1. In your project, open **Serverless → AppSail → Deploy from Console**.
2. Select **Catalyst-Managed Runtime**, choose Python **3.11**, and upload the vendored ZIP.
3. Startup command: `python3 -u app.py`.
4. Start with 512 MB memory, adjusting only if the platform's measured requirements justify it. This is a configuration suggestion, not a verified cloud memory benchmark.
5. The app reads `X_ZOHO_CATALYST_LISTEN_PORT`. If the console asks for a listening port, use its configured/default port consistently; do not hardcode your laptop's port in the cloud.
6. Set `HOST=0.0.0.0`, `FORECAST_BACKEND=quickml`, and the QuickML environment variables in the server settings. The QuickML environment header must refer to the model endpoint's actual Development/Production environment.
7. Deploy and open the returned app URL. Test a forecast from the UI, including an invalid upload and battery-shortage scenario.
8. Complete the platform's production/public-access setup for the URL required by the hackathon. Test access from a private/incognito browser without your own Zoho login. A developer-only URL or a login-restricted page is not a public submission.

The prototype emits planning signals only. Uploaded CSVs are processed in memory and no real electrical switching hardware is controlled.

Official references:

- Runtime versions and build dependency requirements: https://docs.catalyst.zoho.com/en/serverless/help/appsail/catalyst-managed-runtimes/key-concepts/
- Console deployment: https://docs.catalyst.zoho.com/en/serverless/help/appsail/catalyst-managed-runtimes/deploy-from-console/
- Python dependency bundling and startup example: https://docs.catalyst.zoho.com/en/serverless/help/appsail/help-guides/python/flask/

## 9. Final deliverables

Submit the public Catalyst URL plus your source ZIP/public repository. Leave `predict.py` configured to read your actual endpoint URL and stable OAuth configuration from the judging environment. Ask organizers how they inject private credentials if this is not specified; do not put secrets in a public repository just to make an evaluator work. If they require a non-secret endpoint URL in the source, include only that public URL while retaining keys/tokens in private environment settings.

Run the official self-test in the same QuickML-backed environment that will be evaluated. A `SUCCESS` obtained in local mode demonstrates interface correctness only. Keep the final published model accessible throughout judging.
