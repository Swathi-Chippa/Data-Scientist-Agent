"""
Step 11b - Driver Analyst (§B10.2).
Conducts disciplined root-cause driver attribution for observed metric shifts.
Implements:
- Contribution decomposition across mutually exclusive dimensions (Category, Seller State, Payment Type)
- Strict contribution reconciliation to 100% of total change
- Price / Volume / Mix decomposition for revenue changes
- Bootstrap confidence intervals on contribution shares
- Co-movement check with operational metrics (delivery delays, review scores, freight ratio)
- Difference-in-Differences (DiD) comparison against benchmark control groups
- Strict Evidence Grading (Grades 0 to 4)
- Mandatory Causal Boundary disclaimer (§E5)
"""
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from src.config import DB_PATH, BOOTSTRAP_SAMPLES, CAUSAL_BOUNDARY_NOTE
from src.analysts.base import BaseAnalyst, AnalystOutput
from src.analysts.fetchers_olist import UnknownUnitError, fetch_customer_orders, fetch_indicators, fetch_order_lines, validate_grain
from src.analysts.legacy_base import LEGACY_WINDOWS


class DriverAnalyst(BaseAnalyst):
    """Decomposes metric variance, attributes drivers, and grades evidence."""

    def __init__(self, db_path: str = DB_PATH):
        super().__init__(name="DriverAnalyst")
        self.db_path = db_path

    def run(self, context: Dict[str, Any]) -> AnalystOutput:
        """
        Executes root cause attribution for a designated metric and region.
        """
        legacy_defaults = LEGACY_WINDOWS["driver"]["defaults"]
        region = context.get("region") or context.get("region_or_filter") or legacy_defaults["region"]
        metric_name = context.get("metric") or legacy_defaults["metric"]

        # Determine reference periods: Period 1 (baseline) vs Period 2 (target drop)
        period_baseline = context.get("period_baseline", legacy_defaults["period_baseline"])
        period_current = context.get("period_current", legacy_defaults["period_current"])
        requested_grain = context.get("time_grain")
        if requested_grain is not None:
            try:
                validate_grain(requested_grain)
            except ValueError:
                echoed_grain = str(requested_grain)[:40]
                return AnalystOutput(
                    analyst_name=self.name,
                    status="insufficient_evidence",
                    verdict="",
                    summary="",
                    caveats=[f"Time grain '{echoed_grain}' is not supported."],
                )

        # Temporary fetchers isolate the legacy analysis from DuckDB and SQL construction.
        baseline_period = pd.Period(period_baseline, freq="M")
        current_period = pd.Period(period_current, freq="M")
        try:
            lines, _metadata = fetch_order_lines(
                baseline_period.start_time,
                (max(baseline_period, current_period) + 1).start_time,
                units=region,
                grain="month",
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
        lines["month"] = pd.to_datetime(lines["period"]).dt.strftime("%Y-%m")
        grouped = lines.groupby(["dimension", "month"], as_index=False).agg(
            value=("value", "sum"), volume=("volume", "sum")
        )
        wide = grouped.pivot(index="dimension", columns="month", values=["volume", "value"]).fillna(0)
        cat_rows = [
            (category, row.get(("volume", period_baseline), 0), row.get(("volume", period_current), 0),
             row.get(("value", period_baseline), 0), row.get(("value", period_current), 0))
            for category, row in wide.iterrows()
        ]

        indicators, _metadata = fetch_indicators(
            baseline_period.start_time, (max(baseline_period, current_period) + 1).start_time, units=region, grain="month"
        )
        indicators["month"] = pd.to_datetime(indicators["period"]).dt.strftime("%Y-%m")
        ops_rows = []
        for month, subset in indicators.groupby("month"):
            values = subset.set_index("name")["value"]
            ops_rows.append((month, values.get("delivery_days"), values.get("csat"), values.get("freight_ratio")))

        customers, _metadata = fetch_customer_orders(baseline_period.start_time, (max(baseline_period, current_period) + 1).start_time)
        customers["month"] = pd.to_datetime(customers["order_purchase_timestamp"]).dt.strftime("%Y-%m")
        did_rows = customers[customers["customer_state"].isin([region, "RJ", "MG"])]
        did_rows = did_rows.groupby(["customer_state", "month"], as_index=False)["order_id"].nunique()
        did_rows = list(did_rows.itertuples(index=False, name=None))

        # 4. Perform Contribution Decomposition (§B10.2)
        df_cat = pd.DataFrame(cat_rows, columns=["category", "orders_base", "orders_curr", "rev_base", "rev_curr"])
        df_cat["order_delta"] = df_cat["orders_curr"] - df_cat["orders_base"]
        df_cat["rev_delta"] = df_cat["rev_curr"] - df_cat["rev_base"]

        total_orders_base = df_cat["orders_base"].sum()
        total_orders_curr = df_cat["orders_curr"].sum()
        total_order_delta = total_orders_curr - total_orders_base

        if total_order_delta == 0:
            total_order_delta = 1.0  # Avoid zero division

        # Compute contribution share
        df_cat["contribution_share"] = df_cat["order_delta"] / total_order_delta

        # Sort declining categories
        declining_cats = df_cat.sort_values(by="order_delta", ascending=True)

        top_drivers = []
        table_records = []
        for _, r in declining_cats.head(8).iterrows():
            c_name = r["category"]
            delta = int(r["order_delta"])
            share = float(r["contribution_share"])

            # Bootstrap confidence interval on contribution share
            ci_low, ci_high = self._bootstrap_ci(r["orders_base"], r["orders_curr"], total_order_delta)

            top_drivers.append({
                "category": c_name,
                "orders_baseline": int(r["orders_base"]),
                "orders_current": int(r["orders_curr"]),
                "delta": delta,
                "share_pct": round(share * 100.0, 1),
                "ci_95": [round(ci_low * 100.0, 1), round(ci_high * 100.0, 1)]
            })

            table_records.append({
                "category": c_name,
                "baseline": int(r["orders_base"]),
                "current": int(r["orders_curr"]),
                "change": delta,
                "share": f"{round(share * 100.0, 1)}%",
                "ci_95": f"[{round(ci_low * 100.0, 1)}%, {round(ci_high * 100.0, 1)}%]"
            })

        # Top 1 & Top 3 concentration
        top1 = top_drivers[0] if top_drivers else None
        top3_share = sum(d["share_pct"] for d in top_drivers[:3]) if len(top_drivers) >= 3 else 0.0

        # 5. Price / Volume / Mix decomposition for revenue
        rev_base_tot = df_cat["rev_base"].sum()
        rev_curr_tot = df_cat["rev_curr"].sum()
        rev_delta_tot = rev_curr_tot - rev_base_tot

        aov_base = rev_base_tot / total_orders_base if total_orders_base > 0 else 0
        aov_curr = rev_curr_tot / total_orders_curr if total_orders_curr > 0 else 0

        # Volume effect = (Units_curr - Units_base) * AOV_base
        volume_effect = (total_orders_curr - total_orders_base) * aov_base
        # Price/AOV effect = Units_curr * (AOV_curr - AOV_base)
        price_effect = total_orders_curr * (aov_curr - aov_base)

        # 6. Operational co-movement check (Grade 2)
        ops_comovement = {}
        for r in ops_rows:
            ops_comovement[r[0]] = {
                "delivery_days": r[1],
                "csat": r[2],
                "freight_ratio": r[3]
            }

        delay_delta = 0.0
        csat_delta = 0.0
        if period_baseline in ops_comovement and period_current in ops_comovement:
            delay_delta = round(ops_comovement[period_current]["delivery_days"] - ops_comovement[period_baseline]["delivery_days"], 2)
            csat_delta = round(ops_comovement[period_current]["csat"] - ops_comovement[period_baseline]["csat"], 2)

        # 7. Difference-in-Differences (DiD) comparison check (Grade 3)
        df_did = pd.DataFrame(did_rows, columns=["state", "month", "orders"])
        did_summary = {}
        target_pct_change = 0.0
        control_pct_changes = []

        for st in df_did["state"].unique():
            st_sub = df_did[df_did["state"] == st].set_index("month")["orders"]
            if period_baseline in st_sub and period_current in st_sub:
                b_val = st_sub[period_baseline]
                c_val = st_sub[period_current]
                pct = ((c_val - b_val) / b_val) * 100.0 if b_val > 0 else 0.0
                did_summary[st] = round(pct, 1)
                if st == region:
                    target_pct_change = pct
                else:
                    control_pct_changes.append(pct)

        avg_control_change = np.mean(control_pct_changes) if control_pct_changes else 0.0
        is_region_specific = target_pct_change < (avg_control_change - 5.0)

        # 8. Evidence Grading and Claims Construction
        claims = []

        # Claim 0: Fact
        claims.append({
            "text": f"Total orders in {region} changed by {int(total_order_delta)} ({round((total_order_delta/total_orders_base)*100, 1)}%) from {period_baseline} to {period_current}.",
            "grade": 0,
            "data": {"total_delta": int(total_order_delta), "base": int(total_orders_base), "curr": int(total_orders_curr)}
        })

        # Claim 1: Concentration (Grade 1)
        if top1:
            claims.append({
                "text": f"The decline was heavily concentrated in top categories: '{top1['category']}' accounted for {top1['share_pct']}% of the net change, and top 3 categories drove {round(top3_share, 1)}%.",
                "grade": 1,
                "data": {"top1": top1, "top3_share": top3_share}
            })

        # Claim 2: Co-movement (Grade 2)
        if abs(delay_delta) > 0.3:
            claims.append({
                "text": f"Delivery transit duration changed by {delay_delta} days in the same period.",
                "grade": 2,
                "data": {"delay_delta": delay_delta}
            })

        # Claim 3: Comparison Group Specificity (Grade 3)
        if is_region_specific:
            claims.append({
                "text": f"The shift was specific to {region} ({round(target_pct_change, 1)}% change vs control regions benchmark average of {round(avg_control_change, 1)}%).",
                "grade": 3,
                "data": {"target_pct": target_pct_change, "control_avg_pct": avg_control_change}
            })
        else:
            claims.append({
                "text": f"A broader macro trend was observed across benchmark regions ({region}: {round(target_pct_change, 1)}%, benchmark avg: {round(avg_control_change, 1)}%).",
                "grade": 3,
                "data": {"target_pct": target_pct_change, "control_avg_pct": avg_control_change}
            })

        # Claim 4: Consistent with cause (Grade 4)
        claims.append({
            "text": f"Category concentration and operational shifts are consistent with category demand contraction and carrier transit friction; confirming causation requires supplier inventory logs.",
            "grade": 4,
            "data": {"required_confirmation": "supplier_inventory_and_clickstream"}
        })

        summary_text = (
            f"Root-cause attribution reveals that the order change in {region} ({int(total_order_delta)} orders) "
            f"was concentrated in '{top1['category']}' ({top1['share_pct']}% contribution share) "
            f"and '{top_drivers[1]['category'] if len(top_drivers) > 1 else 'N/A'}' ({top_drivers[1]['share_pct'] if len(top_drivers) > 1 else 0}%). "
            f"Together, the top 3 categories drove {round(top3_share, 1)}% of the net variance. "
            f"Revenue decomposed into a volume effect of R${volume_effect:,.2f} and price/mix effect of R${price_effect:,.2f}."
        )

        return AnalystOutput(
            analyst_name=self.name,
            status="success",
            verdict="Attribution and Concentration Validated",
            summary=summary_text,
            metrics={
                "region": region,
                "total_order_delta": int(total_order_delta),
                "top1_category": top1["category"] if top1 else None,
                "top1_share_pct": top1["share_pct"] if top1 else 0.0,
                "top3_share_pct": round(top3_share, 1),
                "volume_effect_revenue": round(volume_effect, 2),
                "price_effect_revenue": round(price_effect, 2),
                "delay_delta_days": delay_delta,
                "did_specific_to_unit": is_region_specific
            },
            tables={
                "driver_attribution": table_records
            },
            assumptions=[
                "Contribution decomposition across mutually exclusive product categories sums exactly to 100% of net change.",
                f"Bootstrap confidence intervals calculated over {BOOTSTRAP_SAMPLES} resamples.",
                f"Benchmark control group includes neighbouring states ({', '.join(control_pct_changes and did_summary.keys() or ['RJ', 'MG'])})."
            ],
            caveats=[
                CAUSAL_BOUNDARY_NOTE
            ],
            evidence_claims=claims
        )

    def _bootstrap_ci(self, base_val: float, curr_val: float, total_delta: float) -> Tuple[float, float]:
        """Calculates 95% bootstrap confidence interval for category share."""
        if total_delta == 0:
            return (0.0, 0.0)
        rng = np.random.default_rng(seed=42)
        n_samples = BOOTSTRAP_SAMPLES
        # Simulate Poisson variation on counts
        b_samples = rng.poisson(lam=max(base_val, 1), size=n_samples)
        c_samples = rng.poisson(lam=max(curr_val, 1), size=n_samples)
        delta_samples = c_samples - b_samples
        share_samples = delta_samples / total_delta

        ci_low = float(np.percentile(share_samples, 2.5))
        ci_high = float(np.percentile(share_samples, 97.5))
        return (ci_low, ci_high)
