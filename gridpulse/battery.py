"""Illustrative one-hour energy balance; no hardware or measured battery telemetry."""
from dataclasses import dataclass
import math


@dataclass
class Battery:
    capacity_kwh: float = 2000
    initial_soc_pct: float = 85
    reserve_soc_pct: float = 20
    solar_peak_kw: float = 150
    inverter_limit_kw: float = 250
    efficiency: float = .95

    @classmethod
    def from_dict(cls, values):
        if values is None:
            return cls()
        if not isinstance(values, dict) or set(values) - set(cls.__dataclass_fields__):
            raise ValueError("Battery settings contain unknown fields.")
        try:
            converted = {k: float(v) for k, v in values.items()}
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Battery settings must be numeric.") from None
        b = cls(**converted)
        if not all(math.isfinite(v) for v in converted.values()):
            raise ValueError("Battery settings must be finite.")
        if not 1 <= b.capacity_kwh <= 100000 or not 0 <= b.initial_soc_pct <= 100:
            raise ValueError("Use battery capacity 1-100000 kWh and initial SOC 0-100%.")
        if not 0 <= b.reserve_soc_pct <= b.initial_soc_pct:
            raise ValueError("Battery reserve must be between 0 and initial SOC.")
        if not 0 <= b.solar_peak_kw <= 10000 or not 1 <= b.inverter_limit_kw <= 10000 or not .5 <= b.efficiency <= 1:
            raise ValueError("Solar, inverter or efficiency settings are out of range.")
        return b


def simulate(rows, settings):
    energy = settings.capacity_kwh * settings.initial_soc_pct / 100
    reserve = settings.capacity_kwh * settings.reserve_soc_pct / 100
    out = []
    for row in rows:
        row = dict(row)
        solar = settings.solar_peak_kw * min(row["solar_irradiance_wm2"] / 1000, 1)
        before = energy
        delivered = 0.
        unmet = 0.
        if row["grid_mode"] == "renewable_storage":
            needed = max(0, row["target_demand_kw"] - solar)
            delivered = min(needed, settings.inverter_limit_kw, max(0, energy-reserve)*settings.efficiency)
            energy -= delivered / settings.efficiency  # 1-hour intervals: kW * 1h = kWh.
            unmet = max(0, needed-delivered)
            surplus = max(0, solar-row["target_demand_kw"])
        else:
            # Policy assumption: main grid supplies demand; all PV can charge storage.
            surplus = solar
        charged = min(surplus, settings.inverter_limit_kw, max(0, settings.capacity_kwh-energy)/settings.efficiency)
        energy += charged * settings.efficiency
        energy = min(settings.capacity_kwh, max(reserve, energy))
        row.update({"soc_start_pct": round(100*before/settings.capacity_kwh, 2),
                    "soc_end_pct": round(100*energy/settings.capacity_kwh, 2),
                    "solar_estimate_kw": round(solar, 3), "battery_delivered_kwh": round(delivered, 3),
                    "unserved_energy_kwh": round(unmet, 3),
                    "battery_shortfall": unmet > .001})
        out.append(row)
    return out
