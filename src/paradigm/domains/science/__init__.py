"""Science domain profile — academic research with arXiv/Semantic Scholar sources."""

from pathlib import Path

from paradigm.domains.base import DomainProfile, SourceProviderConfig
from paradigm.domains.registry import register_domain
from paradigm.domains.science.constants import (
    LITERATURE_INSTRUCTION,
    MODE_TEAM_ROLES,
    ROLE_LATER_ROUND_REINFORCEMENTS,
    ROLE_SEARCH_STRATEGIES,
)
from paradigm.domains.science.template import SCIENCE_TEMPLATE

_SCIENCE_PROFILE = DomainProfile(
    name="science",
    description="Academic science research with arXiv and Semantic Scholar sources",
    source_providers=[
        SourceProviderConfig(name="arxiv"),
        SourceProviderConfig(name="semantic_scholar"),
        SourceProviderConfig(name="internal_corpus"),
    ],
    document_template=SCIENCE_TEMPLATE,
    prompts_dir=Path(__file__).parent / "prompts",
    default_roles=MODE_TEAM_ROLES,
    role_search_strategies=ROLE_SEARCH_STRATEGIES,
    role_later_round_reinforcements=ROLE_LATER_ROUND_REINFORCEMENTS,
    literature_instruction=LITERATURE_INSTRUCTION,
)

register_domain(_SCIENCE_PROFILE)
