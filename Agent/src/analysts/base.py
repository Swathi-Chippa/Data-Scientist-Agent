"""
Base Analyst & Analyst Registry (§B3, §B10).
Defines typed contracts for all statistical and ML analysis modules.
Free-form model code execution is prohibited; all analyses are registered deterministic functions.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class AnalystOutput(BaseModel):
    analyst_name: str
    status: str  # "success", "insufficient_evidence", "failed"
    verdict: str
    summary: str
    metrics: Dict[str, Any] = Field(default_factory=dict)
    tables: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)
    assumptions: List[str] = Field(default_factory=list)
    caveats: List[str] = Field(default_factory=list)
    evidence_claims: List[Dict[str, Any]] = Field(default_factory=list)


class BaseAnalyst(ABC):
    """Abstract base class for all analytical modules."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def run(self, context: Dict[str, Any]) -> AnalystOutput:
        """Executes analytical contract against typed inputs."""
        pass


class AnalystRegistry:
    """Registry maintaining approved and validated Analyst modules."""

    def __init__(self):
        self._analysts: Dict[str, BaseAnalyst] = {}

    def register(self, analyst: BaseAnalyst):
        self._analysts[analyst.name] = analyst

    def get(self, name: str) -> Optional[BaseAnalyst]:
        return self._analysts.get(name)

    def list_registered(self) -> List[str]:
        return list(self._analysts.keys())
