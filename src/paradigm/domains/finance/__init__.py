"""Finance domain profile — financial research with SSRN, SEC EDGAR, FRED, and Semantic Scholar."""

from pathlib import Path

from paradigm.domains.base import DomainProfile, SourceProviderConfig
from paradigm.domains.finance.constants import (
    LITERATURE_INSTRUCTION,
    MODE_TEAM_ROLES,
    ROLE_LATER_ROUND_REINFORCEMENTS,
    ROLE_SEARCH_STRATEGIES,
)
from paradigm.domains.finance.template import FINANCE_TEMPLATE
from paradigm.domains.registry import register_domain

_FINANCE_PROFILE = DomainProfile(
    name="finance",
    description="Financial research with SSRN, SEC EDGAR, FRED, and Semantic Scholar sources",
    source_providers=[
        SourceProviderConfig(name="ssrn"),
        SourceProviderConfig(name="sec_edgar"),
        SourceProviderConfig(name="fred"),
        SourceProviderConfig(name="semantic_scholar"),
        SourceProviderConfig(name="internal_corpus"),
    ],
    document_template=FINANCE_TEMPLATE,
    prompts_dir=Path(__file__).parent / "prompts",
    default_roles=MODE_TEAM_ROLES,
    role_search_strategies=ROLE_SEARCH_STRATEGIES,
    role_later_round_reinforcements=ROLE_LATER_ROUND_REINFORCEMENTS,
    literature_instruction=LITERATURE_INSTRUCTION,
    phase_active_roles={
        "ideation": ["economist", "quant", "strategist", "risk_analyst"],
        "planning": ["economist", "quant", "strategist", "risk_analyst"],
        "post_execution": ["economist", "quant", "strategist", "risk_analyst"],
    },
)

register_domain(_FINANCE_PROFILE)
