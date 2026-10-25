"""Physics-informed IsolationForest, one model per site, in two stages.

1. Screen: the forest flags readings in the most unusual 2% of the site's
   normal score distribution (calibrated on held-out history).
2. Confirm: at least one feature must sit >= 5 sigma from the site's
   same-hour baseline, and the deviation must not be explained by cloud cover
   (power tracking measured sunlight while the sun is weak).

`perf_ratio` (reported / physics-expected power) lets the model see inflation
that raw features hide behind cloud variability. The confirm stage keeps live
false positives near zero and gives every alert a human-readable explanation.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
from sklearn.ensemble import IsolationForest
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Telemetry
from ..simulator import physics

FEATURES = ["power_ratio", "perf_ratio", "irradiance_wm2", "temperature_c",
            "ac_voltage_v", "frequency_hz", "hour_sin", "hour_cos"]
EXPLAINED = FEATURES[:6]  # hour encodings are context, not explanations
STD_FLOOR = {"power_ratio": 0.02, "perf_ratio": 0.03, "irradiance_wm2": 25.0,
             "temperature_c": 1.0, "ac_voltage_v": 1.5, "frequency_hz": 0.02}
LABELS = {"power_ratio": "power vs capacity", "perf_ratio": "power vs physics-expected",
          "irradiance_wm2": "irradiance", "temperature_c": "inverter temperature",
          "ac_voltage_v": "AC voltage", "frequency_hz": "grid frequency"}

HOLDOUT_FRACTION = 0.2
SCREEN_QUANTILE = 0.02
MIN_EXPLAINING_Z = 5.0
# Cloud cover: power tracks measured sunlight but the sun is unusually weak.
CLOUD_PERF_Z = 3.0
CLOUD_IRRADIANCE_Z = -2.0
LOW_SUN_RATIO = 0.05  # below this expected/capacity, perf_ratio uses an absolute scale


def feature_vector(r: dict, capacity_kw: float) -> list[float]:
    ts = datetime.fromisoformat(r["ts"]) if isinstance(r["ts"], str) else r["ts"]
    h = physics.hour_of_day(ts)
    expected = physics.expected_power_kw(r["irradiance_wm2"], r["ambient_temp_c"], capacity_kw)
    floor = LOW_SUN_RATIO * capacity_kw
    if expected >= floor:
        perf_ratio = r["ac_power_kw"] / expected
    else:  # dawn, dusk, night: a ratio of tiny numbers is noise, so scale the excess by the floor
        perf_ratio = 1 + (r["ac_power_kw"] - expected) / floor
    return [
        r["ac_power_kw"] / capacity_kw,
        perf_ratio,
        r["irradiance_wm2"],
        r["temperature_c"],
        r["ac_voltage_v"],
        r["frequency_hz"],
        math.sin(2 * math.pi * h / 24),
        math.cos(2 * math.pi * h / 24),
    ]


@dataclass
class SiteModel:
    forest: IsolationForest
    threshold: float
    hour_mean: np.ndarray  # [24, len(EXPLAINED)]
    hour_std: np.ndarray
    trained_on: int
    trained_at: str

    def zscores(self, x: list[float], hour: int) -> dict[str, float]:
        return {name: float((x[i] - self.hour_mean[hour, i]) / self.hour_std[hour, i])
                for i, name in enumerate(EXPLAINED)}

    def explain(self, x: list[float], hour: int) -> list[dict]:
        out = []
        for i, name in enumerate(EXPLAINED):
            mean = self.hour_mean[hour, i]
            z = (x[i] - mean) / self.hour_std[hour, i]
            out.append({
                "feature": name,
                "value": round(x[i], 3),
                "baseline": round(float(mean), 3),
                "z": round(float(z), 1),
                "text": f"{LABELS[name]} {abs(z):.1f}σ {'above' if z > 0 else 'below'} normal for {hour:02d}:00",
            })
        return sorted(out, key=lambda e: -abs(e["z"]))[:3]


class AnomalyDetector:
    def __init__(self, capacities: dict[str, float], seed: int):
        self.capacities = capacities  # device_id -> kW
        self.seed = seed
        self.models: dict[str, SiteModel] = {}

    def train(self, session: Session, site_ids: list[str], exclude: list[tuple[str, datetime, datetime]] = ()) -> dict:
        """Fit one forest per site. `exclude` = (device_id, start, end) windows of known attacks."""
        summary = {}
        for site_id in site_ids:
            rows, hours = [], []
            for t in session.scalars(select(Telemetry).where(Telemetry.site_id == site_id)):
                if any(t.device_id == d and s <= t.ts <= e for d, s, e in exclude):
                    continue
                rows.append(feature_vector(_row_dict(t), self.capacities[t.device_id]))
                hours.append(t.ts.hour)
            if len(rows) < 100:
                continue
            X, hours = np.array(rows), np.array(hours)
            idx = list(range(len(X)))
            random.Random(self.seed).shuffle(idx)
            cut = int(len(idx) * (1 - HOLDOUT_FRACTION))
            train_idx, hold_idx = idx[:cut], idx[cut:]

            forest = IsolationForest(n_estimators=100, random_state=self.seed)
            forest.fit(X[train_idx])
            threshold = float(np.quantile(forest.score_samples(X[hold_idx]), SCREEN_QUANTILE))

            n = len(EXPLAINED)
            mean, std = np.zeros((24, n)), np.ones((24, n))
            floors = np.array([STD_FLOOR[f] for f in EXPLAINED])
            for h in range(24):
                Xh = X[train_idx][hours[train_idx] == h][:, :n]
                if len(Xh):
                    mean[h], std[h] = Xh.mean(axis=0), np.maximum(Xh.std(axis=0), floors)
            self.models[site_id] = SiteModel(
                forest, threshold, mean, std, trained_on=len(train_idx),
                trained_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
            summary[site_id] = {"trained_on": len(train_idx), "holdout": len(hold_idx),
                                "threshold": round(threshold, 4)}
        return summary

    def score(self, site_id: str, readings: list[dict]) -> list[tuple[dict, float, list[dict]]]:
        """Return (reading, score, explanation) for anomalous readings only."""
        model = self.models.get(site_id)
        if model is None or not readings:
            return []
        X = [feature_vector(r, self.capacities[r["device_id"]]) for r in readings]
        scores = model.forest.score_samples(np.array(X))
        anomalies = []
        for r, x, score in zip(readings, X, scores):
            if score >= model.threshold:
                continue
            hour = datetime.fromisoformat(r["ts"]).hour
            z = model.zscores(x, hour)
            if abs(z["perf_ratio"]) < CLOUD_PERF_Z and z["irradiance_wm2"] < CLOUD_IRRADIANCE_Z:
                continue  # weather, not an attack: don't page an operator for a cloud
            explanation = model.explain(x, hour)
            if abs(explanation[0]["z"]) >= MIN_EXPLAINING_Z:
                anomalies.append((r, float(score), explanation))
        return anomalies

    def describe(self) -> dict:
        return {
            site: {"threshold": round(m.threshold, 4), "trained_on": m.trained_on, "trained_at": m.trained_at,
                   "features": FEATURES}
            for site, m in self.models.items()
        }


def _row_dict(t: Telemetry) -> dict:
    return {"ts": t.ts, "device_id": t.device_id, "ac_power_kw": t.ac_power_kw,
            "irradiance_wm2": t.irradiance_wm2, "ambient_temp_c": t.ambient_temp_c,
            "temperature_c": t.temperature_c, "ac_voltage_v": t.ac_voltage_v, "frequency_hz": t.frequency_hz}
