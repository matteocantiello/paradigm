"""REST endpoints for runtime settings (config sections)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.api.middleware.auth import verify_api_key
from backend.api.models.settings import (
    AllSettings,
    CitationSettings,
    CitationSettingsUpdate,
    KnowledgeSettings,
    KnowledgeSettingsUpdate,
    LiteratureSettings,
    LiteratureSettingsUpdate,
    MemorySettings,
    MemorySettingsUpdate,
    OrchestratorSettings,
    OrchestratorSettingsUpdate,
    SandboxSettings,
    SandboxSettingsUpdate,
)

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

# Mapping: section name -> (config attribute name, read model, update model)
_SECTION_DISPATCH: dict[str, tuple[str, type[BaseModel], type[BaseModel]]] = {
    "orchestrator": ("orchestrator", OrchestratorSettings, OrchestratorSettingsUpdate),
    "sandbox": ("sandbox", SandboxSettings, SandboxSettingsUpdate),
    "literature": ("literature", LiteratureSettings, LiteratureSettingsUpdate),
    "knowledge": ("knowledge", KnowledgeSettings, KnowledgeSettingsUpdate),
    "memory": ("memory", MemorySettings, MemorySettingsUpdate),
    "citation": ("citation", CitationSettings, CitationSettingsUpdate),
}


def _read_section(config: Any, attr_name: str, read_model: type[BaseModel]) -> BaseModel:
    """Read a config section into its response model, picking only curated fields."""
    section_obj = getattr(config, attr_name, None)
    if section_obj is None:
        return read_model()  # defaults
    fields = read_model.model_fields
    data = {}
    for field_name in fields:
        if hasattr(section_obj, field_name):
            data[field_name] = getattr(section_obj, field_name)
    return read_model(**data)


def _read_all(config: Any) -> AllSettings:
    """Build the full AllSettings response from the live config."""
    sections: dict[str, BaseModel] = {}
    for section_name, (attr_name, read_model, _) in _SECTION_DISPATCH.items():
        if hasattr(config, attr_name):
            sections[section_name] = _read_section(config, attr_name, read_model)
    return AllSettings(**sections)


@router.get(
    "",
    response_model=AllSettings,
    dependencies=[Depends(verify_api_key)],
)
async def get_settings(request: Request) -> AllSettings:
    """Return all settings sections with current values."""
    config = request.app.state.config
    if config is None:
        raise HTTPException(status_code=503, detail="Configuration not available")
    return _read_all(config)


@router.put(
    "/{section}",
    response_model=AllSettings,
    dependencies=[Depends(verify_api_key)],
)
async def update_settings(section: str, request: Request) -> AllSettings:
    """Update a single settings section. Returns the full updated settings."""
    config = request.app.state.config
    if config is None:
        raise HTTPException(status_code=503, detail="Configuration not available")

    if section not in _SECTION_DISPATCH:
        raise HTTPException(status_code=404, detail=f"Unknown section: {section}")

    attr_name, _, update_model = _SECTION_DISPATCH[section]

    if not hasattr(config, attr_name):
        raise HTTPException(
            status_code=422,
            detail=f"Section '{section}' not available on current config",
        )

    # Parse request body against the update model
    body = await request.json()
    update = update_model(**body)

    # Apply non-None fields to the config sub-object
    section_obj = getattr(config, attr_name)
    for field_name, value in update.model_dump(exclude_none=True).items():
        if hasattr(section_obj, field_name):
            setattr(section_obj, field_name, value)

    return _read_all(config)
