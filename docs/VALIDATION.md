# Verification and remaining work

Checked on 27 October 2026 using Python 3.12 with the pinned requirements.

| Check | Result |
|---|---|
| Original supplied self-test | SUCCESS, 1,000 predictions, local backend |
| Automated correctness/integration suite | 41 tests passed |
| CLI timestamp preservation | All 1,000 sample timestamps and their order preserved |
| Predictions | Finite, nonnegative; exactly one per sample row |
| Original self-test source | Retained byte-for-byte |
| Controller | 160/200 kW boundaries and inclusive 18:00-22:00 window checked |
| Input handling | Missing values, invalid numbers, bad ranges, duplicate/unsorted/gapped windows checked |
| Battery | Reserve, efficiency, inverter limits, saturation and unmet energy checked |
| QuickML adapter | Single/batch payloads, bounded concurrency, stable row order, shared refresh cache, TLS verification, invalid responses and error redaction checked with mocks |
| Cloud failures | Propagate as errors; no dummy or local fallback |
| HTTP API | Forecast, CSV upload, background jobs and validation tested through a running local server |
| Static files | Dashboard assets served; secret/model paths return 404 |
| JavaScript | Syntax check passed |
| Browser | Layout, navigation and rule display inspected; populated dashboard unverified because the separate managed preview runtime lacked scientific Python dependencies |
| AppSail source ZIP | Flat structure checked; excludes secrets, virtual environments and local model binaries |
| AppSail Linux dependency download | Not executed here |
| Live QuickML request | 24 real QuickML predictions passed with preserved timestamps and correct dispatch/overload rules on 27 October 2026 |
| QuickML model metrics | Console V1 RMSE 8.2451 kW, MAE 6.6181 kW, R2 0.9649; evaluation split not independently verified |
| Public Catalyst deployment | Release 2026-10-27-final1 responds publicly and completed a real QuickML forecast |

Local chronological validation: 3,200 fitting rows and 800 later validation rows. Selected gradient boosting RMSE **12.2853 kW**, MAE **9.4189 kW**, R2 **0.9596**. Hour-of-day mean baseline RMSE: **48.7555 kW**. Model selection used this holdout; these are not untouched-test or QuickML results. Final local model was refit on all 4,000 supplied training rows.

`models/metrics.json` contains full local model metrics. `docs/VALIDATION.json` contains command outputs and checks. Use `python verify.py` to repeat local checks after running `train.py`. This command deliberately uses the local backend; run the official self-test again in the configured QuickML environment before submission.

For initial use, install requirements and launch with the same `.venv` Python interpreter as described in BUILD_GUIDE.md. The source package intentionally omits the serialized model; generate it with `train.py`.
