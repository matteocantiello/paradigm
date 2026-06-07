"""REST endpoint for the agent model picker's catalog (curated + live refresh)."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Depends, Request

from backend.api.middleware.auth import verify_api_key
from backend.api.models.agents import (
    ModelCatalogResponse,
    ModelOption,
    ProviderModels,
)

router = APIRouter(prefix="/api/v1/models", tags=["models"])

# Fallback provider set when the loaded config has no provider registry (e.g. the
# backend's degraded config). Keys mirror configs/production.yaml.
_DEFAULT_PROVIDERS = [
    ("anthropic", "anthropic", "ANTHROPIC_API_KEY", None),
    (
        "gemini",
        "openai_compatible",
        "GEMINI_API_KEY",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    ),
    ("together", "openai_compatible", "TOGETHER_API_KEY", "https://api.together.xyz/v1"),
    ("openai", "openai_compatible", "OPENAI_API_KEY", "https://api.openai.com/v1"),
]


def _provider_specs(config: Any) -> list[SimpleNamespace]:
    """Uniform (name, type, base_url, api_key_env, default_model) list of providers."""
    registry = getattr(config, "providers", None) or {}
    if registry:
        specs = []
        for name, entry in registry.items():
            specs.append(
                SimpleNamespace(
                    name=name,
                    type=getattr(entry, "type", ""),
                    base_url=getattr(entry, "base_url", None),
                    api_key_env=getattr(entry, "api_key_env", None),
                    default_model=getattr(entry, "default_model", None),
                )
            )
        return specs
    return [
        SimpleNamespace(name=n, type=t, base_url=b, api_key_env=k, default_model=None)
        for (n, t, k, b) in _DEFAULT_PROVIDERS
    ]


@router.get("", response_model=ModelCatalogResponse, dependencies=[Depends(verify_api_key)])
async def list_models(request: Request, refresh: bool = False) -> ModelCatalogResponse:
    """Models the agent picker can offer, grouped by provider.

    Returns the curated shortlist per provider by default. With ``?refresh=true``,
    each provider whose API key is set is queried for its live model list (cached
    ~1h); a failed live fetch falls back to that provider's curated list.
    """
    from paradigm.agents.model_catalog import (
        FAMILY_LABELS,
        curated_models,
        fetch_live_models,
        provider_family,
    )

    config = request.app.state.config
    providers: list[ProviderModels] = []

    for spec in _provider_specs(config):
        family = provider_family(spec.type, spec.base_url)
        label = FAMILY_LABELS.get(family, spec.name)
        available = bool(os.getenv(spec.api_key_env or ""))

        models = curated_models(family)
        source = "curated"
        error = ""
        if refresh and available:
            try:
                live = fetch_live_models(
                    spec.name,
                    provider_type=spec.type,
                    base_url=spec.base_url,
                    api_key_env=spec.api_key_env,
                    force=True,
                )
                if live:
                    models, source = live, "live"
            except Exception as e:  # noqa: BLE001 — keep curated, report the reason
                error = f"Live fetch failed: {e}"

        # Make sure the provider's configured default is selectable even if it's
        # not in the curated shortlist (e.g. a flash-lite default).
        ids = {m[0] for m in models}
        if spec.default_model and spec.default_model not in ids:
            models = [(spec.default_model, spec.default_model), *models]

        providers.append(
            ProviderModels(
                name=spec.name,
                family=family,
                label=label,
                available=available,
                models=[ModelOption(id=i, label=lbl) for i, lbl in ((a, b) for a, b in models)],
                source=source,
                error=error,
            )
        )

    return ModelCatalogResponse(providers=providers)
