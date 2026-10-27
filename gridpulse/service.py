"""Dashboard orchestration; every dispatch decision uses the unrounded forecast."""
from dataclasses import asdict
import pandas as pd
from gridpulse.battery import Battery, simulate
from gridpulse.controller import transition
from gridpulse.forecasting import forecast


def run_forecast(frame, battery=None):
    settings = Battery.from_dict(battery)
    clean, values, warnings, provider = forecast(frame, hourly_window=True)
    rows = []
    for source, value in zip(clean.to_dict(orient="records"), values):
        value = float(value)
        rows.append({**source, "target_demand_kw": value, **transition(source["timestamp"], value)})
    rows = simulate(rows, settings)
    switches = []
    for index, row in enumerate(rows):
        if index == 0 or row["grid_mode"] != rows[index-1]["grid_mode"]:
            switches.append({"timestamp": row["timestamp"], "grid_mode": row["grid_mode"],
                             "grid_label": row["grid_label"], "reason": row["reason"]})
    return {"backend": provider, "rows": rows, "warnings": warnings,
            "battery_settings": asdict(settings), "transitions": switches,
            "summary": {"peak_demand_kw": float(values.max()), "average_demand_kw": float(values.mean()),
                        "total_demand_kwh": float(values.sum()),
                        "storage_hours": sum(r["grid_mode"] == "renewable_storage" for r in rows),
                        "critical_hours": sum(r["critical_overload"] for r in rows),
                        "battery_shortfall_hours": sum(r["battery_shortfall"] for r in rows),
                        "unserved_energy_kwh": sum(r["unserved_energy_kwh"] for r in rows),
                        "final_soc_pct": rows[-1]["soc_end_pct"]},
            "assumptions": ["24 one-hour intervals in local grid time; no timezone conversion.",
                            "Weather is supplied by the user; future weather is not fetched automatically.",
                            "Battery SOC and solar generation are simulated, not measured.",
                            "Dispatch signals follow the brief even if storage is insufficient; shortfall is shown separately."]}
