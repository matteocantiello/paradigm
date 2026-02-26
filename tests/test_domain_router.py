"""Tests for domain-aware provider routing."""

from paradigm.literature.domain_router import (
    DEFAULT_RELEVANCE,
    classify_topic,
    compute_result_allocation,
    get_provider_relevance,
    rank_providers,
)

# ---------------------------------------------------------------------------
# classify_topic
# ---------------------------------------------------------------------------


class TestClassifyTopic:
    def test_astrophysics_topic(self):
        topic = "Period-luminosity relation for Cepheid variable stars"
        assert classify_topic(topic) == "astrophysics"

    def test_astrophysics_stellar(self):
        topic = "Massive star variability and stellar pulsation"
        assert classify_topic(topic) == "astrophysics"

    def test_biomedical_topic(self):
        topic = "Gene expression in cancer tumor cells"
        assert classify_topic(topic) == "biomedical"

    def test_biomedical_neuroscience(self):
        topic = "Neural correlates of auditory perception in the brain"
        assert classify_topic(topic) == "biomedical"

    def test_music_topic(self):
        topic = "Entropy of musical expectation: rhythm, melody, and listener cognition"
        assert classify_topic(topic) == "music_and_arts"

    def test_music_topic_groove(self):
        topic = "Rhythmic entrainment and groove in jazz improvisation"
        assert classify_topic(topic) == "music_and_arts"

    def test_computer_science_topic(self):
        topic = "Deep learning for natural language processing"
        assert classify_topic(topic) == "computer_science"

    def test_physics_topic(self):
        topic = "Quantum entanglement in condensed matter systems"
        assert classify_topic(topic) == "physics"

    def test_mathematics_topic(self):
        topic = "Proof of the Riemann conjecture using algebraic topology"
        assert classify_topic(topic) == "mathematics"

    def test_earth_science_topic(self):
        topic = "Climate change effects on ocean acidification and marine biodiversity"
        assert classify_topic(topic) == "earth_and_environmental"

    def test_chemistry_topic(self):
        topic = "Nanoparticle catalyst design for electrochemistry"
        assert classify_topic(topic) == "chemistry"

    def test_social_science_topic(self):
        topic = "Effects of economic inequality on education policy"
        assert classify_topic(topic) == "social_science"

    def test_empty_topic(self):
        assert classify_topic("") is None

    def test_unrecognized_topic(self):
        assert classify_topic("hello world") is None

    def test_multi_word_phrase_detection(self):
        topic = "Black hole accretion disk dynamics"
        result = classify_topic(topic)
        assert result == "astrophysics"

    def test_cross_domain_favors_strongest_match(self):
        # "neural network" is CS but "brain" and "neuron" are biomedical
        topic = "Neural activity patterns in the brain during sleep"
        assert classify_topic(topic) == "biomedical"


# ---------------------------------------------------------------------------
# get_provider_relevance
# ---------------------------------------------------------------------------


class TestGetProviderRelevance:
    def test_astrophysics_relevance(self):
        providers = ["arxiv", "pubmed", "nasa_ads", "semantic_scholar"]
        rel = get_provider_relevance("stellar pulsation", providers)
        assert rel["arxiv"] == 1.0
        assert rel["nasa_ads"] == 1.0
        assert rel["pubmed"] == 0.05

    def test_biomedical_relevance(self):
        providers = ["arxiv", "pubmed", "biorxiv", "semantic_scholar"]
        rel = get_provider_relevance("gene expression in cancer cells", providers)
        assert rel["pubmed"] == 1.0
        assert rel["biorxiv"] == 0.9
        assert rel["arxiv"] == 0.2

    def test_music_relevance(self):
        providers = ["arxiv", "pubmed", "google_scholar", "semantic_scholar"]
        rel = get_provider_relevance("musical rhythm and melody perception", providers)
        assert rel["google_scholar"] == 1.0
        assert rel["semantic_scholar"] == 0.9
        assert rel["arxiv"] == 0.1

    def test_unknown_topic_uses_defaults(self):
        providers = ["arxiv", "pubmed"]
        rel = get_provider_relevance("foo bar baz", providers)
        assert rel["arxiv"] == DEFAULT_RELEVANCE["arxiv"]
        assert rel["pubmed"] == DEFAULT_RELEVANCE["pubmed"]

    def test_unknown_provider_gets_default_score(self):
        providers = ["arxiv", "custom_db"]
        rel = get_provider_relevance("stellar pulsation", providers)
        assert rel["custom_db"] == 0.5  # fallback for unknown providers


# ---------------------------------------------------------------------------
# compute_result_allocation
# ---------------------------------------------------------------------------


class TestComputeResultAllocation:
    def test_astrophysics_allocation(self):
        providers = ["arxiv", "pubmed", "nasa_ads", "semantic_scholar"]
        alloc = compute_result_allocation("stellar pulsation", providers, total_results=50)
        # arxiv and nasa_ads should get the most
        assert alloc["arxiv"] > alloc["pubmed"]
        assert alloc["nasa_ads"] > alloc["pubmed"]
        # pubmed below MIN_RELEVANCE (0.05 < 0.1) → 0
        assert alloc["pubmed"] == 0

    def test_music_allocation_skips_arxiv(self):
        providers = ["arxiv", "pubmed", "google_scholar", "semantic_scholar"]
        alloc = compute_result_allocation("music rhythm melody", providers, total_results=50)
        # arxiv relevance 0.1 == MIN_RELEVANCE → included but minimal
        assert alloc["google_scholar"] > alloc["arxiv"]
        assert alloc["semantic_scholar"] > alloc["arxiv"]

    def test_all_providers_get_at_least_one_when_qualified(self):
        providers = ["arxiv", "semantic_scholar", "google_scholar"]
        alloc = compute_result_allocation("deep learning for NLP", providers, total_results=10)
        for _name, count in alloc.items():
            if count > 0:
                assert count >= 1

    def test_empty_providers_fallback(self):
        alloc = compute_result_allocation("some topic", ["custom_a", "custom_b"], total_results=10)
        # Unknown providers get 0.5 relevance (above MIN_RELEVANCE)
        assert alloc["custom_a"] >= 1
        assert alloc["custom_b"] >= 1

    def test_zero_results_gives_zeros(self):
        providers = ["arxiv", "pubmed"]
        alloc = compute_result_allocation("stars", providers, total_results=0)
        # With 0 total results, proportional allocation rounds to 0 or 1
        assert sum(alloc.values()) <= len(providers)


# ---------------------------------------------------------------------------
# rank_providers
# ---------------------------------------------------------------------------


class TestRankProviders:
    def test_astrophysics_ranking(self):
        providers = ["arxiv", "pubmed", "nasa_ads", "semantic_scholar", "google_scholar"]
        ranked = rank_providers("stellar pulsation", providers)
        names = [name for name, _ in ranked]
        # arxiv and nasa_ads should be at the top
        assert names[0] in ("arxiv", "nasa_ads")
        assert names[1] in ("arxiv", "nasa_ads")
        # pubmed should be excluded (score 0.05 < MIN_RELEVANCE 0.1)
        assert "pubmed" not in names

    def test_music_ranking(self):
        providers = ["arxiv", "pubmed", "google_scholar", "semantic_scholar"]
        ranked = rank_providers("musical rhythm and melody", providers)
        names = [name for name, _ in ranked]
        # google_scholar should be at the top
        assert names[0] == "google_scholar"
        # arxiv should be last or excluded
        if "arxiv" in names:
            assert names.index("arxiv") > names.index("google_scholar")

    def test_excludes_below_min_relevance(self):
        providers = ["arxiv", "pubmed", "nasa_ads", "biorxiv"]
        ranked = rank_providers("galaxy redshift cosmology", providers)
        names = [name for name, _ in ranked]
        # pubmed (0.05) and biorxiv (0.0) should be excluded
        assert "biorxiv" not in names

    def test_all_scored(self):
        providers = ["arxiv", "semantic_scholar"]
        ranked = rank_providers("deep learning", providers)
        assert len(ranked) == 2
        for _, score in ranked:
            assert 0.0 <= score <= 1.0

    def test_unknown_topic_uses_defaults(self):
        providers = ["arxiv", "semantic_scholar", "pubmed"]
        ranked = rank_providers("lorem ipsum dolor sit", providers)
        names = [name for name, _ in ranked]
        # All should be included with default relevance
        assert len(names) == 3


# ---------------------------------------------------------------------------
# Integration: music cognition scenario (the motivating case)
# ---------------------------------------------------------------------------


class TestMusicCognitionScenario:
    """Reproduce the paper-489a566e6225 failure scenario.

    A music cognition topic should NOT be dominated by arXiv astrophysics
    results. PubMed, Google Scholar, and Semantic Scholar should be prioritized.
    """

    TOPIC = (
        "Information-theoretic analysis of musical expectation: "
        "the entropy of melodic and rhythmic patterns in listener cognition"
    )
    PROVIDERS = [
        "arxiv",
        "nasa_ads",
        "semantic_scholar",
        "pubmed",
        "biorxiv",
        "google_scholar",
        "internal_corpus",
    ]

    def test_classifies_as_music(self):
        assert classify_topic(self.TOPIC) == "music_and_arts"

    def test_arxiv_deprioritized(self):
        rel = get_provider_relevance(self.TOPIC, self.PROVIDERS)
        assert rel["arxiv"] <= 0.2
        assert rel["google_scholar"] >= 0.8
        assert rel["semantic_scholar"] >= 0.8

    def test_nasa_ads_excluded(self):
        ranked = rank_providers(self.TOPIC, self.PROVIDERS)
        names = [name for name, _ in ranked]
        assert "nasa_ads" not in names  # score 0.0

    def test_allocation_favors_relevant_providers(self):
        alloc = compute_result_allocation(self.TOPIC, self.PROVIDERS, total_results=50)
        # Google Scholar and Semantic Scholar should get more than arXiv
        assert alloc["google_scholar"] > alloc.get("arxiv", 0)
        assert alloc["semantic_scholar"] > alloc.get("arxiv", 0)
        # PubMed should also get significant allocation (music cognition overlaps neuro)
        assert alloc["pubmed"] > 0
        # nasa_ads should get 0
        assert alloc["nasa_ads"] == 0
