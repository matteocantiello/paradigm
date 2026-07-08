"""Repository data providers (D2): search + fetch REAL datasets for the sandbox.

The real-data mandate needs an acquisition path, not just a ban: agents get
``[DATASEARCH: query]`` to find datasets in wired repositories and
``[FETCHDATA: <id>]`` to stage one into /data/shared/data with a data card —
mirroring the literature [SEARCH:]/[READ:] pattern.

v1 providers (plain httpx, endpoints verified live 2026-07-08):
- VizieR/CDS  — ``-words`` catalog search + ``asu-tsv`` table download
                (ids like ``vizier:J/A+A/701/A297``).
- Zenodo      — REST record search + first-data-file download
                (ids like ``zenodo:999271``).

Providers are configured via ``literature.data_providers`` (names), so domains
choose their repositories — the orchestrator stays domain-agnostic.
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

_TIMEOUT = 45.0
_MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024  # match the upload cap
_VIZIER_WORDS_URL = "https://vizier.cds.unistra.fr/viz-bin/votable"
_VIZIER_TSV_URL = "https://vizier.cds.unistra.fr/viz-bin/asu-tsv"
_VIZIER_ROW_CAP = 100_000
_ZENODO_API = "https://zenodo.org/api/records"
# Data-file extensions worth staging from a Zenodo record.
_ZENODO_DATA_EXTS = (".csv", ".tsv", ".txt", ".dat", ".fits", ".json", ".parquet", ".npy", ".npz")


@dataclass
class DataCandidate:
    """One search hit an agent can [FETCHDATA:]."""

    id: str  # provider-prefixed, e.g. "vizier:J/A+A/701/A297"
    title: str
    source: str
    detail: str = ""


async def _download_capped(client: httpx.AsyncClient, url: str, dest: Path) -> int:
    """Stream a URL to dest with a hard size cap. Returns bytes written."""
    written = 0
    async with client.stream("GET", url) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            async for chunk in r.aiter_bytes():
                written += len(chunk)
                if written > _MAX_DOWNLOAD_BYTES:
                    raise ValueError(f"download exceeds {_MAX_DOWNLOAD_BYTES // 2**20} MB cap")
                f.write(chunk)
    if written == 0:
        raise ValueError("empty download")
    return written


def _sanitize(name: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", name).strip("._") or "dataset"


def parse_vizier_resources(votable_text: str, max_results: int = 4) -> list[DataCandidate]:
    """Extract catalog RESOURCEs (name= + DESCRIPTION) from a VizieR VOTable."""
    out: list[DataCandidate] = []
    seen: set[str] = set()
    for chunk in votable_text.split("<RESOURCE")[1:]:
        m = re.search(r'name="((?:J|[IVX]+|B)/[^"]+)"', chunk)
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        desc = re.search(r"<DESCRIPTION>\s*(.*?)\s*</DESCRIPTION>", chunk, re.S)
        title = re.sub(r"\s+", " ", desc.group(1)) if desc else m.group(1)
        out.append(DataCandidate(id=f"vizier:{m.group(1)}", title=title[:200], source="VizieR/CDS"))
        if len(out) >= max_results:
            break
    return out


class VizieRDataProvider:
    """CDS/VizieR: astronomical catalogs (the canonical astro table service)."""

    name = "vizier"

    async def search(self, query: str, max_results: int = 4) -> list[DataCandidate]:
        params = {"-words": query, "-meta": "", "-out.max": str(max_results)}
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(_VIZIER_WORDS_URL, params=params)
            r.raise_for_status()
            text = r.text
        return parse_vizier_resources(text, max_results)

    def owns(self, dataset_id: str) -> bool:
        return dataset_id.startswith("vizier:") or bool(re.match(r"^(?:J|[IVX]+|B)/", dataset_id))

    async def fetch(self, dataset_id: str, dest_dir: Path) -> Path:
        cat = dataset_id.split(":", 1)[1] if dataset_id.startswith("vizier:") else dataset_id
        url = f"{_VIZIER_TSV_URL}?-source={quote(cat, safe='')}&-out.all&-out.max={_VIZIER_ROW_CAP}"
        dest = dest_dir / f"vizier_{_sanitize(cat)}.tsv"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            await _download_capped(client, url, dest)
        # A words-page or error page instead of a table is a failed fetch.
        head = dest.read_text(errors="replace")[:4000]
        if "#RESOURCE" not in head and "\t" not in head:
            dest.unlink(missing_ok=True)
            raise ValueError(f"VizieR returned no table for '{cat}'")
        return dest


class ZenodoDataProvider:
    """Zenodo: general open research data (domain-agnostic)."""

    name = "zenodo"

    async def search(self, query: str, max_results: int = 4) -> list[DataCandidate]:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(
                _ZENODO_API, params={"q": query, "size": str(max_results), "sort": "bestmatch"}
            )
            r.raise_for_status()
            hits = (r.json().get("hits") or {}).get("hits") or []
        out: list[DataCandidate] = []
        for h in hits:
            files = h.get("files") or []
            data_files = [
                f for f in files if str(f.get("key", "")).lower().endswith(_ZENODO_DATA_EXTS)
            ]
            if not data_files:
                continue  # only offer records the fetch step can actually stage
            out.append(
                DataCandidate(
                    id=f"zenodo:{h.get('id')}",
                    title=str((h.get("metadata") or {}).get("title", ""))[:200],
                    source="Zenodo",
                    detail=f"{len(data_files)} data file(s)",
                )
            )
        return out

    def owns(self, dataset_id: str) -> bool:
        return dataset_id.startswith("zenodo:")

    async def fetch(self, dataset_id: str, dest_dir: Path) -> Path:
        recid = dataset_id.split(":", 1)[1]
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            r = await client.get(f"{_ZENODO_API}/{quote(recid, safe='')}")
            r.raise_for_status()
            files = r.json().get("files") or []
            data_files = [
                f for f in files if str(f.get("key", "")).lower().endswith(_ZENODO_DATA_EXTS)
            ]
            if not data_files:
                raise ValueError(f"Zenodo record {recid} has no stageable data file")
            f0 = data_files[0]
            url = (f0.get("links") or {}).get("self")
            if not url:
                raise ValueError(f"Zenodo record {recid}: file has no download link")
            dest = dest_dir / _sanitize(str(f0.get("key", f"zenodo_{recid}")))
            await _download_capped(client, url, dest)
        return dest


_PROVIDER_CLASSES: dict[str, type] = {
    "vizier": VizieRDataProvider,
    "zenodo": ZenodoDataProvider,
}


def create_data_providers(names: list[str]) -> list[Any]:
    """Instantiate the configured providers (unknown names are skipped)."""
    out: list[Any] = []
    for name in names or []:
        cls = _PROVIDER_CLASSES.get(str(name).strip().lower())
        if cls is not None:
            out.append(cls())
    return out


async def fetch_dataset(providers: list[Any], dataset_id: str) -> Path:
    """Download a dataset id via whichever provider owns it (temp location)."""
    dataset_id = dataset_id.strip()
    tmp_dir = Path(tempfile.mkdtemp(prefix="paradigm-data-"))
    for p in providers:
        if p.owns(dataset_id):
            return await p.fetch(dataset_id, tmp_dir)
    raise ValueError(
        f"no configured data provider recognizes '{dataset_id}' "
        "(use the id exactly as shown in the DATASEARCH results)"
    )
