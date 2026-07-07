"""REST endpoints for runtime configuration (testing/production mode toggle)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.api.middleware.auth import verify_api_key

router = APIRouter(prefix="/api/v1/config", tags=["config"])


class ConfigModeResponse(BaseModel):
    """Current configuration mode."""

    mode: str  # "production" or "testing"
    testing_available: bool


class ModelTierInfo(BaseModel):
    """One selectable model tier (the wizard's Models toggle)."""

    id: str  # "premium" | "open"
    label: str
    description: str
    available: bool


class ModelTiersResponse(BaseModel):
    """Available per-cycle model tiers + which one the active config resembles."""

    tiers: list[ModelTierInfo]
    default: str


@router.get(
    "/tiers",
    response_model=ModelTiersResponse,
    dependencies=[Depends(verify_api_key)],
)
async def get_model_tiers(request: Request) -> ModelTiersResponse:
    """Model tiers a new cycle can choose between (premium vs open weights)."""
    from backend.api.services.model_tiers import default_tier, tier_availability

    config = getattr(request.app.state, "config", None)
    return ModelTiersResponse(
        tiers=[ModelTierInfo(**t) for t in tier_availability()],
        default=default_tier(config) if config is not None else "premium",
    )


class ConfigModeUpdate(BaseModel):
    """Request body to switch mode."""

    mode: str  # "production" or "testing"


@router.get(
    "/mode",
    response_model=ConfigModeResponse,
    dependencies=[Depends(verify_api_key)],
)
async def get_config_mode(request: Request) -> ConfigModeResponse:
    """Return the current configuration mode."""
    config = request.app.state.config
    if config is None:
        return ConfigModeResponse(mode="demo", testing_available=False)

    return ConfigModeResponse(
        mode="testing" if config.is_testing_mode else "production",
        testing_available=len(config.testing_overrides) > 0,
    )


@router.put(
    "/mode",
    response_model=ConfigModeResponse,
    dependencies=[Depends(verify_api_key)],
)
async def set_config_mode(body: ConfigModeUpdate, request: Request) -> ConfigModeResponse:
    """Switch between production and testing mode at runtime."""
    config = request.app.state.config
    if config is None:
        raise HTTPException(status_code=503, detail="Configuration not available")

    if body.mode not in ("production", "testing"):
        raise HTTPException(status_code=422, detail="mode must be 'production' or 'testing'")

    if body.mode == "testing":
        if not config.testing_overrides:
            raise HTTPException(status_code=400, detail="No testing overrides configured")
        config.apply_testing_overrides()
    else:
        config.restore_production_overrides()

    return ConfigModeResponse(
        mode="testing" if config.is_testing_mode else "production",
        testing_available=len(config.testing_overrides) > 0,
    )
