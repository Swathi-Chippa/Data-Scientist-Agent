"""Export the AN-1 V2 JSON Schemas used by FE-1 and BE-1."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.analysts.contracts import (
    AdvisorInputV2,
    AdvisorOutputV2,
    AnalystInputV2,
    AnalystOutputV2,
    AnomalyResultV2,
    DQResultV2,
    DriverResultV2,
    RiskResultV2,
    TableRefV2,
)


def export_schemas(output_dir: str | Path | None = None) -> list[Path]:
    root = Path(__file__).resolve().parents[2]
    destination = Path(output_dir) if output_dir else root / "contracts" / "schemas" / "analysts"
    destination.mkdir(parents=True, exist_ok=True)
    models: dict[str, Any] = {
        "table_ref": TableRefV2,
        "analyst_input": AnalystInputV2,
        "analyst_output": TypeAdapter(AnalystOutputV2[Any]),
        "anomaly_result": AnomalyResultV2,
        "dq_result": DQResultV2,
        "driver_result": DriverResultV2,
        "risk_result": RiskResultV2,
        "advisor_input": AdvisorInputV2,
        "advisor_output": AdvisorOutputV2,
    }
    written: list[Path] = []
    for name, model in models.items():
        schema = model.json_schema() if isinstance(model, TypeAdapter) else model.model_json_schema()
        path = destination / f"{name}.schema.json"
        path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)
    return written


if __name__ == "__main__":
    for schema_path in export_schemas():
        print(schema_path)
