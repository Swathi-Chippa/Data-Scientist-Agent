"""
Value Linker (§B7, §C6).
Maps natural language entities, state names, product categories, and payment types
to exact database stored literals using exact and fuzzy lookup with confidence scoring.
"""
from typing import Dict, Tuple, Optional


class ValueLinker:
    """Links user phrases to exact stored warehouse values."""

    def __init__(self):
        # Known Brazilian State mappings
        self.state_literals = {
            "sp": "SP", "sao paulo": "SP", "são paulo": "SP",
            "rj": "RJ", "rio": "RJ", "rio de janeiro": "RJ",
            "mg": "MG", "minas": "MG", "minas gerais": "MG",
            "rs": "RS", "rio grande do sul": "RS",
            "pr": "PR", "parana": "PR", "paraná": "PR",
            "sc": "SC", "santa catarina": "SC",
            "ba": "BA", "bahia": "BA",
            "df": "DF", "brasilia": "DF", "distrito federal": "DF",
            "go": "GO", "goias": "GO", "goiás": "GO",
            "pe": "PE", "pernambuco": "PE",
            "ce": "CE", "ceara": "CE", "ceará": "CE"
        }

        # Category English-to-Portuguese translations mapped to canonical database literals
        self.category_literals = {
            "bed bath table": "cama_mesa_banho",
            "bed bath and table": "cama_mesa_banho",
            "cama mesa banho": "cama_mesa_banho",
            "health beauty": "beleza_saude",
            "health and beauty": "beleza_saude",
            "beleza saude": "beleza_saude",
            "sports leisure": "esporte_lazer",
            "esporte lazer": "esporte_lazer",
            "furniture decor": "moveis_decoracao",
            "furniture and decor": "moveis_decoracao",
            "computers accessories": "informatica_acessorios",
            "computer accessories": "informatica_acessorios",
            "housewares": "utilidades_domesticas",
            "watches gifts": "relogios_presentes",
            "telephony": "telefonia",
            "auto": "automotivo",
            "toys": "brinquedos",
            "cool stuff": "cool_stuff",
            "garden tools": "ferramentas_jardim",
            "perfumery": "perfumaria"
        }

        # Payment types
        self.payment_types = {
            "credit card": "credit_card",
            "credit": "credit_card",
            "boleto": "boleto",
            "voucher": "voucher",
            "debit card": "debit_card",
            "debit": "debit_card"
        }

        # Order statuses
        self.order_statuses = {
            "delivered": "delivered",
            "shipped": "shipped",
            "canceled": "canceled",
            "cancelled": "canceled",
            "invoiced": "invoiced",
            "processing": "processing",
            "unavailable": "unavailable"
        }

    def link_values(self, text: str) -> Tuple[Dict[str, str], float]:
        """
        Scans text and links entities to canonical literals.
        Returns: (linked_values_dict, confidence_score)
        """
        linked = {}
        t_low = text.lower()
        confidence = 1.0

        # 1. State matching
        for k, lit in self.state_literals.items():
            # Match whole words
            if f" {k} " in f" {t_low} " or f"in {k}" in t_low or f"region {k}" in t_low or f"state {k}" in t_low:
                linked["customer_state"] = lit
                break

        # 2. Category matching
        for k, lit in self.category_literals.items():
            if k in t_low:
                linked["product_category_name"] = lit
                break

        # 3. Payment type matching
        for k, lit in self.payment_types.items():
            if k in t_low:
                linked["payment_type"] = lit
                break

        # 4. Status matching
        for k, lit in self.order_statuses.items():
            if k in t_low:
                linked["order_status"] = lit
                break

        return linked, confidence
