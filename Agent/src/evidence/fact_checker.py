"""
Step 14 - Fact Checker (§B11, §B12, §E5).
Enforces faithfulness and causal discipline:
1. Verifies that numbers appearing in the narrative originate in the Evidence Ledger.
2. Blocks unauthorized causal language ('caused', 'because of', 'due to') unless Grade 4 boundary limits are attached.
"""
import re
from typing import Tuple, List, Set, Dict, Any
from src.models.schemas import EvidenceLedger, EvidenceClaim


class FactChecker:
    """Verifies numeric faithfulness and causal wording boundaries."""

    DISALLOWED_CAUSAL_WORDS = [
        r"\bcaused\b",
        r"\bbecause\s+of\b",
        r"\bdue\s+to\b",
        r"\bproves\s+that\b",
        r"\bdefinitive\s+cause\b"
    ]

    def verify(
        self,
        narrative: str,
        ledger: EvidenceLedger,
        has_causal_boundary_attached: bool
    ) -> Tuple[bool, str, List[str]]:
        """
        Validates narrative against the ledger and causal rules.
        Returns: (passed: bool, cleaned_narrative: str, violations: List[str])
        """
        violations = []
        cleaned_narrative = narrative

        # 1. Causal Language Boundary Check (§B11)
        # Unauthorized causal claims are forbidden unless Grade 4 is present with causal boundary disclaimer
        has_grade_4 = any(c.evidence_grade == 4 for c in ledger.claims)

        for pattern in self.DISALLOWED_CAUSAL_WORDS:
            matches = list(re.finditer(pattern, cleaned_narrative, re.IGNORECASE))
            if matches:
                if not (has_grade_4 and has_causal_boundary_attached):
                    for m in matches:
                        violations.append(
                            f"Causal Discipline Violation: Unauthorized causal claim '{m.group(0)}' detected without Grade 4 boundary attachment."
                        )
                    # Replace unauthorized causal claims with association phrases
                    cleaned_narrative = re.sub(r"\bcaused\b", "was associated with", cleaned_narrative, flags=re.IGNORECASE)
                    cleaned_narrative = re.sub(r"\bbecause\s+of\b", "co-occurring with", cleaned_narrative, flags=re.IGNORECASE)
                    cleaned_narrative = re.sub(r"\bdue\s+to\b", "in conjunction with", cleaned_narrative, flags=re.IGNORECASE)

        # 2. Number verification
        # Extract figures from narrative (percentages, floats, ints > 10)
        narrative_numbers = self._extract_numbers(cleaned_narrative)
        ledger_numbers = set()

        for claim in ledger.claims:
            for num in self._extract_numbers(claim.text):
                ledger_numbers.add(num)
            # Add numbers from data dictionary
            self._extract_data_numbers(claim.data_points, ledger_numbers)

        # Allow standard operational metadata numbers (e.g. 2018, 2017, 95%, 90 days, ranks 1, 2, 3)
        exempt_numbers = {"1", "2", "3", "4", "5", "10", "20", "90", "95", "100", "2016", "2017", "2018", "0"}

        unverified_numbers = []
        for n in narrative_numbers:
            if n not in ledger_numbers and n not in exempt_numbers:
                # Check for small rounding differences (e.g. 21.4 vs 21.41)
                if not any(abs(float(n) - float(ln)) < 0.5 for ln in ledger_numbers if self._is_float(ln) and self._is_float(n)):
                    unverified_numbers.append(n)

        if unverified_numbers:
            violations.append(
                f"Numeric Faithfulness Warning: Number(s) {unverified_numbers[:3]} in text could not be directly matched to Evidence Ledger."
            )

        passed = len(violations) == 0

        return passed, cleaned_narrative, violations

    def _extract_numbers(self, text: str) -> Set[str]:
        # Matches integers and decimals
        raw = re.findall(r"\b\d+(?:\.\d+)?\b", text)
        return set(raw)

    def _extract_data_numbers(self, data: Dict[str, Any], number_set: Set[str]):
        for v in data.values():
            if isinstance(v, (int, float)):
                number_set.add(str(v))
                number_set.add(str(int(v)))
                number_set.add(f"{v:.1f}")
                number_set.add(f"{v:.2f}")
            elif isinstance(v, dict):
                self._extract_data_numbers(v, number_set)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, (int, float)):
                        number_set.add(str(item))

    def _is_float(self, val: str) -> bool:
        try:
            float(val)
            return True
        except ValueError:
            return False
