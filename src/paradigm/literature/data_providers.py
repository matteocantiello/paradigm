"""Repository data providers (D2): search + fetch REAL datasets for the sandbox.

The real-data mandate needs an acquisition path, not just a ban: agents get
``[DATASEARCH: query]`` to find datasets in wired repositories and
``[FETCHDATA: <id>]`` to stage one into /data/shared/data with a data card —
mirroring the literature [SEARCH:]/[READ:] pattern.

Providers (plain httpx, endpoints verified live 2026-07-08 / 2026-07-09):

Astronomy —
- VizieR/CDS   — ``-words`` catalog search + ``asu-tsv`` download
                 (``vizier:J/A+A/701/A297``); multi-table catalogs are split
                 into one staged file per sub-table.
- Gaia (ESA)   — Gaia archive TAP (``gaia:gaiadr3.nss_two_body_orbit``); full
                 server-side ADQL, so orbits and stellar parameters can be
                 JOINed on ``source_id`` in one bounded query.
- MAST         — space-telescope archive (Hubble/Webb/TESS/Kepler), TAP catalog.
- IRSA         — NASA/IPAC infrared archive, TAP catalog.
- HEASARC      — high-energy archive, TAP catalog (``heasarc:swiftmastr``).
- NED          — extragalactic database, TAP catalog.
- NASA Exoplanet Archive — TAP catalog (``exoplanet:ps``).
- SIMBAD       — object cross-match (resolve a name → coordinates/type/basic
                 params; ``simbad:M31``).

General / biology —
- Zenodo       — open research data (``zenodo:999271``).
- Dryad        — curated research datasets (``dryad:doi:10.5061/dryad.xxx``).
- UniProt      — protein sequences/annotations, TSV (``uniprot:P01308``).
- RCSB PDB     — protein structures (``pdb:3GOU`` → ``.pdb``/``.cif``).
- NCBI GEO     — gene-expression datasets (``geo:GSE12345``).

Providers are configured via ``literature.data_providers`` (names), so domains
choose their repositories — the orchestrator stays domain-agnostic. Astro
configs default to the astronomy set; a bio domain would list uniprot/pdb/geo.
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

_TIMEOUT = 90.0  # survey-catalog exports (GALAH/APOGEE) take server-side time
_MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024  # match the upload cap
_VIZIER_WORDS_URL = "https://vizier.cds.unistra.fr/viz-bin/votable"
_VIZIER_TSV_URL = "https://vizier.cds.unistra.fr/viz-bin/asu-tsv"
# Bounded sample, not the whole catalog: survey tables (GALAH, APOGEE) with
# -out.all can exceed the 100 MB download cap at 100k rows. 20k rows keeps a
# usable slice well under the cap; agents needing more run a targeted TAP query.
_VIZIER_ROW_CAP = 20_000
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


async def _download_capped(
    client: httpx.AsyncClient, url: str, dest: Path, *, keep_partial: bool = False
) -> int:
    """Stream a URL to dest with a hard size cap. Returns bytes written.

    ``keep_partial`` (line-oriented text only): instead of failing when a big
    catalog exceeds the cap, keep the prefix trimmed to the last complete line —
    a bounded, valid sample beats no data. Binary formats leave it False.
    """
    written = 0
    async with client.stream("GET", url) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            async for chunk in r.aiter_bytes():
                if written + len(chunk) > _MAX_DOWNLOAD_BYTES:
                    if keep_partial:
                        f.write(chunk[: _MAX_DOWNLOAD_BYTES - written])
                        written = _MAX_DOWNLOAD_BYTES
                        break
                    raise ValueError(f"download exceeds {_MAX_DOWNLOAD_BYTES // 2**20} MB cap")
                written += len(chunk)
                f.write(chunk)
    if written == 0:
        raise ValueError("empty download")
    if keep_partial and written >= _MAX_DOWNLOAD_BYTES:
        # Trim a truncated text file back to its last complete line.
        data = dest.read_bytes()
        nl = data.rfind(b"\n")
        if nl > 0:
            dest.write_bytes(data[: nl + 1])
    return written


def _sanitize(name: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", name).strip("._") or "dataset"


_VIZIER_TABLE_RE = re.compile(r"^#Table\s+(.+)$", re.M)
# asu-tsv header/data separator: dash-groups joined by tabs. A width-1 column
# (e.g. a 1-char Flags field) yields a single "-", so segments are 1+ dashes.
_VIZIER_DASHES_RE = re.compile(r"^-{3,}[-\t]*\s*$", re.M)


def split_vizier_tables(text: str) -> list[tuple[str, str]]:
    """Split a multi-table VizieR asu-tsv export into ``(name, standalone_text)``.

    A ``-source=<catalog>`` fetch of a multi-table catalog (e.g. Gaia DR3 NSS
    ``I/357``, which bundles 17 solution-type sub-tables) concatenates every
    sub-table under ONE ``#RESOURCE`` preamble, each with its own ``#Column``
    schema + header. Read as a single TSV, only the first table's columns align
    with its data — every other sub-table's rows land in the wrong columns and
    get silently dropped (this is what buried ~52k short-period Gaia binaries).

    Returns one entry per sub-table, each prefixed with the shared preamble so it
    is a valid standalone single-table export. A single-table input returns
    ``[("", text)]`` (caller keeps its existing one-file behaviour).
    """
    marks = list(_VIZIER_TABLE_RE.finditer(text))
    if len(marks) <= 1:
        return [("", text)]
    preamble = text[: marks[0].start()]
    out: list[tuple[str, str]] = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        block = text[m.start() : end]
        name = m.group(1).strip().rstrip(":").strip()
        # Skip a table only when we can POSITIVELY confirm it is empty (a dashes
        # separator with no data after it). If the separator can't be located we
        # keep the table — never drop real data over a parsing edge case.
        dash = _VIZIER_DASHES_RE.search(block)
        if dash is not None and not any(
            ln.strip() and not ln.startswith("#") for ln in block[dash.end() :].splitlines()
        ):
            continue
        out.append((name, preamble + block))
    return out or [("", text)]


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
        # Default (curated main) columns, NOT -out.all: survey catalogs like
        # GALAH/APOGEE carry ~500 columns and -out.all blows past the size cap.
        url = f"{_VIZIER_TSV_URL}?-source={quote(cat, safe='')}&-out.max={_VIZIER_ROW_CAP}"
        dest = dest_dir / f"vizier_{_sanitize(cat)}.tsv"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            await _download_capped(client, url, dest, keep_partial=True)
        # A words-page or error page instead of a table is a failed fetch.
        text = dest.read_text(errors="replace")
        if "#RESOURCE" not in text[:4000] and "\t" not in text[:4000]:
            dest.unlink(missing_ok=True)
            raise ValueError(f"VizieR returned no table for '{cat}'")
        # A multi-table catalog must be split into one file per sub-table, or
        # every sub-table after the first is misread against the wrong header.
        tables = split_vizier_tables(text)
        if len(tables) <= 1:
            return dest
        dest.unlink(missing_ok=True)
        out_dir = dest_dir / f"vizier_{_sanitize(cat)}"
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, tbl_text in tables:
            fname = _sanitize(name or "table")
            (out_dir / f"{fname}.tsv").write_text(tbl_text)
        return out_dir


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


# ---------------------------------------------------------------------------
# TAP archives (IVOA Table Access Protocol) — MAST / IRSA / HEASARC / NED /
# NASA Exoplanet Archive. Search lists matching tables; fetch dumps a bounded
# TOP-N slice. Some services honor FORMAT=csv, others always return VOTable, so
# both are parsed.
# ---------------------------------------------------------------------------

_TAP_ROW_CAP = 5_000  # bounded first slice; agents can run their own TAP query in-sandbox
_TD_RE = re.compile(r"<TD>(.*?)</TD>", re.S)
_TR_RE = re.compile(r"<TR>(.*?)</TR>", re.S)


def parse_tabular_rows(text: str) -> list[list[str]]:
    """Rows of a TAP response, whether it came back as CSV or VOTable."""
    stripped = text.lstrip()
    if stripped.startswith("<") or "<VOTABLE" in stripped[:200]:
        rows: list[list[str]] = []
        block = text
        m = re.search(r"<TABLEDATA>(.*?)</TABLEDATA>", text, re.S)
        if m:
            block = m.group(1)
        for tr in _TR_RE.findall(block):
            cells = [re.sub(r"\s+", " ", _unescape(c)).strip() for c in _TD_RE.findall(tr)]
            if cells:
                rows.append(cells)
        return rows
    # CSV
    import csv
    import io

    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if r]
    return rows[1:] if rows else []  # drop header row


def _unescape(s: str) -> str:
    return s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("&quot;", '"')


class _TapCatalogProvider:
    """Base for IVOA-TAP archives exposing queryable tables.

    Subclasses set ``name``, ``_BASE_URL``, ``_PREFIX``, ``_SOURCE`` and (for
    NASA Exoplanet Archive's non-standard TAP) ``_EXOPLANET_STYLE``.
    """

    name = ""
    _BASE_URL = ""
    _PREFIX = ""
    _SOURCE = ""
    _EXOPLANET_STYLE = False

    async def _run(self, adql: str) -> str:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            if self._EXOPLANET_STYLE:
                r = await client.get(self._BASE_URL, params={"query": adql, "format": "csv"})
            else:
                # POST is the robust TAP-sync method (HEASARC in particular
                # rejects the GET form for these queries).
                r = await client.post(
                    self._BASE_URL,
                    data={
                        "REQUEST": "doQuery",
                        "LANG": "ADQL",
                        "FORMAT": "csv",
                        "QUERY": adql,
                    },
                )
            r.raise_for_status()
            return r.text

    async def search(self, query: str, max_results: int = 4) -> list[DataCandidate]:
        q = re.sub(r"[^\w\s%.-]", " ", query).strip()[:60]
        like = f"%{q.replace(' ', '%')}%"
        n = max_results
        # Tiered so one archive's quirks (HEASARC has no `description` column;
        # MAST descriptions don't carry science keywords) degrade gracefully:
        # (1) keyword over name+description, (2) keyword over name only,
        # (3) just list some real tables so the archive is still discoverable.
        # Exclude the TAP_SCHEMA meta-tables in the QUERY so real data tables
        # surface in the tier-3 listing (they otherwise sort first and get
        # filtered client-side, leaving 0 hits for MAST/NED).
        no_meta = "table_name NOT LIKE 'TAP_SCHEMA%' AND table_name NOT LIKE 'tap_schema%'"
        for adql in (
            f"SELECT TOP {n} table_name, description FROM TAP_SCHEMA.tables "
            f"WHERE ({no_meta}) AND (table_name LIKE '{like}' OR description LIKE '{like}')",
            f"SELECT TOP {n} table_name FROM TAP_SCHEMA.tables "
            f"WHERE ({no_meta}) AND table_name LIKE '{like}'",
            f"SELECT TOP {n} table_name FROM TAP_SCHEMA.tables WHERE {no_meta}",
        ):
            try:
                rows = parse_tabular_rows(await self._run(adql))
            except Exception:
                continue
            out: list[DataCandidate] = []
            for row in rows:
                tname = row[0].strip().strip('"')
                if not tname or tname.lower().startswith("tap_schema"):
                    continue
                desc = row[1].strip().strip('"') if len(row) > 1 else ""
                out.append(
                    DataCandidate(
                        id=f"{self._PREFIX}:{tname}",
                        title=(desc or tname)[:200],
                        source=self._SOURCE,
                    )
                )
                if len(out) >= n:
                    break
            if out:
                return out
        return []

    def owns(self, dataset_id: str) -> bool:
        return dataset_id.startswith(f"{self._PREFIX}:")

    async def fetch(self, dataset_id: str, dest_dir: Path) -> Path:
        table = dataset_id.split(":", 1)[1]
        if not re.match(r"^[\w.\"]+$", table):
            raise ValueError(f"unsafe table name '{table}'")
        text = await self._run(f"SELECT TOP {_TAP_ROW_CAP} * FROM {table}")
        if len(text) > _MAX_DOWNLOAD_BYTES:
            raise ValueError("TAP result exceeds the size cap")
        if not text.strip() or ("ERROR" in text[:400] and "," not in text[:400]):
            raise ValueError(f"{self._SOURCE} returned no data for '{table}'")
        dest = dest_dir / f"{self._PREFIX}_{_sanitize(table)}.csv"
        dest.write_text(text)
        return dest


class MastDataProvider(_TapCatalogProvider):
    """MAST — Hubble/Webb/TESS/Kepler/Roman space-telescope archive."""

    name = "mast"
    _BASE_URL = "https://mast.stsci.edu/vo-tap/api/v0.1/caom/sync"
    _PREFIX = "mast"
    _SOURCE = "MAST"


class IrsaDataProvider(_TapCatalogProvider):
    """IRSA — NASA/IPAC Infrared Science Archive (WISE, 2MASS, Spitzer, …)."""

    name = "irsa"
    _BASE_URL = "https://irsa.ipac.caltech.edu/TAP/sync"
    _PREFIX = "irsa"
    _SOURCE = "IRSA"


class HeasarcDataProvider(_TapCatalogProvider):
    """HEASARC — High-Energy Astrophysics archive (X-ray/gamma catalogs).

    NOTE: HEASARC's Xamin TAP executes ADQL (fetch by an explicit
    ``heasarc:<table>`` id works) but does not serve ``TAP_SCHEMA.tables``
    rows to anonymous keyword queries, so ``search`` typically returns nothing —
    an agent must already know the catalog name (e.g. ``heasarc:swiftmastr``).
    Registered and available; kept out of the default provider lists for now.
    """

    name = "heasarc"
    _BASE_URL = "https://heasarc.gsfc.nasa.gov/xamin/vo/tap/sync"
    _PREFIX = "heasarc"
    _SOURCE = "HEASARC"


class NedDataProvider(_TapCatalogProvider):
    """NED — NASA/IPAC Extragalactic Database (multiwavelength object data)."""

    name = "ned"
    _BASE_URL = "https://ned.ipac.caltech.edu/tap/sync"
    _PREFIX = "ned"
    _SOURCE = "NED"


class ExoplanetArchiveDataProvider(_TapCatalogProvider):
    """NASA Exoplanet Archive — confirmed planets, KOIs, time series."""

    name = "nasa_exoplanet"
    _BASE_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
    _PREFIX = "exoplanet"
    _SOURCE = "NASA Exoplanet Archive"
    _EXOPLANET_STYLE = True


class GaiaDataProvider(_TapCatalogProvider):
    """ESA Gaia archive TAP — DR3 astrometry, NSS binary orbits, astrophysical
    parameters (the canonical Gaia source).

    Because it runs full ADQL server-side, ``[FETCHDATA: gaia:gaiadr3.<table>]``
    stages a bounded slice of a real Gaia table with correctly-named columns and
    ALL rows (e.g. every ``nss_two_body_orbit`` solution type, including the
    short-period SB1/SB2 orbits) — the reliable alternative to a multi-table
    VizieR export. For combining orbits with stellar parameters, an experiment
    should JOIN ``nss_two_body_orbit`` to ``astrophysical_parameters`` on
    ``source_id`` in one bounded server-side query rather than crossmatching
    capped local files.
    """

    name = "gaia"
    _BASE_URL = "https://gea.esac.esa.int/tap-server/tap/sync"
    _PREFIX = "gaia"
    _SOURCE = "ESA Gaia Archive"


# ---------------------------------------------------------------------------
# SIMBAD — object cross-match (name → coordinates / type / basic parameters)
# ---------------------------------------------------------------------------

_SIMBAD_TAP = "https://simbad.cds.unistra.fr/simbad/sim-tap/sync"


class SimbadDataProvider:
    """SIMBAD — resolve an astronomical object name to its basic parameters.

    Distinct from the catalog archives: ``[DATASEARCH: M31]`` resolves the name
    and offers ``simbad:M31``; ``[FETCHDATA: simbad:M31]`` stages a one-row CSV
    (identifier, RA/Dec, object type, spectral type, magnitudes). The
    cross-match use — turn a list of names into coordinates/types.
    """

    name = "simbad"

    async def _run(self, adql: str) -> str:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            r = await client.get(
                _SIMBAD_TAP,
                params={"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": adql},
            )
            r.raise_for_status()
            return r.text

    async def search(self, query: str, max_results: int = 4) -> list[DataCandidate]:
        name = query.strip().replace("'", "''")[:80]
        adql = (
            "SELECT TOP 1 b.main_id, b.otype_txt FROM ident i "
            "JOIN basic b ON i.oidref = b.oid WHERE i.id = '" + name + "'"
        )
        try:
            rows = parse_tabular_rows(await self._run(adql))
        except Exception:
            return []
        if not rows:
            return []
        main_id = rows[0][0].strip().strip('"')
        otype = rows[0][1].strip().strip('"') if len(rows[0]) > 1 else ""
        return [
            DataCandidate(
                id=f"simbad:{main_id}",
                title=f"{main_id} — {otype}" if otype else main_id,
                source="SIMBAD",
                detail="object cross-match (coordinates + basic params)",
            )
        ]

    def owns(self, dataset_id: str) -> bool:
        return dataset_id.startswith("simbad:")

    async def fetch(self, dataset_id: str, dest_dir: Path) -> Path:
        obj = dataset_id.split(":", 1)[1].replace("'", "''")
        adql = (
            "SELECT b.main_id, b.ra, b.dec, b.otype_txt, b.sp_type, b.nbref "
            "FROM ident i JOIN basic b ON i.oidref = b.oid WHERE i.id = '" + obj + "'"
        )
        text = await self._run(adql)
        if not text.strip() or len(parse_tabular_rows(text)) == 0:
            raise ValueError(f"SIMBAD did not resolve '{obj}'")
        dest = dest_dir / f"simbad_{_sanitize(obj)}.csv"
        dest.write_text(text)
        return dest


# ---------------------------------------------------------------------------
# Biology / general REST archives
# ---------------------------------------------------------------------------

_DRYAD_API = "https://datadryad.org/api/v2"
_UNIPROT_API = "https://rest.uniprot.org/uniprotkb"
_PDB_SEARCH = "https://search.rcsb.org/rcsbsearch/v2/query"
_PDB_FILES = "https://files.rcsb.org/download"
_GEO_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class DryadDataProvider:
    """Dryad — curated, DOI-assigned research datasets (domain-agnostic)."""

    name = "dryad"

    async def search(self, query: str, max_results: int = 4) -> list[DataCandidate]:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            r = await client.get(
                f"{_DRYAD_API}/search", params={"q": query, "per_page": str(max_results)}
            )
            r.raise_for_status()
            datasets = (r.json().get("_embedded") or {}).get("stash:datasets") or []
        out: list[DataCandidate] = []
        for d in datasets[:max_results]:
            ident = d.get("identifier")  # "doi:10.5061/dryad.xxx"
            if not ident:
                continue
            out.append(
                DataCandidate(
                    id=f"dryad:{ident}", title=str(d.get("title", ""))[:200], source="Dryad"
                )
            )
        return out

    def owns(self, dataset_id: str) -> bool:
        return dataset_id.startswith("dryad:")

    async def fetch(self, dataset_id: str, dest_dir: Path) -> Path:
        doi = dataset_id.split(":", 1)[1]  # "doi:10.5061/dryad.xxx"
        enc = quote(doi, safe="")
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            # Resolve the latest version, then download its files zip.
            meta = await client.get(f"{_DRYAD_API}/datasets/{enc}")
            meta.raise_for_status()
            ver = ((meta.json().get("_links") or {}).get("stash:version") or {}).get("href")
            if ver:
                vr = await client.get(f"https://datadryad.org{ver}")
                if vr.status_code == 200:
                    dl = ((vr.json().get("_links") or {}).get("stash:download") or {}).get("href")
                    if dl:
                        url = dl if dl.startswith("http") else f"https://datadryad.org{dl}"
                        resp = await client.get(url)
                        if resp.status_code == 200 and resp.content:
                            dest = dest_dir / f"dryad_{_sanitize(doi)}.zip"
                            dest.write_bytes(resp.content[:_MAX_DOWNLOAD_BYTES])
                            return dest
        # Dryad increasingly gates bulk downloads; the DOI landing page always
        # works. Fail with an actionable message rather than a silent stub.
        raise ValueError(
            f"Dryad dataset {doi} could not be auto-downloaded (bulk download is "
            f"often auth-gated). Use its landing page https://doi.org/{doi.split(':', 1)[-1]} "
            "or a [DATA: <direct file url>] tag."
        )


class UniProtDataProvider:
    """UniProt — protein sequence + annotation records (TSV)."""

    name = "uniprot"
    _FIELDS = "accession,id,protein_name,gene_names,organism_name,length,sequence"

    async def search(self, query: str, max_results: int = 4) -> list[DataCandidate]:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            r = await client.get(
                f"{_UNIPROT_API}/search",
                params={
                    "query": query,
                    "format": "tsv",
                    "size": str(max_results),
                    "fields": "accession,protein_name,organism_name",
                },
            )
            r.raise_for_status()
            lines = [ln for ln in r.text.splitlines() if ln.strip()]
        out: list[DataCandidate] = []
        for ln in lines[1 : max_results + 1]:  # skip header
            cols = ln.split("\t")
            acc = cols[0].strip()
            if not acc:
                continue
            title = f"{cols[1]} ({cols[2]})" if len(cols) > 2 else acc
            out.append(DataCandidate(id=f"uniprot:{acc}", title=title[:200], source="UniProt"))
        return out

    def owns(self, dataset_id: str) -> bool:
        return dataset_id.startswith("uniprot:")

    async def fetch(self, dataset_id: str, dest_dir: Path) -> Path:
        acc = _sanitize(dataset_id.split(":", 1)[1])
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            r = await client.get(
                f"{_UNIPROT_API}/search",
                params={"query": f"accession:{acc}", "format": "tsv", "fields": self._FIELDS},
            )
            r.raise_for_status()
            if len(r.text.splitlines()) < 2:
                raise ValueError(f"UniProt has no entry {acc}")
            dest = dest_dir / f"uniprot_{acc}.tsv"
            dest.write_text(r.text)
        return dest


class PdbDataProvider:
    """RCSB PDB — experimentally determined macromolecular structures."""

    name = "pdb"

    async def search(self, query: str, max_results: int = 4) -> list[DataCandidate]:
        body = {
            "query": {
                "type": "terminal",
                "service": "full_text",
                "parameters": {"value": query},
            },
            "return_type": "entry",
            "request_options": {"paginate": {"start": 0, "rows": max_results}},
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            r = await client.post(_PDB_SEARCH, json=body)
            if r.status_code == 204:
                return []
            r.raise_for_status()
            ids = [x["identifier"] for x in (r.json().get("result_set") or [])]
        return [
            DataCandidate(id=f"pdb:{i}", title=f"PDB structure {i}", source="RCSB PDB")
            for i in ids[:max_results]
        ]

    def owns(self, dataset_id: str) -> bool:
        return dataset_id.startswith("pdb:")

    async def fetch(self, dataset_id: str, dest_dir: Path) -> Path:
        pid = _sanitize(dataset_id.split(":", 1)[1]).lower()
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            dest = dest_dir / f"pdb_{pid}.pdb"
            try:
                await _download_capped(client, f"{_PDB_FILES}/{pid}.pdb", dest)
            except Exception:
                # Large/modern entries are mmCIF-only.
                dest = dest_dir / f"pdb_{pid}.cif"
                await _download_capped(client, f"{_PDB_FILES}/{pid}.cif", dest)
        return dest


class GeoDataProvider:
    """NCBI GEO — gene-expression datasets/series (metadata + supplementary)."""

    name = "geo"

    async def search(self, query: str, max_results: int = 4) -> list[DataCandidate]:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            r = await client.get(
                f"{_GEO_EUTILS}/esearch.fcgi",
                params={"db": "gds", "term": query, "retmax": str(max_results), "retmode": "json"},
            )
            r.raise_for_status()
            uids = (r.json().get("esearchresult") or {}).get("idlist") or []
            if not uids:
                return []
            s = await client.get(
                f"{_GEO_EUTILS}/esummary.fcgi",
                params={"db": "gds", "id": ",".join(uids), "retmode": "json"},
            )
            s.raise_for_status()
            result = s.json().get("result") or {}
        out: list[DataCandidate] = []
        for uid in uids[:max_results]:
            rec = result.get(uid) or {}
            acc = rec.get("accession") or f"UID{uid}"  # e.g. "GSE12345"
            out.append(
                DataCandidate(
                    id=f"geo:{acc}", title=str(rec.get("title", acc))[:200], source="NCBI GEO"
                )
            )
        return out

    def owns(self, dataset_id: str) -> bool:
        return dataset_id.startswith("geo:")

    async def fetch(self, dataset_id: str, dest_dir: Path) -> Path:
        acc = _sanitize(dataset_id.split(":", 1)[1])
        if not re.match(r"^GSE\d+$", acc):
            raise ValueError(f"GEO fetch needs a GSE series accession, got '{acc}'")
        # SOFT-family flat file (series matrix requires the FTP path scheme).
        stub = acc[:-3] + "nnn"
        url = f"https://ftp.ncbi.nlm.nih.gov/geo/series/{stub}/{acc}/soft/{acc}_family.soft.gz"
        dest = dest_dir / f"geo_{acc}_family.soft.gz"
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            await _download_capped(client, url, dest)
        return dest


_PROVIDER_CLASSES: dict[str, type] = {
    # Astronomy
    "vizier": VizieRDataProvider,
    "gaia": GaiaDataProvider,
    "mast": MastDataProvider,
    "irsa": IrsaDataProvider,
    "heasarc": HeasarcDataProvider,
    "ned": NedDataProvider,
    "nasa_exoplanet": ExoplanetArchiveDataProvider,
    "simbad": SimbadDataProvider,
    # General / biology
    "zenodo": ZenodoDataProvider,
    "dryad": DryadDataProvider,
    "uniprot": UniProtDataProvider,
    "pdb": PdbDataProvider,
    "geo": GeoDataProvider,
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
    """Download a dataset id via whichever provider owns it (temp location).

    Retries the owning provider once on failure — archive TAP endpoints have
    transient hiccups, and losing a whole dataset to one timeout is worse than a
    second attempt.
    """
    dataset_id = dataset_id.strip()
    tmp_dir = Path(tempfile.mkdtemp(prefix="paradigm-data-"))
    for p in providers:
        if p.owns(dataset_id):
            try:
                return await p.fetch(dataset_id, tmp_dir)
            except Exception:
                return await p.fetch(dataset_id, tmp_dir)  # one retry on transient failure
    raise ValueError(
        f"no configured data provider recognizes '{dataset_id}' "
        "(use the id exactly as shown in the DATASEARCH results)"
    )
