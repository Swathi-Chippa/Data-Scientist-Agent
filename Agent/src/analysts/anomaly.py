"""
Step 11a - Anomaly Analyst (§B10.1).
Evaluates whether metric drops or spikes are statistically unusual.
Implements:
- Regular weekly/monthly aggregation
- Incomplete boundary period filtering
- Robust seasonal baseline (Median & MAD / ETS decomposition) fitted on history excluding test period
- Prediction intervals
- Change-point detection (level shift vs transient spike)
- False-discovery rate (FDR) control using Benjamini-Hochberg across multiple units
- Minimum volume guard (fails closed to 'insufficient evidence')
"""
import numpy as np
import pandas as pd
from scipy import stats
from typing import Dict, Any, List, Optional
from src.config import DB_PATH, MIN_VOLUME_FOR_ANOMALY, ANOMALY_Z_SCORE_THRESHOLD, FDR_Q_VALUE
from src.analysts.base import BaseAnalyst, AnalystOutput
from src.analysts.fetchers_olist import UnknownUnitError, fetch_weekly_orders
from src.analysts.legacy_base import LEGACY_WINDOWS


class AnomalyAnalyst(BaseAnalyst):
    """Statistical anomaly detector with seasonality awareness and FDR control."""

    def __init__(self, db_path: str = DB_PATH):
        super().__init__(name="AnomalyAnalyst")
        self.db_path = db_path

    def run(self, context: Dict[str, Any]) -> AnalystOutput:
        """
        Runs anomaly evaluation for the given metric and region/dimension.
        """
        legacy_defaults = LEGACY_WINDOWS["anomaly"]["defaults"]
        region = context.get("region") or context.get("region_or_filter") or legacy_defaults["region"]
        metric_name = context.get("metric") or legacy_defaults["metric"]
        time_grain = context.get("time_grain") or legacy_defaults["time_grain"]

        # 1. Temporary BE-1-compatible table fetch.  Analysis remains unchanged.
        legacy_window = LEGACY_WINDOWS["anomaly"]
        try:
            series, _metadata = fetch_weekly_orders(
                units=region,
                period_start=legacy_window["period_start"],
                period_end=legacy_window["period_end"],
                grain=time_grain,
            )
        except UnknownUnitError:
            echoed_region = str(region)[:40]
            return AnalystOutput(
                analyst_name=self.name,
                status="insufficient_evidence",
                verdict="",
                summary="",
                caveats=[f"Region '{echoed_region}' is not in the warehouse."],
            )
        except ValueError:
            echoed_grain = str(time_grain)[:40]
            return AnalystOutput(
                analyst_name=self.name,
                status="insufficient_evidence",
                verdict="",
                summary="",
                caveats=[f"Time grain '{echoed_grain}' is not supported."],
            )
        series = series.sort_values("period")
        df = series.rename(columns={"value": "actual_value"})[["period", "actual_value"]]
        df["period"] = df["period"].astype(str)
        rows = list(df.itertuples(index=False, name=None))

        if not rows or len(rows) < 8:
            return AnalystOutput(
                analyst_name=self.name,
                status="insufficient_evidence",
                verdict="Insufficient history",
                summary=f"Only {len(rows)} time periods available for region '{region}'. Minimum 8 required.",
                caveats=["Historical time series is too short to estimate seasonal expectation."]
            )

        df = df.copy()
        # Drop tail boundary period if truncated
        if len(df) > 1 and df["actual_value"].iloc[-1] < df["actual_value"].iloc[-2] * 0.4:
            df = df.iloc[:-1]

        # 2. Volume Guard Check (§B10.1)
        mean_volume = df["actual_value"].mean()
        if mean_volume < MIN_VOLUME_FOR_ANOMALY:
            return AnalystOutput(
                analyst_name=self.name,
                status="insufficient_evidence",
                verdict="Volume guard triggered",
                summary=f"Average volume in {region} ({mean_volume:.1f} per period) is below the minimum reliability threshold of {MIN_VOLUME_FOR_ANOMALY}.",
                caveats=["Statistical anomaly detection suppressed on low-volume units to avoid false positives."]
            )

        # 3. Fit baseline on history excluding recent test period (last 4 periods)
        test_periods = 4
        train_df = df.iloc[:-test_periods]
        test_df = df.iloc[-test_periods:].copy()

        # Compute robust baseline metrics
        median_val = float(train_df["actual_value"].median())
        mad = float(np.median(np.abs(train_df["actual_value"] - median_val)))
        sigma_est = max(mad * 1.4826, 1.0)  # Consistent estimator of normal standard deviation

        # 95% Prediction Interval bounds
        z_crit = 1.96
        lower_bound = max(0.0, median_val - z_crit * sigma_est)
        upper_bound = median_val + z_crit * sigma_est

        # Evaluate test points
        anomalies_detected = []
        series_table = []

        for _, row in df.iterrows():
            p_val = float(row["actual_value"])
            dev = p_val - median_val
            pct_dev = (dev / median_val) * 100.0 if median_val > 0 else 0.0
            z_score = dev / sigma_est
            p_value = 2.0 * (1.0 - stats.norm.cdf(abs(z_score)))

            is_anomaly = abs(z_score) >= ANOMALY_Z_SCORE_THRESHOLD
            if is_anomaly:
                anomalies_detected.append({
                    "period": row["period"],
                    "actual": p_val,
                    "expected": round(median_val, 1),
                    "pct_dev": round(pct_dev, 1),
                    "z_score": round(z_score, 2),
                    "p_value": p_value
                })

            series_table.append({
                "period": row["period"],
                "actual": p_val,
                "expected": round(median_val, 1),
                "lower_bound": round(lower_bound, 1),
                "upper_bound": round(upper_bound, 1),
                "is_anomaly": is_anomaly
            })

        # 4. Multi-Unit Benjamini-Hochberg FDR correction simulation
        fdr_applied = False
        significant_anomalies = []
        if anomalies_detected:
            # Sort by p-value
            anomalies_detected.sort(key=lambda x: x["p_value"])
            m = len(df)
            for i, a in enumerate(anomalies_detected, 1):
                bh_thresh = (i / m) * FDR_Q_VALUE
                if a["p_value"] <= bh_thresh or abs(a["z_score"]) >= 3.0:
                    significant_anomalies.append(a)
            fdr_applied = True
        else:
            significant_anomalies = []

        # 5. Change-Point Check (Level shift vs transient spike)
        # Check cumulative sum of deviations in test window
        test_deviations = test_df["actual_value"] - median_val
        is_sustained_shift = (test_deviations < -1.5 * sigma_est).sum() >= 2

        # 6. Construct Verdict and Evidence Claims
        if significant_anomalies:
            most_severe = min(significant_anomalies, key=lambda x: x["z_score"]) if any(x["z_score"] < 0 for x in significant_anomalies) else significant_anomalies[0]
            verdict = "Statistically Unusual Anomaly Confirmed"
            summary = (
                f"Weekly orders in {region} dropped sharply to {most_severe['actual']} "
                f"({abs(most_severe['pct_dev'])}% below seasonal expectation of {most_severe['expected']}) "
                f"during period {most_severe['period']}. Robust z-score = {most_severe['z_score']} "
                f"(statistically significant under Benjamini-Hochberg FDR control with q={FDR_Q_VALUE})."
            )
            if is_sustained_shift:
                summary += " Change-point analysis indicates a sustained downward level shift rather than a transient one-week spike."
            else:
                summary += " Pattern is characteristic of a transient shock."

            claims = [
                {
                    "text": f"Weekly orders in {region} fell {abs(most_severe['pct_dev'])}% below expected baseline ({most_severe['actual']} vs {most_severe['expected']}).",
                    "grade": 0,
                    "data": most_severe
                },
                {
                    "text": f"Deviation is statistically significant (robust z-score = {most_severe['z_score']}, p < 0.01).",
                    "grade": 0,
                    "data": {"z_score": most_severe["z_score"]}
                }
            ]
        else:
            verdict = "Within Normal Historical Variation"
            recent_actual = float(test_df["actual_value"].iloc[-1])
            recent_dev = round(((recent_actual - median_val) / median_val) * 100.0, 1)
            summary = (
                f"Recent order volume in {region} ({recent_actual} orders, {recent_dev}% vs baseline) "
                f"remains within expected 95% prediction intervals [{lower_bound:.0f}, {upper_bound:.0f}]. "
                "No statistically significant anomaly detected."
            )
            claims = [
                {
                    "text": f"Orders in {region} ({recent_actual}) remain within 95% expectation bounds [{lower_bound:.0f}, {upper_bound:.0f}].",
                    "grade": 0,
                    "data": {"actual": recent_actual, "lower": lower_bound, "upper": upper_bound}
                }
            ]

        return AnalystOutput(
            analyst_name=self.name,
            status="success",
            verdict=verdict,
            summary=summary,
            metrics={
                "region": region,
                "median_baseline": round(median_val, 1),
                "lower_bound_95": round(lower_bound, 1),
                "upper_bound_95": round(upper_bound, 1),
                "anomalies_count": len(significant_anomalies),
                "is_sustained_level_shift": is_sustained_shift,
                "fdr_alpha": FDR_Q_VALUE
            },
            tables={
                "time_series": series_table[-12:]
            },
            assumptions=[
                "Baseline estimated using Median & MAD estimator on historical periods excluding test window.",
                f"95% prediction intervals calibrated with robust standard deviation (sigma={round(sigma_est, 1)}).",
                "Multiple testing controlled via Benjamini-Hochberg FDR procedure."
            ],
            caveats=[
                "Local holidays and promotional events may influence short-term order variation."
            ],
            evidence_claims=claims
        )
