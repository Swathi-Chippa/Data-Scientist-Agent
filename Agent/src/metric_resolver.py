"""
Step 4 - Metric Resolver: Maps business terms to governed definitions.
Contract: Slots -> GovernedMetric definition or None (with caveats).
"""
from typing import Optional, Tuple
from src.models.schemas import ExtractedSlots, GovernedMetric
from src.metric_registry import METRIC_REGISTRY


class MetricResolver:
    """Consults the Metric Registry to resolve governed metrics, grains, filters, and caveats."""

    def __init__(self):
        self.registry = METRIC_REGISTRY

    def resolve(self, slots: ExtractedSlots) -> Tuple[Optional[GovernedMetric], bool, list[str]]:
        """
        Resolves metric from extracted slots.
        Returns: (metric_def: Optional[GovernedMetric], is_fully_governed: bool, caveats: list[str])
        """
        caveats = []
        target_name = slots.metric

        if not target_name:
            return None, False, ["No specific metric identified; query treated as analytical exploration."]

        # 1. Direct key match
        target_name_lower = target_name.lower().strip()
        matched_metric = self.registry.get(target_name_lower)

        # 2. Synonym match if direct lookup failed
        if not matched_metric:
            for m_key, m_def in self.registry.items():
                if target_name_lower in [s.lower() for s in m_def.synonyms]:
                    matched_metric = m_def
                    break

        if not matched_metric:
            return None, False, [f"Ungoverned metric '{target_name}'. Results are computed using analytical model generation."]

        # 3. Check dimension governance
        is_fully_governed = True
        if slots.dimension:
            dim_clean = slots.dimension.lower().strip()
            # Normalize dimension
            if dim_clean in ["category", "product_category"]:
                dim_clean = "product_category_name"
            elif dim_clean in ["state", "region"]:
                dim_clean = "customer_state"

            if dim_clean not in matched_metric.allowed_dimensions:
                is_fully_governed = False
                caveats.append(
                    f"Dimension '{slots.dimension}' is outside the pre-approved governed dimensions for metric '{matched_metric.name}'."
                )

        caveats.extend(matched_metric.caveats)
        return matched_metric, is_fully_governed, caveats
