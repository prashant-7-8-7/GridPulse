# GridPulse presenter notes

Suggested length: about 6 minutes. Spend most of the demo on the forecast, exact rules and visible shortfalls.

## 1. GridPulse

GridPulse is a working software prototype for the supplied Smart Energy Microgrid & Demand Forecasting Engine problem. It forecasts each hour using a published QuickML endpoint and applies the exact dispatch rules. The cover is concept artwork, not a record of a physical installation. Source: supplied PROBLEM_STATEMENT.pdf. Cover artwork generated using the built-in image generation tool. Prompt: wide 16:9, campus microgrid on the right with solar panels and battery enclosure at blue hour, empty dark navy left side, no text, restrained editorial composition.

## 2. The microgrid planning problem

The challenge asks for a 24-hour view of demand and rule-based source transitions. Weather and time affect demand. A useful operator interface must expose when storage is requested and whether the simulated battery can actually supply the load. Campus microgrids are a proposed target use case, not a customer or field deployment claim. Source: supplied PROBLEM_STATEMENT.pdf, sections 1, 3 and 6.

## 3. A complete 24-hour dispatch workflow

Load a complete day of historical weather or supply a valid 24-row CSV. Validation rejects duplicate, unsorted or gapped hourly windows and uses training medians for missing numeric weather values. Shared code creates 11 numeric features. QuickML supplies one prediction per row. The controller and battery simulator turn those values into visible dispatch signals and energy shortfalls. Sources: gridpulse/schema.py, forecasting.py, service.py and battery.py.

## 4. QuickML and AppSail have clear roles

The frontend and API share one Catalyst AppSail origin. Python validates and transforms inputs, calls the published QuickML REST endpoint, then applies controller and simulation logic. Credentials stay on the server and token refresh is synchronized. The browser receives an opaque background job identifier and polls for the completed result. Jobs live in memory in a single instance and do not survive replacement or restart. Sources: app.py, gridpulse/jobs.py and gridpulse/quickml.py.

## 5. Demand regression in QuickML

The supplied QuickML console screenshot for GridPulseDemandModel V1 reports RMSE 8.2451, MAE 6.6181 and R2 0.9649. These are the console evaluation figures, not measured hidden-test results. The console split was not independently verified. R2 must not be presented as a percentage accuracy. The endpoint consumes the same weather, calendar, cyclic-hour, weekend and degree features created by the shared Python feature builder. Local chronological model evaluation is separate: gradient boosting RMSE 12.2853 kW after fitting 3,200 rows and validating on 800 later rows. Sources: user-supplied Metrics screenshot, models/metrics.json and gridpulse/schema.py.

## 6. A real forecast from the deployed app

This editable chart uses the real 24-row QuickML forecast captured from the public AppSail deployment on 27 October 2026. The inputs are supplied historical sample weather for 17 June 2015, not live sensor readings or future weather. The captured result reports backend quickml. The check verified finite nonnegative values, preserved timestamps and exact dispatch and overload logic. This demonstration does not have demand labels and does not establish accuracy. Sources: docs/live_forecast.json and docs/LIVE_VERIFICATION.json.

## 7. Exact dispatch rules, including boundaries

The storage condition is demand greater than 160 kW OR an hour in the inclusive 18 to 22 window. Exactly 160 outside the window stays on the main grid. Overload is a separate demand greater than or equal to 200 kW test. Values below are deliberately chosen boundary examples, not forecast observations. Source: supplied PROBLEM_STATEMENT.pdf, section 6, gridpulse/controller.py and ControllerTests.

## 8. A storage signal still needs enough energy

The battery curve is simulated using the real QuickML demand values. Defaults are 2,000 kWh capacity, 85 percent initial SOC, 20 percent reserve, 150 kW solar peak, 250 kW inverter limit and 95 percent charge/discharge efficiency per step. The sample reaches its reserve and reports nine hours with a simulated shortfall. The software keeps the required dispatch signal unchanged and displays unserved energy. This is planning evidence, not actual hardware performance. Sources: docs/live_forecast.json and gridpulse/battery.py.

## 9. An operator can inspect every hour

This is a screenshot of the actual public GridPulse deployment after its own live forecast completed. The UI shows QuickML verified this run, demand curves, thresholds, overloads and simulated battery outlook. A second run may differ slightly from the captured JSON demonstration. Use the live demo to edit a row, inspect an hour and export the dispatch CSV. Source: public Catalyst URL captured 27 October 2026.

## 10. Correctness checks cover the full contract

The 41 automated tests passed in the supplied runtime. They cover schema validation, controller threshold boundaries, battery constraints, inference response validation, timestamp order, safe error handling, bounded QuickML concurrency, token refresh reuse and asynchronous API behavior. Provider mock tests are not live inference. The unchanged original starter self-test passed for 1,000 rows in local mode. The separate deployed check used 24 real QuickML predictions. Sources: docs/VALIDATION.json, tests/ and docs/LIVE_VERIFICATION.json.

## 11. A lean prototype with a clear next step

The supplied training set has 4,000 rows. Local CPU training fits the available 16 GB RAM laptop and does not require the RTX GPU. The production inference path uses Catalyst QuickML. Each 24-hour forecast consumes 24 single-record endpoint calls, so quota planning matters. Potential operator benefits are easier inspection of dispatch and identification of simulated storage shortfalls, but field savings and reliability improvements have not been measured. Proposed next steps are weather-provider integration, calibrated uncertainty, operator-approved overrides and persistent job/telemetry storage. Sources: supplied datasets, source code and README.

## 12. Live demo and source code

Demo: open the Catalyst URL, load the historical weather if needed, run the forecast and wait for QuickML verified this run. Select an evening hour and explain the inclusive time rule. Show a battery shortfall, then export the dispatch CSV. Source code and the editable deck are published in the repository listed on the slide when available. Never put private endpoint credentials into the presentation or public repository.
