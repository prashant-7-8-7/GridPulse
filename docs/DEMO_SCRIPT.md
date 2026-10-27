# A three-minute GridPulse demonstration

Use this sequence after the final QuickML deployment works. During local development say "local baseline" wherever the script says QuickML; do not imply a cloud connection that is not present.

## 0:00-0:30 — Problem and input

"Microgrids need to anticipate demand before deciding which source to dispatch. GridPulse accepts 24 hourly weather rows and predicts energy demand for each hour. This demonstration uses the official historical sample weather; a future run needs future weather inputs."

Show the 24 weather rows in Telemetry. Mention timestamp, temperature, humidity and irradiance. State that extra engineered features are computed identically during training and inference.

## 0:30-1:10 — Forecast and explainability

Run a forecast. Point to the actual provider badge, the load curve, peak demand and overload hours.

"Our final submission calls a published QuickML regression endpoint. The local CPU model helped us validate the workflow without using the GPU. QuickML errors stay visible rather than producing dummy predictions."

Report only the measured cloud validation score for the correct model version. The package's 12.29 kW RMSE is a local baseline result, not a QuickML or hidden-test score.

## 1:10-1:50 — Exact controller

Select a timeline hour and show its reason. Show the rule table:

- Demand above 160 kW OR 18:00-22:00 inclusive requests storage.
- Otherwise request the main grid.
- At or above 200 kW, independently raise a critical alert.

"These decisions use the raw prediction, so rounding in the chart cannot change the threshold result. The boundaries are covered by automated tests."

## 1:50-2:20 — Battery feasibility

Select a few hours to inspect simulated SOC. Reduce capacity to 100 kWh and rerun.

"The brief supplies no measured battery state, so SOC is explicitly simulated. If the requested storage load exceeds available energy, we show a shortfall. We preserve the required controller signal rather than hiding that shortage."

Restore capacity to 2,000 kWh and initial SOC to 85% after this example.

## 2:20-3:00 — Validation and delivery

Show a rejected invalid input, download a dispatch CSV, and show the official self-test output from the QuickML backend. Finish with the public Catalyst URL and source package.

"The end-to-end path is weather input, validation, published QuickML inference, exact dispatch signals, battery feasibility, and an exportable plan."

## Claims to avoid

- Do not promise a winning result, a hidden-test score, or guaranteed zero cloud cost.
- Do not call playback live telemetry or present the SOC as a measured battery value.
- Do not say there is real hardware switching, automatic weather fetching, continuous autonomous dispatch, savings optimization or production-grade fault protection; these are not implemented.
- Do not claim the local `SUCCESS` proves QuickML use or a public deployment.
