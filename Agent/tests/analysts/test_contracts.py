"""Contract and fixture tests for the FE-1 / BE-1 analyst hand-off."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from src.analysts.contracts import (
    AdvisorInputV2,
    AdvisorOutputV2,
    AnalystInputV2,
    AnalystOutputV2,
    AnomalyResultV2,
    DriverResultV2,
    RiskResultV2,
)
from src.analysts.export_schemas import export_schemas


ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "contracts" / "examples" / "analysts"


def _payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload.pop("_example") is True
    return payload


@pytest.mark.parametrize(
    ("pattern", "adapter"),
    [
        ("anomaly_*.json", TypeAdapter(AnalystOutputV2[AnomalyResultV2])),
        ("driver_*.json", TypeAdapter(AnalystOutputV2[DriverResultV2])),
        ("risk_*.json", TypeAdapter(AnalystOutputV2[RiskResultV2])),
    ],
)
def test_each_analyst_example_validates(pattern: str, adapter: TypeAdapter[Any]) -> None:
    paths = sorted(EXAMPLES.glob(pattern))
    assert paths
    for path in paths:
        adapter.validate_python(_payload(path))


def test_each_advisor_example_validates() -> None:
    paths = sorted(EXAMPLES.glob("advisor_*.json"))
    assert {p.stem for p in paths} == {"advisor_ok", "advisor_information_gathering"}
    for path in paths:
        AdvisorOutputV2.model_validate(_payload(path))


def test_contract_support_models_validate() -> None:
    table_ref = {
        "query_id": "Q1",
        "columns": [{"name": "period", "type": "date", "role": "time"}],
        "row_count": 3,
        "uri": "parquet://inputs/series.parquet",
    }
    AnalystInputV2.model_validate({"module": "anomaly", "params": {}, "tables": {"series": table_ref}, "run_id": "R1", "seed": 7})
    AdvisorInputV2.model_validate({"options": [], "constraints": {"max_options": 3}})


def test_schemas_export_without_error(tmp_path: Path) -> None:
    paths = export_schemas(tmp_path)
    assert len(paths) == 9
    expected_titles = {
        "table_ref": "TableRef",
        "analyst_input": "AnalystInput",
        "analyst_output": "AnalystOutput",
        "anomaly_result": "AnomalyResult",
        "dq_result": "DQResult",
        "driver_result": "DriverResult",
        "risk_result": "RiskResult",
        "advisor_input": "AdvisorInput",
        "advisor_output": "AdvisorOutput",
    }
    for stem, title in expected_titles.items():
        schema = json.loads((tmp_path / f"{stem}.schema.json").read_text(encoding="utf-8"))
        assert schema["title"] == title


def test_deliberately_broken_example_fails_validation() -> None:
    broken = _payload(EXAMPLES / "anomaly_unusual.json")
    del broken["result"]["expected"]
    with pytest.raises(ValidationError):
        TypeAdapter(AnalystOutputV2[AnomalyResultV2]).validate_python(broken)
