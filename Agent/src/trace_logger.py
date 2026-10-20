"""
Trace Logger for the Data Scientist Agent.
Manages in-memory structured execution traces for runtime inspection and Web UI.
Disk persistence is disabled by default to prevent on-disk folder pollution.
"""
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from src.config import TRACES_DIR, ENABLE_DISK_TRACING
from src.models.trace import PipelineRunTrace


class TraceLogger:
    """Manages in-memory execution traces and index."""

    def __init__(self, traces_dir: Optional[Path] = None, enable_disk: bool = ENABLE_DISK_TRACING):
        self.enable_disk = enable_disk
        self.traces_dir = traces_dir or TRACES_DIR
        self._traces: Dict[str, Dict[str, Any]] = {}
        self._index: List[Dict[str, Any]] = []

    def _sanitize(self, val):
        if hasattr(val, "item"):
            return val.item()
        if isinstance(val, dict):
            return {k: self._sanitize(v) for k, v in val.items()}
        if isinstance(val, (list, tuple, set)):
            return [self._sanitize(v) for v in val]
        return val

    def save_trace(self, trace: PipelineRunTrace) -> tuple[Optional[str], Optional[str]]:
        """Stores trace in-memory. Only writes to disk if enable_disk is explicitly True."""
        sanitized_data = self._sanitize(trace.model_dump())
        self._traces[trace.trace_id] = sanitized_data

        entry = {
            "trace_id": trace.trace_id,
            "timestamp": trace.timestamp,
            "question": trace.question,
            "route": trace.route_chosen,
            "status": trace.final_status,
            "duration_ms": trace.total_duration_ms,
            "json_file": None,
            "md_file": None
        }
        self._index.insert(0, entry)
        if len(self._index) > 100:
            self._index = self._index[:100]

        json_path_str = None
        md_path_str = None

        if self.enable_disk and self.traces_dir:
            try:
                self.traces_dir.mkdir(parents=True, exist_ok=True)
                safe_ts = trace.timestamp.replace(":", "-").replace(".", "-")
                base_name = f"run_{safe_ts}_{trace.trace_id[:8]}"
                json_path = self.traces_dir / f"{base_name}.json"
                md_path = self.traces_dir / f"{base_name}.md"

                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(sanitized_data, f, indent=2)

                md_content = self._render_markdown_trace(trace)
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(md_content)

                json_path_str = str(json_path)
                md_path_str = str(md_path)
                entry["json_file"] = str(json_path.name)
                entry["md_file"] = str(md_path.name)
            except Exception:
                pass

        return json_path_str, md_path_str

    def get_all_traces(self) -> List[Dict[str, Any]]:
        """Returns the in-memory index of recent traces."""
        return list(self._index)

    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a specific trace by trace_id (exact or prefix match)."""
        if trace_id in self._traces:
            return self._traces[trace_id]
        for tid, tdata in self._traces.items():
            if tid.startswith(trace_id) or trace_id.startswith(tid[:8]):
                return tdata
        return None

    def _render_markdown_trace(self, trace: PipelineRunTrace) -> str:
        lines = [
            f"# Execution Trace: {trace.trace_id}",
            f"**Timestamp:** {trace.timestamp} | **Total Duration:** {trace.total_duration_ms:.1f}ms | **Status:** `{trace.final_status}`",
            f"**Question:** \"{trace.question}\"",
            f"**Route:** `{trace.route_chosen}`",
            "",
            "---",
            "## Step-by-Step Audit Trail",
            "",
            "| Step | Component | Type | Duration | Status | Notes |",
            "|---|---|---|---|---|---|"
        ]

        for s in trace.steps:
            note_str = "<br>".join(s.notes) if s.notes else "-"
            lines.append(
                f"| {s.step_number} | **{s.step_name}** | {s.component_type} | {s.duration_ms}ms | `{s.status}` | {note_str} |"
            )

        lines.extend([
            "",
            "---",
            "## Executed SQL Queries",
            ""
        ])

        if not trace.executed_queries:
            lines.append("*No SQL queries were executed for this run.*")
        else:
            for i, q in enumerate(trace.executed_queries, 1):
                lines.extend([
                    f"### Query {i}: {q.get('source', 'Unknown')} ({q.get('timing_ms', 0)}ms, {q.get('row_count', 0)} rows)",
                    "```sql",
                    q.get("sql", "").strip(),
                    "```",
                    f"- Status: `{q.get('status', 'OK')}`",
                    f"- Scanned rows estimate: {q.get('estimated_rows', 'N/A')}",
                    ""
                ])

        lines.extend([
            "---",
            "## Quality & Safety Verification",
            f"- **Hard Safety Gates:** {'PASSED (Zero violations)' if trace.hard_safety_gates_passed else 'FAILED'}",
            f"- **Fact Checker:** {'PASSED' if trace.fact_check_passed else 'FLAGGED'}",
            f"- **Evidence Claims Generated:** {trace.evidence_claims_count}",
            f"- **Estimated Token Usage:** {trace.token_usage_estimate}",
            ""
        ])

        return "\n".join(lines)
