"""Domain-aware provider routing for literature search.

Classifies research topics into academic domains and routes search
queries to the most relevant providers, preventing off-topic results
(e.g., astrophysics papers for a music cognition study).
"""

from __future__ import annotations

import logging
import re

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain keyword taxonomy
# ---------------------------------------------------------------------------

# Each domain maps to a set of keywords/phrases that indicate the topic
# belongs to that domain.  Keywords are matched case-insensitively against
# the seed prompt and individual search queries.

DOMAIN_KEYWORDS: dict[str, set[str]] = {
    "astrophysics": {
        "star",
        "stars",
        "stellar",
        "galaxy",
        "galaxies",
        "galactic",
        "nebula",
        "cosmology",
        "cosmological",
        "supernova",
        "supernovae",
        "pulsar",
        "quasar",
        "black hole",
        "neutron star",
        "white dwarf",
        "red giant",
        "main sequence",
        "hertzsprung",
        "cepheid",
        "exoplanet",
        "planet",
        "planetary",
        "asteroid",
        "comet",
        "solar",
        "helioseismology",
        "asteroseismology",
        "spectroscopy",
        "photometry",
        "redshift",
        "dark matter",
        "dark energy",
        "gravitational wave",
        "luminosity",
        "magnitude",
        "accretion",
        "interstellar",
        "intergalactic",
        "telescope",
        "observatory",
        "hubble",
        "jwst",
        "cosmic",
        "astrophysical",
        "magnetar",
        "binary star",
        "variable star",
        "variability",
        "pulsation",
        "oscillation",
        "convection",
        "nucleosynthesis",
        "metallicity",
        "isochrone",
    },
    "biomedical": {
        "gene",
        "genes",
        "genetic",
        "genomic",
        "genome",
        "protein",
        "proteomic",
        "enzyme",
        "cell",
        "cellular",
        "tissue",
        "organ",
        "disease",
        "clinical",
        "patient",
        "therapy",
        "therapeutic",
        "drug",
        "pharmaceutical",
        "pathology",
        "cancer",
        "tumor",
        "oncology",
        "neuroscience",
        "neural",
        "neuron",
        "brain",
        "cortex",
        "hippocampus",
        "fmri",
        "eeg",
        "cognitive",
        "cognition",
        "perception",
        "auditory",
        "visual",
        "sensory",
        "motor",
        "immune",
        "immunology",
        "vaccine",
        "antibody",
        "virus",
        "viral",
        "bacteria",
        "bacterial",
        "microbiome",
        "epidemiology",
        "public health",
        "biomarker",
        "diagnosis",
        "prognosis",
        "surgery",
        "cardiology",
        "cardiac",
        "respiratory",
        "metabolic",
        "metabolism",
        "hormone",
        "endocrine",
        "anatomy",
        "physiology",
        "pharmacology",
        "toxicology",
        "psychiatry",
        "psychology",
        "behavioral",
        "psychoacoustic",
    },
    "music_and_arts": {
        "music",
        "musical",
        "melody",
        "harmony",
        "rhythm",
        "rhythmic",
        "tempo",
        "pitch",
        "timbre",
        "chord",
        "tonal",
        "tonality",
        "atonal",
        "jazz",
        "classical music",
        "rock music",
        "pop music",
        "hip hop",
        "composer",
        "composition",
        "improvisation",
        "instrument",
        "instrumental",
        "vocal",
        "singing",
        "song",
        "acoustic",
        "listener",
        "listening",
        "music cognition",
        "music perception",
        "music theory",
        "musicology",
        "ethnomusicology",
        "groove",
        "syncopation",
        "entrainment",
        "beat",
        "meter",
        "sonata",
        "symphony",
        "opera",
        "concert",
        "performance",
        "performer",
        "art",
        "aesthetic",
        "aesthetics",
        "creativity",
        "artistic",
    },
    "computer_science": {
        "algorithm",
        "computational",
        "computer",
        "software",
        "hardware",
        "programming",
        "machine learning",
        "deep learning",
        "neural network",
        "artificial intelligence",
        "nlp",
        "natural language processing",
        "computer vision",
        "robotics",
        "database",
        "distributed",
        "cloud computing",
        "cybersecurity",
        "cryptography",
        "blockchain",
        "compiler",
        "operating system",
        "network",
        "networking",
        "data structure",
        "optimization",
        "reinforcement learning",
        "transformer",
        "large language model",
        "llm",
        "generative",
        "diffusion model",
        "convolutional",
        "recurrent",
        "graph neural",
        "gpu",
        "parallel computing",
        "quantum computing",
    },
    "physics": {
        "quantum",
        "quantum mechanics",
        "quantum field",
        "particle",
        "hadron",
        "lepton",
        "boson",
        "fermion",
        "condensed matter",
        "superconductor",
        "semiconductor",
        "magnetism",
        "electromagnetism",
        "optics",
        "photonics",
        "laser",
        "plasma",
        "thermodynamics",
        "statistical mechanics",
        "fluid dynamics",
        "turbulence",
        "relativity",
        "gravitation",
        "string theory",
        "nuclear",
        "accelerator",
        "collider",
        "higgs",
        "standard model",
        "lattice",
        "topological",
    },
    "mathematics": {
        "theorem",
        "proof",
        "conjecture",
        "algebra",
        "algebraic",
        "topology",
        "manifold",
        "differential equation",
        "partial differential",
        "stochastic",
        "probability",
        "combinatorics",
        "graph theory",
        "number theory",
        "prime number",
        "group theory",
        "ring theory",
        "category theory",
        "functional analysis",
        "measure theory",
        "dynamical system",
        "chaos",
        "fractal",
        "geometry",
        "geometric",
        "riemannian",
        "euclidean",
    },
    "earth_and_environmental": {
        "climate",
        "weather",
        "atmospheric",
        "ocean",
        "oceanic",
        "marine",
        "geology",
        "geological",
        "seismology",
        "earthquake",
        "volcanic",
        "tectonic",
        "sediment",
        "mineral",
        "paleontology",
        "fossil",
        "ecosystem",
        "ecology",
        "biodiversity",
        "conservation",
        "deforestation",
        "pollution",
        "greenhouse",
        "carbon",
        "ozone",
        "glacier",
        "permafrost",
        "hydrology",
        "watershed",
        "soil",
    },
    "chemistry": {
        "molecule",
        "molecular",
        "chemical",
        "reaction",
        "synthesis",
        "catalyst",
        "catalysis",
        "organic chemistry",
        "inorganic",
        "polymer",
        "electrochemistry",
        "spectral",
        "chromatography",
        "mass spectrometry",
        "nmr",
        "crystallography",
        "nanoparticle",
        "nanotechnology",
        "materials science",
        "battery",
        "fuel cell",
        "photovoltaic",
    },
    "social_science": {
        "sociology",
        "anthropology",
        "economics",
        "economic",
        "political",
        "politics",
        "policy",
        "governance",
        "democracy",
        "inequality",
        "poverty",
        "education",
        "pedagogy",
        "linguistics",
        "language",
        "communication",
        "media",
        "culture",
        "cultural",
        "society",
        "social",
        "demographic",
        "population",
        "migration",
        "urban",
        "rural",
        "ethnography",
    },
}

# ---------------------------------------------------------------------------
# Provider relevance per domain
# ---------------------------------------------------------------------------

# Score 0.0–1.0 indicating how relevant each provider is for each domain.
# Providers with score < MIN_RELEVANCE are skipped entirely.

PROVIDER_RELEVANCE: dict[str, dict[str, float]] = {
    "astrophysics": {
        "arxiv": 1.0,
        "nasa_ads": 1.0,
        "semantic_scholar": 0.8,
        "google_scholar": 0.5,
        "pubmed": 0.05,
        "biorxiv": 0.0,
        "internal_corpus": 0.8,
    },
    "biomedical": {
        "pubmed": 1.0,
        "biorxiv": 0.9,
        "semantic_scholar": 0.8,
        "google_scholar": 0.7,
        "arxiv": 0.2,
        "nasa_ads": 0.0,
        "internal_corpus": 0.8,
    },
    "music_and_arts": {
        "pubmed": 0.7,  # neuroscience of music
        "google_scholar": 1.0,
        "semantic_scholar": 0.9,
        "arxiv": 0.1,
        "biorxiv": 0.3,
        "nasa_ads": 0.0,
        "internal_corpus": 0.8,
    },
    "computer_science": {
        "arxiv": 1.0,
        "semantic_scholar": 0.9,
        "google_scholar": 0.7,
        "pubmed": 0.1,
        "biorxiv": 0.05,
        "nasa_ads": 0.1,
        "internal_corpus": 0.8,
    },
    "physics": {
        "arxiv": 1.0,
        "semantic_scholar": 0.8,
        "google_scholar": 0.6,
        "nasa_ads": 0.4,
        "pubmed": 0.05,
        "biorxiv": 0.0,
        "internal_corpus": 0.8,
    },
    "mathematics": {
        "arxiv": 1.0,
        "semantic_scholar": 0.8,
        "google_scholar": 0.6,
        "pubmed": 0.0,
        "biorxiv": 0.0,
        "nasa_ads": 0.1,
        "internal_corpus": 0.8,
    },
    "earth_and_environmental": {
        "google_scholar": 0.9,
        "semantic_scholar": 0.8,
        "pubmed": 0.5,
        "biorxiv": 0.3,
        "arxiv": 0.3,
        "nasa_ads": 0.2,
        "internal_corpus": 0.8,
    },
    "chemistry": {
        "google_scholar": 0.9,
        "semantic_scholar": 0.8,
        "pubmed": 0.6,
        "arxiv": 0.3,
        "biorxiv": 0.2,
        "nasa_ads": 0.0,
        "internal_corpus": 0.8,
    },
    "social_science": {
        "google_scholar": 1.0,
        "semantic_scholar": 0.8,
        "pubmed": 0.3,
        "arxiv": 0.1,
        "biorxiv": 0.05,
        "nasa_ads": 0.0,
        "internal_corpus": 0.8,
    },
}

# Default relevance when topic doesn't match any domain
DEFAULT_RELEVANCE: dict[str, float] = {
    "semantic_scholar": 0.9,
    "google_scholar": 0.8,
    "arxiv": 0.5,
    "pubmed": 0.4,
    "biorxiv": 0.3,
    "nasa_ads": 0.2,
    "internal_corpus": 0.8,
}

# Providers below this relevance score are skipped
MIN_RELEVANCE: float = 0.1


def classify_topic(topic: str) -> str | None:
    """Classify a research topic into an academic domain.

    Uses keyword matching against the topic string. Returns the domain
    with the highest keyword overlap, or None if no domain scores.

    Args:
        topic: The research topic or seed prompt.

    Returns:
        Domain name (e.g. "astrophysics", "biomedical") or None.
    """
    if not topic:
        return None

    topic_lower = topic.lower()
    # Tokenize for single-word matching
    topic_words = set(re.sub(r"[^a-z0-9\s]", " ", topic_lower).split())

    best_domain: str | None = None
    best_score: float = 0.0

    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = 0.0
        for kw in keywords:
            if " " in kw:
                # Multi-word phrase: check substring
                if kw in topic_lower:
                    score += 2.0  # Phrases are stronger signals
            else:
                # Single word: check word boundary
                if kw in topic_words:
                    score += 1.0

        if score > best_score:
            best_score = score
            best_domain = domain

    if best_score < 1.0:
        return None  # No meaningful match

    return best_domain


def get_provider_relevance(
    topic: str,
    available_providers: list[str],
) -> dict[str, float]:
    """Get relevance scores for each provider given a research topic.

    Args:
        topic: The research topic or seed prompt.
        available_providers: Names of providers that are registered.

    Returns:
        Dict mapping provider name to relevance score (0.0–1.0).
    """
    domain = classify_topic(topic)

    if domain and domain in PROVIDER_RELEVANCE:
        relevance_map = PROVIDER_RELEVANCE[domain]
    else:
        relevance_map = DEFAULT_RELEVANCE

    result: dict[str, float] = {}
    for name in available_providers:
        result[name] = relevance_map.get(name, 0.5)

    return result


def compute_result_allocation(
    topic: str,
    available_providers: list[str],
    total_results: int,
) -> dict[str, int]:
    """Allocate result slots to providers proportional to relevance.

    Providers below MIN_RELEVANCE get zero slots. The remaining slots
    are distributed proportionally, with each qualifying provider
    guaranteed at least 1 slot.

    Args:
        topic: The research topic or seed prompt.
        available_providers: Names of providers that are registered.
        total_results: Total number of results to distribute.

    Returns:
        Dict mapping provider name to allocated result count.
    """
    relevance = get_provider_relevance(topic, available_providers)

    # Filter out providers below threshold
    qualified = {name: score for name, score in relevance.items() if score >= MIN_RELEVANCE}

    if not qualified:
        # Fallback: give equal allocation to all providers
        per_provider = max(1, total_results // len(available_providers))
        return {name: per_provider for name in available_providers}

    total_relevance = sum(qualified.values())
    allocation: dict[str, int] = {}

    for name in available_providers:
        if name not in qualified:
            allocation[name] = 0
            continue
        # Proportional allocation with minimum of 1
        share = qualified[name] / total_relevance * total_results
        allocation[name] = max(1, round(share))

    return allocation


def rank_providers(
    topic: str,
    available_providers: list[str],
) -> list[tuple[str, float]]:
    """Rank providers by relevance to the topic.

    Args:
        topic: The research topic or seed prompt.
        available_providers: Names of providers that are registered.

    Returns:
        List of (provider_name, relevance_score) sorted by descending relevance.
        Providers below MIN_RELEVANCE are excluded.
    """
    relevance = get_provider_relevance(topic, available_providers)

    ranked = [(name, score) for name, score in relevance.items() if score >= MIN_RELEVANCE]
    ranked.sort(key=lambda x: x[1], reverse=True)

    _logger.debug(
        "Provider ranking for topic '%s': %s",
        topic[:60],
        [(name, f"{score:.2f}") for name, score in ranked],
    )

    return ranked
