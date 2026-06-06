"""Tests for LLM provider abstraction layer."""

import os
from unittest.mock import MagicMock, patch

import pytest

from paradigm.agents.providers import (
    AnthropicProvider,
    OpenAICompatibleProvider,
    ProviderConfig,
    _llm_timeout,
    create_provider,
)
from paradigm.config import AgentOverrideConfig, Config, ProviderConfigEntry


class TestLLMTimeout:
    """Every LLM client must be bounded so a hung call can't stall the cycle."""

    def test_default_read_timeout(self, monkeypatch):
        monkeypatch.delenv("PARADIGM_LLM_TIMEOUT", raising=False)
        assert _llm_timeout().read == 180.0

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("PARADIGM_LLM_TIMEOUT", "42")
        assert _llm_timeout().read == 42.0

    def test_malformed_env_falls_back(self, monkeypatch):
        monkeypatch.setenv("PARADIGM_LLM_TIMEOUT", "not-a-number")
        assert _llm_timeout().read == 180.0

    def test_anthropic_client_gets_timeout(self, monkeypatch):
        monkeypatch.delenv("PARADIGM_LLM_TIMEOUT", raising=False)
        with patch("anthropic.Anthropic") as mock_anthropic:
            AnthropicProvider(api_key="k")
            assert mock_anthropic.call_args.kwargs.get("timeout") is not None


# ---------------------------------------------------------------------------
# AnthropicProvider tests
# ---------------------------------------------------------------------------


class TestAnthropicProvider:
    """Test AnthropicProvider wrapper."""

    def test_default_model(self):
        """Provider exposes its default model."""
        with patch("anthropic.Anthropic"):
            provider = AnthropicProvider(api_key="fake-key")
            assert provider.default_model == "claude-sonnet-4-5-20250929"

    def test_custom_default_model(self):
        """Provider accepts custom default model."""
        with patch("anthropic.Anthropic"):
            provider = AnthropicProvider(api_key="fake-key", default_model="claude-opus-4-6")
            assert provider.default_model == "claude-opus-4-6"

    def test_complete(self):
        """complete() calls client.messages.create and returns tuple."""
        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="Hello world")]
            mock_response.usage.input_tokens = 10
            mock_response.usage.output_tokens = 5
            mock_client.messages.create.return_value = mock_response
            mock_cls.return_value = mock_client

            provider = AnthropicProvider(api_key="fake-key")
            text, in_tok, out_tok = provider.complete(
                model="claude-sonnet-4-5-20250929",
                system="You are helpful.",
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=100,
                temperature=0.5,
            )

            assert text == "Hello world"
            assert in_tok == 10
            assert out_tok == 5
            mock_client.messages.create.assert_called_once_with(
                model="claude-sonnet-4-5-20250929",
                max_tokens=100,
                temperature=0.5,
                system="You are helpful.",
                messages=[{"role": "user", "content": "Hi"}],
            )

    def test_complete_forwards_extra_body(self):
        """complete() forwards per-role extra_body to the SDK (was silently dropped)."""
        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="ok")]
            mock_response.usage.input_tokens = 1
            mock_response.usage.output_tokens = 1
            mock_client.messages.create.return_value = mock_response
            mock_cls.return_value = mock_client

            provider = AnthropicProvider(api_key="fake-key")
            provider.complete(
                model="claude-sonnet-4-5-20250929",
                system="s",
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=100,
                extra_body={"thinking": {"type": "enabled", "budget_tokens": 1024}},
            )

            _, kwargs = mock_client.messages.create.call_args
            assert kwargs["extra_body"] == {"thinking": {"type": "enabled", "budget_tokens": 1024}}

    def test_complete_omits_extra_body_when_absent(self):
        """No extra_body kwarg is sent when none is supplied (keeps SDK call clean)."""
        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="ok")]
            mock_response.usage.input_tokens = 1
            mock_response.usage.output_tokens = 1
            mock_client.messages.create.return_value = mock_response
            mock_cls.return_value = mock_client

            AnthropicProvider(api_key="fake-key").complete(
                model="m", system="s", messages=[{"role": "user", "content": "Hi"}], max_tokens=10
            )
            _, kwargs = mock_client.messages.create.call_args
            assert "extra_body" not in kwargs

    def test_complete_streaming(self):
        """complete_streaming() yields chunks then final usage."""
        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()

            # Mock the stream context manager
            mock_stream = MagicMock()
            mock_stream.text_stream = iter(["Hello", " ", "world"])
            mock_final = MagicMock()
            mock_final.usage.input_tokens = 15
            mock_final.usage.output_tokens = 8
            mock_stream.get_final_message.return_value = mock_final
            mock_client.messages.stream.return_value.__enter__ = MagicMock(return_value=mock_stream)
            mock_client.messages.stream.return_value.__exit__ = MagicMock(return_value=False)
            mock_cls.return_value = mock_client

            provider = AnthropicProvider(api_key="fake-key")
            chunks = list(
                provider.complete_streaming(
                    model="claude-sonnet-4-5-20250929",
                    system="test",
                    messages=[{"role": "user", "content": "Hi"}],
                    max_tokens=100,
                )
            )

            # First 3 chunks are text, last is usage
            assert chunks[0] == ("Hello", 0, 0)
            assert chunks[1] == (" ", 0, 0)
            assert chunks[2] == ("world", 0, 0)
            assert chunks[3] == ("", 15, 8)


# ---------------------------------------------------------------------------
# OpenAICompatibleProvider tests
# ---------------------------------------------------------------------------


class TestOpenAICompatibleProvider:
    """Test OpenAICompatibleProvider wrapper."""

    def test_import_error(self):
        """Provider raises clear error when openai not installed."""
        with patch.dict("sys.modules", {"openai": None}):
            with pytest.raises(ImportError, match="openai"):
                OpenAICompatibleProvider(
                    api_key="fake",
                    base_url="https://api.together.xyz/v1",
                )

    def test_default_model(self):
        """Provider exposes its default model."""
        mock_openai_mod = MagicMock()
        with patch.dict("sys.modules", {"openai": mock_openai_mod}):
            provider = OpenAICompatibleProvider(
                api_key="fake",
                base_url="https://api.together.xyz/v1",
                default_model="deepseek-r1",
            )
            assert provider.default_model == "deepseek-r1"

    def test_complete(self):
        """complete() prepends system message and calls chat.completions.create."""
        mock_openai_mod = MagicMock()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Result"
        mock_response.usage.prompt_tokens = 20
        mock_response.usage.completion_tokens = 10
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_mod.OpenAI.return_value = mock_client

        with patch.dict("sys.modules", {"openai": mock_openai_mod}):
            provider = OpenAICompatibleProvider(
                api_key="fake",
                base_url="https://api.together.xyz/v1",
            )
            text, in_tok, out_tok = provider.complete(
                model="deepseek-r1",
                system="You are helpful.",
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=100,
            )

            assert text == "Result"
            assert in_tok == 20
            assert out_tok == 10

            # Verify system message was prepended
            call_args = mock_client.chat.completions.create.call_args
            msgs = call_args.kwargs["messages"]
            assert msgs[0] == {"role": "system", "content": "You are helpful."}
            assert msgs[1] == {"role": "user", "content": "Hi"}


# ---------------------------------------------------------------------------
# create_provider factory tests
# ---------------------------------------------------------------------------


class TestCreateProvider:
    """Test create_provider factory function."""

    def test_create_anthropic_provider(self):
        """Creates AnthropicProvider for type='anthropic'."""
        os.environ["TEST_ANTHROPIC_KEY"] = "test-key"
        try:
            with patch("anthropic.Anthropic"):
                provider = create_provider(
                    ProviderConfig(type="anthropic", api_key_env="TEST_ANTHROPIC_KEY")
                )
                assert isinstance(provider, AnthropicProvider)
        finally:
            del os.environ["TEST_ANTHROPIC_KEY"]

    def test_create_openai_compatible_provider(self):
        """Creates OpenAICompatibleProvider for type='openai_compatible'."""
        os.environ["TEST_OPENAI_KEY"] = "test-key"
        try:
            mock_openai_mod = MagicMock()
            with patch.dict("sys.modules", {"openai": mock_openai_mod}):
                provider = create_provider(
                    ProviderConfig(
                        type="openai_compatible",
                        api_key_env="TEST_OPENAI_KEY",
                        base_url="https://api.together.xyz/v1",
                    )
                )
                assert isinstance(provider, OpenAICompatibleProvider)
        finally:
            del os.environ["TEST_OPENAI_KEY"]

    def test_missing_api_key_env(self):
        """Raises ValueError when env var is not set."""
        # Make sure env var doesn't exist
        os.environ.pop("NONEXISTENT_KEY", None)
        with pytest.raises(ValueError, match="NONEXISTENT_KEY"):
            create_provider(ProviderConfig(type="anthropic", api_key_env="NONEXISTENT_KEY"))

    def test_unknown_provider_type(self):
        """Raises ValueError for unknown provider type."""
        os.environ["TEST_KEY"] = "test"
        try:
            with pytest.raises(ValueError, match="Unknown provider type"):
                create_provider(ProviderConfig(type="unknown_backend", api_key_env="TEST_KEY"))
        finally:
            del os.environ["TEST_KEY"]

    def test_openai_compatible_requires_base_url(self):
        """openai_compatible requires base_url."""
        os.environ["TEST_KEY"] = "test"
        try:
            with pytest.raises(ValueError, match="base_url is required"):
                create_provider(ProviderConfig(type="openai_compatible", api_key_env="TEST_KEY"))
        finally:
            del os.environ["TEST_KEY"]

    def test_custom_default_model(self):
        """Provider gets custom default_model from config."""
        os.environ["TEST_KEY"] = "test"
        try:
            with patch("anthropic.Anthropic"):
                provider = create_provider(
                    ProviderConfig(
                        type="anthropic",
                        api_key_env="TEST_KEY",
                        default_model="claude-opus-4-6",
                    )
                )
                assert provider.default_model == "claude-opus-4-6"
        finally:
            del os.environ["TEST_KEY"]


# ---------------------------------------------------------------------------
# Config provider integration tests
# ---------------------------------------------------------------------------


class TestConfigProviders:
    """Test Config provider registry and helper methods."""

    @pytest.fixture(autouse=True)
    def _set_api_key(self):
        """Ensure API key is set for Config validation."""
        original = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["ANTHROPIC_API_KEY"] = "test-api-key"
        yield
        if original:
            os.environ["ANTHROPIC_API_KEY"] = original
        else:
            del os.environ["ANTHROPIC_API_KEY"]

    def test_auto_creates_anthropic_provider(self):
        """Config auto-creates anthropic provider when providers is empty."""
        config = Config()
        assert "anthropic" in config.providers
        assert config.providers["anthropic"].type == "anthropic"
        assert config.providers["anthropic"].api_key_env == "ANTHROPIC_API_KEY"

    def test_explicit_providers_preserved(self):
        """Explicit providers in config are not overwritten."""
        config = Config(
            providers={
                "anthropic": {
                    "type": "anthropic",
                    "api_key_env": "MY_CUSTOM_KEY",
                }
            }
        )
        assert config.providers["anthropic"].api_key_env == "MY_CUSTOM_KEY"

    def test_invalid_default_provider(self):
        """Raises error when default_provider not in providers."""
        with pytest.raises(ValueError, match="default_provider"):
            Config(
                agent={"default_provider": "nonexistent"},
                providers={"anthropic": {"type": "anthropic", "api_key_env": "ANTHROPIC_API_KEY"}},
            )

    def test_invalid_override_provider(self):
        """Raises error when override references unknown provider."""
        with pytest.raises(ValueError, match="role 'skeptic'"):
            Config(
                agent={
                    "overrides": {
                        "skeptic": {"provider": "nonexistent"},
                    },
                },
                providers={"anthropic": {"type": "anthropic", "api_key_env": "ANTHROPIC_API_KEY"}},
            )

    def test_get_provider(self):
        """get_provider() returns a provider instance."""
        config = Config()
        with patch("anthropic.Anthropic"):
            provider = config.get_provider("anthropic")
            assert isinstance(provider, AnthropicProvider)

    def test_get_provider_default(self):
        """get_provider() without name uses default_provider."""
        config = Config()
        with patch("anthropic.Anthropic"):
            provider = config.get_provider()
            assert isinstance(provider, AnthropicProvider)

    def test_get_provider_unknown(self):
        """get_provider() raises for unknown name."""
        config = Config()
        with pytest.raises(ValueError, match="not found"):
            config.get_provider("nonexistent")

    def test_get_provider_and_model_for_role_default(self):
        """Default role gets default provider + model."""
        config = Config()
        with patch("anthropic.Anthropic"):
            provider, model, extra_body = config.get_provider_and_model_for_role("theorist")
            assert isinstance(provider, AnthropicProvider)
            assert model == config.agent.default_model
            assert extra_body is None

    def test_get_provider_and_model_for_role_override_model(self):
        """Role override can specify just the model."""
        config = Config(
            agent={
                "overrides": {
                    "skeptic": {"model": "claude-opus-4-6"},
                },
            },
        )
        with patch("anthropic.Anthropic"):
            provider, model, extra_body = config.get_provider_and_model_for_role("skeptic")
            assert model == "claude-opus-4-6"
            assert extra_body is None

    def test_get_provider_and_model_for_role_override_provider(self):
        """Role override can specify a different provider."""
        os.environ["TOGETHER_API_KEY"] = "fake-together-key"
        try:
            config = Config(
                providers={
                    "anthropic": {"type": "anthropic", "api_key_env": "ANTHROPIC_API_KEY"},
                    "together": {
                        "type": "openai_compatible",
                        "api_key_env": "TOGETHER_API_KEY",
                        "base_url": "https://api.together.xyz/v1",
                        "default_model": "deepseek-r1",
                    },
                },
                agent={
                    "overrides": {
                        "skeptic": {"provider": "together", "model": "deepseek-r1"},
                    },
                },
            )
            mock_openai_mod = MagicMock()
            with patch.dict("sys.modules", {"openai": mock_openai_mod}):
                provider, model, extra_body = config.get_provider_and_model_for_role("skeptic")
                assert isinstance(provider, OpenAICompatibleProvider)
                assert model == "deepseek-r1"
                assert extra_body is None
        finally:
            del os.environ["TOGETHER_API_KEY"]

    def test_provider_config_from_yaml(self):
        """ProviderConfigEntry model validates correctly."""
        entry = ProviderConfigEntry(
            type="openai_compatible",
            api_key_env="MY_KEY",
            base_url="https://example.com/v1",
            default_model="my-model",
        )
        assert entry.type == "openai_compatible"
        assert entry.base_url == "https://example.com/v1"

    def test_agent_override_config(self):
        """AgentOverrideConfig model validates correctly."""
        override = AgentOverrideConfig(provider="together", model="deepseek-r1")
        assert override.provider == "together"
        assert override.model == "deepseek-r1"

    def test_agent_override_config_partial(self):
        """AgentOverrideConfig allows partial specification."""
        override = AgentOverrideConfig(model="claude-opus-4-6")
        assert override.provider is None
        assert override.model == "claude-opus-4-6"


# ---------------------------------------------------------------------------
# Testing overrides tests
# ---------------------------------------------------------------------------


class TestTestingOverrides:
    """Test Config.testing_overrides field and apply_testing_overrides()."""

    @pytest.fixture(autouse=True)
    def _set_api_keys(self):
        """Ensure API keys are set for Config validation."""
        original_anthropic = os.environ.get("ANTHROPIC_API_KEY")
        original_together = os.environ.get("TOGETHER_API_KEY")
        os.environ["ANTHROPIC_API_KEY"] = "test-api-key"
        os.environ["TOGETHER_API_KEY"] = "test-together-key"
        yield
        if original_anthropic:
            os.environ["ANTHROPIC_API_KEY"] = original_anthropic
        else:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        if original_together:
            os.environ["TOGETHER_API_KEY"] = original_together
        else:
            os.environ.pop("TOGETHER_API_KEY", None)

    def _make_config(self, **kwargs) -> Config:
        """Build a Config with both providers pre-registered."""
        defaults = dict(
            providers={
                "anthropic": {"type": "anthropic", "api_key_env": "ANTHROPIC_API_KEY"},
                "together": {
                    "type": "openai_compatible",
                    "api_key_env": "TOGETHER_API_KEY",
                    "base_url": "https://api.together.xyz/v1",
                    "default_model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
                },
            },
            agent={
                "default_provider": "together",
                "overrides": {
                    "theorist": {"provider": "anthropic", "model": "claude-opus-4-6"},
                },
            },
        )
        defaults.update(kwargs)
        return Config(**defaults)

    def test_testing_overrides_parsed_from_dict(self):
        """testing_overrides are parsed into AgentOverrideConfig objects."""
        config = self._make_config(
            testing_overrides={
                "theorist": {"provider": "together", "model": "deepseek-ai/DeepSeek-V3.1"},
            }
        )
        assert "theorist" in config.testing_overrides
        assert config.testing_overrides["theorist"].provider == "together"
        assert config.testing_overrides["theorist"].model == "deepseek-ai/DeepSeek-V3.1"

    def test_testing_overrides_default_empty(self):
        """testing_overrides defaults to empty dict."""
        config = self._make_config()
        assert config.testing_overrides == {}

    def test_apply_testing_overrides_merges(self):
        """apply_testing_overrides() merges into agent.overrides."""
        config = self._make_config(
            testing_overrides={
                "theorist": {"provider": "together", "model": "deepseek-ai/DeepSeek-V3.1"},
            }
        )
        # Before applying: theorist uses anthropic/opus
        assert config.agent.overrides["theorist"].provider == "anthropic"
        assert config.agent.overrides["theorist"].model == "claude-opus-4-6"

        config.apply_testing_overrides()

        # After applying: theorist uses together/deepseek
        assert config.agent.overrides["theorist"].provider == "together"
        assert config.agent.overrides["theorist"].model == "deepseek-ai/DeepSeek-V3.1"

    def test_apply_testing_overrides_adds_new_roles(self):
        """apply_testing_overrides() can add overrides for roles that had none."""
        config = self._make_config(
            testing_overrides={
                "writer": {"provider": "together", "model": "some-model"},
            }
        )
        assert "writer" not in config.agent.overrides

        config.apply_testing_overrides()

        assert "writer" in config.agent.overrides
        assert config.agent.overrides["writer"].provider == "together"

    def test_theorist_resolves_to_together_after_testing_overrides(self):
        """After applying testing overrides, theorist resolves to Together provider."""
        config = self._make_config(
            testing_overrides={
                "theorist": {"provider": "together", "model": "deepseek-ai/DeepSeek-V3.1"},
            }
        )
        config.apply_testing_overrides()

        mock_openai_mod = MagicMock()
        with patch.dict("sys.modules", {"openai": mock_openai_mod}):
            provider, model, extra_body = config.get_provider_and_model_for_role("theorist")
            assert isinstance(provider, OpenAICompatibleProvider)
            assert model == "deepseek-ai/DeepSeek-V3.1"

    def test_invalid_provider_in_testing_overrides(self):
        """Validation catches invalid provider names in testing_overrides."""
        with pytest.raises(ValueError, match="Testing override for role 'theorist'"):
            self._make_config(
                testing_overrides={
                    "theorist": {"provider": "nonexistent", "model": "some-model"},
                }
            )
