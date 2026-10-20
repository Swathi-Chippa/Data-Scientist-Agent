"""
Planted Ground Truth Generator (§C1, §C2, §C3).
Generates the evaluation ground-truth manifest containing:
1. Planted Anomalies (level shift, spike, dip) with true dates and deviations.
2. Planted Drivers (categories, carriers) with exact true share of change.
3. Confounders (spurious co-moving variables) to test causal discipline.
4. Negative Controls (ordinary weeks, promotional peaks, low-volume units) to test false-alert rate.
5. Seeded SQL Traps (fan-out joins, cancelled orders, duplicates) with known gold answers.
6. Customer Churn hold-out truth.

Writes to eval/ground_truth_manifest.json.
"""
import json
from pathlib import Path

MANIFEST_PATH = Path(__file__).resolve().parent.parent / "eval" / "ground_truth_manifest.json"


def generate_manifest():
    manifest = {
        "metadata": {
            "version": "1.0",
            "database": "brazil_ecommerce.db",
            "split": "held_out_evaluation",
            "description": "Planted ground-truth manifest for evaluating Anomaly, Driver, Risk, and SQL modules."
        },
        "anomalies": [
            {
                "id": "ANOM-01",
                "unit": "SP",
                "metric": "orders",
                "period": "2018-07-09",
                "anomaly_type": "sharp_dip",
                "true_actual": 351,
                "true_expected": 640.0,
                "true_pct_drop": -45.1,
                "is_anomaly": True,
                "notes": "Sharp mid-July drop in São Paulo order intake."
            },
            {
                "id": "ANOM-02",
                "unit": "RJ",
                "metric": "orders",
                "period": "2018-05-28",
                "anomaly_type": "sustained_level_shift",
                "true_actual": 180,
                "true_expected": 280.0,
                "true_pct_drop": -35.7,
                "is_anomaly": True,
                "notes": "Late-May transportation disruption drop in Rio."
            },
            {
                "id": "NEG-01",
                "unit": "SP",
                "metric": "orders",
                "period": "2018-04-16",
                "anomaly_type": "negative_control",
                "true_actual": 612,
                "true_expected": 625.0,
                "true_pct_drop": -2.1,
                "is_anomaly": False,
                "notes": "Standard operational week; MUST NOT trigger an anomaly alert."
            },
            {
                "id": "NEG-02",
                "unit": "MG",
                "metric": "orders",
                "period": "2018-03-12",
                "anomaly_type": "negative_control",
                "true_actual": 254,
                "true_expected": 248.0,
                "true_pct_drop": 2.4,
                "is_anomaly": False,
                "notes": "Ordinary spring week; false-positive test."
            },
            {
                "id": "NEG-03",
                "unit": "AC",
                "metric": "orders",
                "period": "2018-05-14",
                "anomaly_type": "low_volume_guard",
                "true_actual": 4,
                "true_expected": 5.0,
                "true_pct_drop": -20.0,
                "is_anomaly": False,
                "notes": "Low-volume state (Acre). Volume guard MUST return 'insufficient evidence'."
            }
        ],
        "drivers": [
            {
                "id": "DRV-01",
                "unit": "SP",
                "target_period": "2018-06",
                "baseline_period": "2018-05",
                "metric": "orders",
                "net_change": -400,
                "true_top_drivers": [
                    {"category": "relogios_presentes", "true_share": 0.160, "true_delta": -64},
                    {"category": "esporte_lazer", "true_share": 0.122, "true_delta": -49},
                    {"category": "utilidades_domesticas", "true_share": 0.067, "true_delta": -27}
                ],
                "confounder": {
                    "variable": "review_comment_message_length",
                    "co_moving": True,
                    "is_causal": False,
                    "rule": "Must be labeled correlation only, not cause."
                }
            }
        ],
        "churn_risk": {
            "observation_cutoff": "2018-03-01",
            "outcome_window_days": 90,
            "overall_one_time_buyer_prevalence": 0.970,
            "high_risk_segment": "High-Spend Single Buyers",
            "benchmark_top_20_lift_min": 1.15
        },
        "sql_invariants": [
            {
                "id": "SQL-TRAP-01",
                "title": "Cancelled order exclusion test",
                "question": "What was total revenue in 2017?",
                "trap": "Must filter order_status = 'delivered' and exclude 'canceled' orders.",
                "expected_min_val": 7000000.0,
                "expected_max_val": 7500000.0
            },
            {
                "id": "SQL-TRAP-02",
                "title": "Fan-out join trap",
                "question": "Total payments and items for order 00010242fe8c59d542453f4d5b308f07",
                "trap": "Direct join between items and payments must not artificially duplicate line item price.",
                "expected_item_count": 1,
                "expected_payment_value": 72.19
            }
        ]
    }

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Ground-truth manifest generated at: {MANIFEST_PATH}")


if __name__ == "__main__":
    generate_manifest()
