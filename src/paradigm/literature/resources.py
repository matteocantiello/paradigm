"""Resource classification and resolution for prompt preprocessing.

Classifies URLs in the research prompt into different resource types
(papers, code repos, code files, data files, web references) and resolves
them during the SEEDING phase so agents can use them in later phases.
"""

from __future__ import annotations

import asyncio
import html
import re
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from paradigm.logging.events import EventLogger

# Maximum file size for data downloads (100 MB)
_MAX_DATA_SIZE = 100 * 1024 * 1024

# Maximum chars to keep from HTML reference pages
_MAX_REFERENCE_LENGTH = 20_000

# Maximum chars per reference in context injection
_REFERENCE_CONTEXT_LIMIT = 5_000

# Git clone timeout in seconds
_GIT_CLONE_TIMEOUT = 120

# Code file extensions
_CODE_EXTENSIONS = frozenset(
    {
        ".py",
        ".ipynb",
        ".jl",
        ".r",
        ".R",
        ".m",
        ".f90",
        ".f95",
        ".c",
        ".cpp",
        ".h",
        ".rs",
        ".go",
        ".sh",
        ".yaml",
        ".yml",
        ".toml",
        ".json",
    }
)

# Data file extensions
_DATA_EXTENSIONS = frozenset(
    {
        ".csv",
        ".fits",
        ".hdf5",
        ".h5",
        ".npy",
        ".npz",
        ".parquet",
        ".tsv",
        ".dat",
        ".txt",
        ".gz",
        ".tar",
        ".zip",
    }
)

# Regex to strip HTML tags
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_HTML_BLOCK_RE = re.compile(r"</(p|div|h[1-6]|li|tr|br)[^>]*>", re.IGNORECASE)

# GitHub URL patterns
_GITHUB_REPO_RE = re.compile(
    r"^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/(?:tree|blob)/.*)?$"
)
_GITHUB_BLOB_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/]+)/blob/(.+)$")
_GITHUB_RAW_RE = re.compile(r"^https?://raw\.githubusercontent\.com/")


class ResourceType(StrEnum):
    """Type of external resource referenced in a prompt."""

    PAPER = "paper"
    CODE_REPO = "code_repo"
    CODE_FILE = "code_file"
    DATA = "data"
    REFERENCE = "reference"


class ResolvedResource(BaseModel):
    """A resolved external resource with metadata and local paths."""

    url: str
    resource_type: ResourceType
    name: str
    local_path: str | None = None
    sandbox_path: str | None = None
    summary: str = ""
    content: str | None = None
    size_bytes: int | None = None
    error: str | None = None


def _get_extension(url: str) -> str:
    """Extract file extension from URL, ignoring query params."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if "." in path.split("/")[-1]:
        return "." + path.rsplit(".", 1)[-1].lower()
    return ""


def _github_to_raw_url(url: str) -> str:
    """Convert a GitHub blob URL to a raw.githubusercontent.com URL.

    Args:
        url: GitHub blob or tree URL.

    Returns:
        Raw content URL.
    """
    match = _GITHUB_BLOB_RE.match(url)
    if match:
        owner, repo, path = match.groups()
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{path}"
    return url


def _html_to_text(html_content: str) -> str:
    """Strip HTML to plain text.

    Removes script/style blocks, converts block-level tags to newlines,
    strips all remaining tags, and decodes HTML entities.

    Args:
        html_content: Raw HTML string.

    Returns:
        Plain text extracted from HTML.
    """
    text = _HTML_SCRIPT_RE.sub("", html_content)
    text = _HTML_BLOCK_RE.sub("\n", text)
    text = _HTML_TAG_RE.sub("", text)
    text = html.unescape(text)
    # Collapse whitespace within lines, preserve paragraph breaks
    lines = []
    for line in text.split("\n"):
        stripped = " ".join(line.split())
        if stripped:
            lines.append(stripped)
    text = "\n".join(lines)
    return text[:_MAX_REFERENCE_LENGTH]


def classify_resource(url: str) -> ResourceType:
    """Classify a URL into a resource type.

    Uses pattern matching in priority order:
    1. arxiv.org → paper
    2. .pdf extension → paper
    3. GitHub repo root or /tree/ → code_repo
    4. GitHub blob/raw + code extension → code_file
    5. GitHub blob/raw + data extension → data
    6. zenodo.org → data
    7. URL ending in code extension → code_file
    8. URL ending in data extension → data
    9. Everything else → reference

    Args:
        url: URL to classify.

    Returns:
        ResourceType for this URL.
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    path = parsed.path.rstrip("/")
    ext = _get_extension(url)

    # Priority 1: arXiv
    if "arxiv.org" in host:
        return ResourceType.PAPER

    # Priority 2: Direct PDF
    if ext == ".pdf":
        return ResourceType.PAPER

    # Priority 3: GitHub repo (root or /tree/)
    if "github.com" in host:
        # Count path segments after owner/repo
        segments = [s for s in path.split("/") if s]
        if len(segments) <= 2:
            # github.com/owner/repo or github.com/owner/repo.git
            return ResourceType.CODE_REPO
        if len(segments) >= 3 and segments[2] == "tree":
            return ResourceType.CODE_REPO

        # Priority 4/5: GitHub blob/raw
        if len(segments) >= 3 and segments[2] in ("blob", "raw"):
            if ext in _CODE_EXTENSIONS:
                return ResourceType.CODE_FILE
            if ext in _DATA_EXTENSIONS:
                return ResourceType.DATA
            # Default blob to code_file
            return ResourceType.CODE_FILE

    # raw.githubusercontent.com
    if _GITHUB_RAW_RE.match(url):
        if ext in _DATA_EXTENSIONS:
            return ResourceType.DATA
        return ResourceType.CODE_FILE

    # Priority 6: Zenodo
    if "zenodo.org" in host:
        return ResourceType.DATA

    # Priority 7: Code extension
    if ext in _CODE_EXTENSIONS:
        return ResourceType.CODE_FILE

    # Priority 8: Data extension
    if ext in _DATA_EXTENSIONS:
        return ResourceType.DATA

    # Priority 9: Everything else
    return ResourceType.REFERENCE


async def resolve_resource(
    url: str,
    resource_type: ResourceType,
    shared_dir: Path,
    logger: EventLogger,
) -> ResolvedResource:
    """Resolve a non-paper resource: download, clone, or scrape.

    Args:
        url: URL to resolve.
        resource_type: Pre-classified resource type.
        shared_dir: Base shared directory (data/shared).
        logger: Event logger for error reporting.

    Returns:
        ResolvedResource with local paths and metadata.
    """
    try:
        if resource_type == ResourceType.CODE_REPO:
            return await _resolve_code_repo(url, shared_dir)
        elif resource_type == ResourceType.CODE_FILE:
            return await _resolve_code_file(url, shared_dir)
        elif resource_type == ResourceType.DATA:
            return await _resolve_data_file(url, shared_dir)
        elif resource_type == ResourceType.REFERENCE:
            return await _resolve_reference(url)
        else:
            return ResolvedResource(
                url=url,
                resource_type=resource_type,
                name=url,
                error=f"Unsupported resource type: {resource_type}",
            )
    except Exception as e:
        return ResolvedResource(
            url=url,
            resource_type=resource_type,
            name=_extract_name(url, resource_type),
            error=str(e),
        )


def _extract_name(url: str, resource_type: ResourceType) -> str:
    """Extract a human-readable name from a URL."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    segments = [s for s in path.split("/") if s]

    if resource_type == ResourceType.CODE_REPO and "github.com" in (parsed.hostname or ""):
        if len(segments) >= 2:
            return segments[1].removesuffix(".git")
    if segments:
        return segments[-1]
    return parsed.hostname or url


async def _resolve_code_repo(url: str, shared_dir: Path) -> ResolvedResource:
    """Clone a GitHub repository (shallow).

    Args:
        url: GitHub repo URL.
        shared_dir: Base shared directory.

    Returns:
        ResolvedResource with clone path.
    """
    parsed = urlparse(url)
    segments = [s for s in parsed.path.rstrip("/").split("/") if s]

    if len(segments) >= 2:
        repo_name = segments[1].removesuffix(".git")
    else:
        repo_name = "repo"

    # Build clone URL (ensure it ends with .git for git clone)
    clone_url = f"https://github.com/{segments[0]}/{segments[1]}"
    if not clone_url.endswith(".git"):
        clone_url += ".git"

    repos_dir = shared_dir / "repos"
    repos_dir.mkdir(parents=True, exist_ok=True)
    local_path = repos_dir / repo_name

    if local_path.exists():
        # Already cloned (e.g. from a previous cycle)
        summary = f"Repository '{repo_name}' already exists at {local_path}"
    else:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "clone",
            "--depth",
            "1",
            clone_url,
            str(local_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_GIT_CLONE_TIMEOUT)
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            return ResolvedResource(
                url=url,
                resource_type=ResourceType.CODE_REPO,
                name=repo_name,
                error=f"Git clone timed out after {_GIT_CLONE_TIMEOUT}s",
            )

        if proc.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            return ResolvedResource(
                url=url,
                resource_type=ResourceType.CODE_REPO,
                name=repo_name,
                error=f"Git clone failed: {error_msg}",
            )

        # Build summary from top-level listing
        top_files = sorted(f.name for f in local_path.iterdir() if not f.name.startswith("."))
        summary = f"Cloned '{repo_name}': {', '.join(top_files[:15])}"

    sandbox_path = f"/data/shared/repos/{repo_name}"
    return ResolvedResource(
        url=url,
        resource_type=ResourceType.CODE_REPO,
        name=repo_name,
        local_path=str(local_path),
        sandbox_path=sandbox_path,
        summary=summary,
    )


async def _resolve_code_file(url: str, shared_dir: Path) -> ResolvedResource:
    """Download a code file.

    Args:
        url: URL to the code file (GitHub blob URLs are auto-converted to raw).
        shared_dir: Base shared directory.

    Returns:
        ResolvedResource with download path.
    """
    raw_url = _github_to_raw_url(url)
    filename = urlparse(raw_url).path.rstrip("/").split("/")[-1]

    code_dir = shared_dir / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    local_path = code_dir / filename

    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
        resp = await client.get(raw_url, headers={"User-Agent": "Paradigm/1.0"})
        resp.raise_for_status()

    local_path.write_bytes(resp.content)

    # Preview first 10 lines
    text = resp.content.decode("utf-8", errors="replace")
    preview_lines = text.split("\n")[:10]
    preview = "\n".join(preview_lines)
    summary = f"Downloaded '{filename}' ({len(resp.content)} bytes)\nPreview:\n{preview}"

    sandbox_path = f"/data/shared/code/{filename}"
    return ResolvedResource(
        url=url,
        resource_type=ResourceType.CODE_FILE,
        name=filename,
        local_path=str(local_path),
        sandbox_path=sandbox_path,
        summary=summary,
        size_bytes=len(resp.content),
    )


async def _resolve_data_file(url: str, shared_dir: Path) -> ResolvedResource:
    """Download a data file.

    Args:
        url: URL to the data file.
        shared_dir: Base shared directory.

    Returns:
        ResolvedResource with download path.
    """
    raw_url = _github_to_raw_url(url)
    filename = urlparse(raw_url).path.rstrip("/").split("/")[-1]

    data_dir = shared_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    local_path = data_dir / filename

    async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
        # Stream to check size before committing
        async with client.stream("GET", raw_url, headers={"User-Agent": "Paradigm/1.0"}) as resp:
            resp.raise_for_status()
            content_length = resp.headers.get("content-length")
            if content_length and int(content_length) > _MAX_DATA_SIZE:
                return ResolvedResource(
                    url=url,
                    resource_type=ResourceType.DATA,
                    name=filename,
                    error=f"File too large: {int(content_length)} bytes (max {_MAX_DATA_SIZE})",
                )

            chunks = []
            total = 0
            async for chunk in resp.aiter_bytes():
                total += len(chunk)
                if total > _MAX_DATA_SIZE:
                    return ResolvedResource(
                        url=url,
                        resource_type=ResourceType.DATA,
                        name=filename,
                        error=f"File too large: >{_MAX_DATA_SIZE} bytes",
                    )
                chunks.append(chunk)

    data = b"".join(chunks)
    local_path.write_bytes(data)

    sandbox_path = f"/data/shared/data/{filename}"
    summary = f"Downloaded '{filename}' ({len(data)} bytes)"

    return ResolvedResource(
        url=url,
        resource_type=ResourceType.DATA,
        name=filename,
        local_path=str(local_path),
        sandbox_path=sandbox_path,
        summary=summary,
        size_bytes=len(data),
    )


async def _resolve_reference(url: str) -> ResolvedResource:
    """Fetch a web page and extract text content.

    Args:
        url: URL to fetch.

    Returns:
        ResolvedResource with extracted text content.
    """
    name = urlparse(url).hostname or url

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        resp = await client.get(url, headers={"User-Agent": "Paradigm/1.0"})
        resp.raise_for_status()

    content_type = resp.headers.get("content-type", "")
    if "html" not in content_type and "text" not in content_type:
        return ResolvedResource(
            url=url,
            resource_type=ResourceType.REFERENCE,
            name=name,
            error=f"Not a text/HTML page: {content_type}",
        )

    text = _html_to_text(resp.text)
    summary = text[:500] + "..." if len(text) > 500 else text

    return ResolvedResource(
        url=url,
        resource_type=ResourceType.REFERENCE,
        name=name,
        content=text,
        summary=summary,
    )


def build_code_context(resources: list[ResolvedResource]) -> str:
    """Build markdown context string listing available code resources.

    Args:
        resources: All resolved resources.

    Returns:
        Markdown string for agent prompts, or empty string if none.
    """
    code_resources = [
        r
        for r in resources
        if r.resource_type in (ResourceType.CODE_REPO, ResourceType.CODE_FILE) and r.error is None
    ]
    if not code_resources:
        return ""

    lines = ["## Available Code Resources\n"]
    lines.append(
        "The following code repositories and files are available in the sandbox "
        "under `/data/shared/`. You can import from repositories directly.\n"
    )

    for r in code_resources:
        if r.resource_type == ResourceType.CODE_REPO:
            lines.append(f"- **Repository: {r.name}** — `{r.sandbox_path}`")
            lines.append(f"  {r.summary}")
            lines.append(f"  Import with: `import {r.name}` or `from {r.name} import ...`")
        else:
            lines.append(f"- **File: {r.name}** — `{r.sandbox_path}`")
            # Generate import instruction from filename
            module_name = Path(r.name).stem
            lines.append(
                f"  Import directly: `from {module_name} import ...` or `import {module_name}`"
            )
            lines.append(f"  {r.summary}")
    lines.append("")

    return "\n".join(lines)


def build_data_context(resources: list[ResolvedResource]) -> str:
    """Build markdown context string listing available data files.

    Args:
        resources: All resolved resources.

    Returns:
        Markdown string for agent prompts, or empty string if none.
    """
    data_resources = [
        r for r in resources if r.resource_type == ResourceType.DATA and r.error is None
    ]
    if not data_resources:
        return ""

    lines = ["## Available Data Files\n"]
    lines.append(
        "The following data files are available in the sandbox under `/data/shared/data/`. "
        "Use pandas, astropy, or numpy to load them.\n"
    )

    for r in data_resources:
        size_str = ""
        if r.size_bytes is not None:
            if r.size_bytes > 1024 * 1024:
                size_str = f" ({r.size_bytes / (1024 * 1024):.1f} MB)"
            elif r.size_bytes > 1024:
                size_str = f" ({r.size_bytes / 1024:.1f} KB)"
            else:
                size_str = f" ({r.size_bytes} bytes)"
        lines.append(f"- **{r.name}**{size_str} — `{r.sandbox_path}`")
    lines.append("")

    # Data cards: schema previews so experiments never blind-guess column
    # names/dtypes (URL-downloaded and locally-attached datasets alike).
    for r in data_resources:
        if r.local_path:
            card = build_data_card(Path(r.local_path))
            if card:
                lines.append(card)
                lines.append("")

    return "\n".join(lines)


def build_reference_context(resources: list[ResolvedResource]) -> str:
    """Build markdown context string with extracted text from web references.

    Args:
        resources: All resolved resources.

    Returns:
        Markdown string for agent prompts, or empty string if none.
    """
    refs = [
        r
        for r in resources
        if r.resource_type == ResourceType.REFERENCE and r.error is None and r.content
    ]
    if not refs:
        return ""

    lines = ["## Web Reference Materials\n"]

    for r in refs:
        content = r.content[:_REFERENCE_CONTEXT_LIMIT]
        if r.content and len(r.content) > _REFERENCE_CONTEXT_LIMIT:
            content += "\n... (truncated)"
        lines.append(f"### {r.name} ({r.url})\n")
        lines.append(content)
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Data cards + local dataset staging (attached datasets)
# ---------------------------------------------------------------------------

# Extensions treated as delimited text for schema preview.
_CARD_TABULAR_EXTS = {".csv", ".tsv", ".dat", ".txt"}
_CARD_SAMPLE_ROWS = 1000  # rows scanned for dtypes / value counts
_CARD_HEAD_ROWS = 5
_CARD_MAX_COLS = 30
_CARD_CELL_CAP = 24  # chars per head-row cell
_CARD_LOW_CARDINALITY = 12  # <= this many distinct values -> show value counts
_CARD_MAX_CHARS = 2000
_STAGE_MAX_DIR_FILES = 20  # files carded per attached directory

_SAFE_NAME_RE = re.compile(r"[^\w.\-]+")


def _sanitize_dataset_name(name: str) -> str:
    """Filesystem/sandbox-safe file name (also blocks path traversal in uploads)."""
    cleaned = _SAFE_NAME_RE.sub("_", Path(name).name).strip("._")
    return cleaned or "dataset"


def _infer_dtype(values: list[str]) -> str:
    """int / float / str over the non-empty sample values."""
    seen = [v for v in values if v.strip()]
    if not seen:
        return "empty"

    def _is(kind: type) -> bool:
        try:
            for v in seen:
                kind(v)
        except ValueError:
            return False
        return True

    if _is(int):
        return "int"
    if _is(float):
        return "float"
    return "str"


def _card_delimiter(sample: str, suffix: str) -> str | None:
    """Best-effort delimiter: csv.Sniffer, falling back by extension.

    Returns None for whitespace-delimited files (split on any whitespace).
    """
    import csv as _csv

    try:
        return _csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except _csv.Error:
        pass
    if suffix == ".csv":
        return ","
    if suffix == ".tsv":
        return "\t"
    return None  # .dat/.txt: whitespace


def _is_dashes_separator(row: list[str]) -> bool:
    """True for an asu-tsv ``---\\t---`` header/data separator row."""
    return bool(row) and all(
        c.strip() == "" or set(c.strip()) == {"-"} for c in row
    ) and any(set(c.strip()) == {"-"} for c in row)


def _tabular_card_lines(path: Path) -> list[str]:
    """Schema lines for a delimited text file (header, dtypes, head, value counts).

    Handles VizieR/CDS asu-tsv exports: leading ``#`` metadata is skipped and the
    units + dashes rows between header and data are dropped, so the card shows the
    REAL column names (e.g. ``Per``, ``ecc``) instead of a ``#RESOURCE`` line —
    otherwise experiments guess names like ``period`` and crash on load.
    """
    import csv as _csv

    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        raw: list[str] = []
        for line in f:
            if line.startswith("#"):
                continue  # asu-tsv / VizieR comment metadata
            raw.append(line)
            if len(raw) > _CARD_SAMPLE_ROWS + 5:
                break

    delimiter = _card_delimiter("".join(raw[:64]), path.suffix.lower())
    if delimiter is not None:
        rows = [r for r in _csv.reader(raw, delimiter=delimiter) if r]
    else:
        rows = [ln.split() for ln in raw if ln.strip()]

    if len(rows) < 2:
        return ["(no parseable rows)"]

    header = [h.strip() for h in rows[0]][:_CARD_MAX_COLS]
    data_rows = rows[1:]
    # asu-tsv: drop the units row + dashes separator so dtypes/head see real data.
    for i, r in enumerate(rows[1:5], start=1):
        if _is_dashes_separator(r):
            data_rows = rows[i + 1 :]
            break
    n_cols_note = (
        f" (first {_CARD_MAX_COLS} columns shown)" if len(rows[0]) > _CARD_MAX_COLS else ""
    )

    columns: list[list[str]] = [[] for _ in header]
    for row in data_rows:
        for i in range(min(len(header), len(row))):
            columns[i].append(row[i])

    lines = [f"Columns ({len(rows[0])}){n_cols_note}:"]
    for name, values in zip(header, columns, strict=False):
        dtype = _infer_dtype(values)
        entry = f"  - {name}: {dtype}"
        if dtype == "str":
            distinct = {v.strip() for v in values if v.strip()}
            if 0 < len(distinct) <= _CARD_LOW_CARDINALITY:
                from collections import Counter

                counts = Counter(v.strip() for v in values if v.strip())
                top = ", ".join(f"{k}({n})" for k, n in counts.most_common(6))
                entry += f" [{len(distinct)} values: {top}]"
        lines.append(entry)

    lines.append(
        f"Rows sampled: {len(data_rows)}" + ("+" if len(data_rows) > _CARD_SAMPLE_ROWS - 1 else "")
    )
    lines.append("Head:")
    for row in data_rows[:_CARD_HEAD_ROWS]:
        cells = [c[:_CARD_CELL_CAP] for c in row[:_CARD_MAX_COLS]]
        lines.append("  " + " | ".join(cells))
    return lines


def build_data_card(path: Path, max_chars: int = _CARD_MAX_CHARS) -> str:
    """Compact schema preview ("data card") of a data file for agent prompts.

    The durable fix for schema-blindness: without this, experiments blind-guess
    column names/dtypes and burn retry rounds (bit 3 models on CliniFact).
    Stdlib-only (no pandas on the host). Never raises — unreadable/binary files
    degrade to a name+size line.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return ""
    if size > 1024 * 1024:
        size_str = f"{size / (1024 * 1024):.1f} MB"
    elif size > 1024:
        size_str = f"{size / 1024:.1f} KB"
    else:
        size_str = f"{size} B"

    lines = [f"### Data card: {path.name} ({size_str})"]
    suffix = path.suffix.lower()
    try:
        if suffix in _CARD_TABULAR_EXTS:
            lines += _tabular_card_lines(path)
        elif suffix == ".json":
            import json as _json

            with open(path, encoding="utf-8", errors="replace") as f:
                obj = _json.loads(f.read(512 * 1024))
            if isinstance(obj, list):
                lines.append(f"JSON array of {len(obj)} items")
                if obj and isinstance(obj[0], dict):
                    lines.append("Item keys: " + ", ".join(list(obj[0].keys())[:_CARD_MAX_COLS]))
            elif isinstance(obj, dict):
                lines.append(
                    "JSON object; top-level keys: " + ", ".join(list(obj.keys())[:_CARD_MAX_COLS])
                )
        else:
            # Unknown format: show the first text lines if it decodes at all.
            with open(path, encoding="utf-8", errors="replace") as f:
                head = [next(f, "").rstrip() for _ in range(3)]
            head = [h[:120] for h in head if h and h.isprintable()]
            if head:
                lines.append("First lines:")
                lines += [f"  {h}" for h in head]
    except Exception:
        lines.append("(contents not previewable)")

    # CDS/VizieR awareness: a ReadMe's byte-by-byte table is the AUTHORITATIVE
    # schema for the sibling fixed-width .dat files — parse it into an explicit
    # read_fwf recipe. (A live run parsed a .dat by whitespace-splitting and got
    # the right columns only by luck; masked values or spaced IDs would have
    # silently misaligned.)
    try:
        if path.name.lower().startswith("readme"):
            text = path.read_text(errors="replace")[:200_000]
            specs = parse_cds_readme(text)
            for fname, cols in list(specs.items())[:4]:
                lines.append(f"CDS byte-by-byte spec for {fname}:")
                lines += [
                    f"  {c['label']}: bytes {c['bytes']}"
                    + (f" [{c['unit']}]" if c["unit"] and c["unit"] != "---" else "")
                    + (f" — {c['explanation'][:60]}" if c["explanation"] else "")
                    for c in cols[:_CARD_MAX_COLS]
                ]
                lines.append("  Read it with (do NOT whitespace-split fixed-width files):")
                lines.append(f"  {cds_read_fwf_recipe(fname, cols)}")
        elif suffix == ".dat":
            readme = next((p for p in path.parent.glob("[Rr]ead[Mm]e*") if p.is_file()), None)
            if readme is not None:
                specs = parse_cds_readme(readme.read_text(errors="replace")[:200_000])
                cols = specs.get(path.name)
                if cols:
                    lines.append(
                        f"Fixed-width CDS table — schema in {readme.name}. Columns: "
                        + ", ".join(c["label"] for c in cols[:_CARD_MAX_COLS])
                    )
                    lines.append("  Read with (do NOT whitespace-split):")
                    lines.append(f"  {cds_read_fwf_recipe(path.name, cols)}")
    except Exception:
        pass  # the base card already stands

    card = "\n".join(lines)
    return card[:max_chars]


# CDS ReadMe "Byte-by-byte Description of file: <name>" table row, e.g.
#   "   1- 11  A11   ---     Name      Star name"
#   "  14- 18  F5.2  [K]     Teff      Effective temperature"
_CDS_ROW_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s+([AIFELX][\d.]*)\s+(\S+)\s+(\S+)\s*(.*)$")
_CDS_ROW_SINGLE_RE = re.compile(r"^\s*(\d+)\s+([AIFELX][\d.]*)\s+(\S+)\s+(\S+)\s*(.*)$")
_CDS_FILE_HEAD_RE = re.compile(r"Byte-by-byte Description of file:?\s*([^\s,]+)", re.IGNORECASE)


def parse_cds_readme(text: str) -> dict[str, list[dict[str, str]]]:
    """Parse a CDS ReadMe's byte-by-byte tables → {filename: [column specs]}.

    Each column spec is ``{"bytes": "1-11", "start": "1", "end": "11",
    "unit": ..., "label": ..., "explanation": ...}``. Best-effort: malformed
    sections yield fewer columns, never an exception.
    """
    specs: dict[str, list[dict[str, str]]] = {}
    current: str | None = None
    for line in text.splitlines():
        head = _CDS_FILE_HEAD_RE.search(line)
        if head:
            current = head.group(1).strip()
            specs[current] = []
            continue
        if current is None:
            continue
        m = _CDS_ROW_RE.match(line)
        if m:
            start, end, _fmt, unit, label, expl = m.groups()
            specs[current].append(
                {
                    "bytes": f"{start}-{end}",
                    "start": start,
                    "end": end,
                    "unit": unit,
                    "label": label,
                    "explanation": expl.strip(),
                }
            )
            continue
        m1 = _CDS_ROW_SINGLE_RE.match(line)
        if m1:
            pos, _fmt, unit, label, expl = m1.groups()
            specs[current].append(
                {
                    "bytes": pos,
                    "start": pos,
                    "end": pos,
                    "unit": unit,
                    "label": label,
                    "explanation": expl.strip(),
                }
            )
    return {k: v for k, v in specs.items() if v}


def cds_read_fwf_recipe(filename: str, cols: list[dict[str, str]]) -> str:
    """A ready-to-paste pandas ``read_fwf`` call for a CDS fixed-width table."""
    colspecs = ", ".join(f"({int(c['start']) - 1},{c['end']})" for c in cols)
    names = ", ".join(f"'{c['label']}'" for c in cols)
    return (
        f"pd.read_fwf('/data/shared/data/{filename}', "
        f"colspecs=[{colspecs}], names=[{names}], header=None)"
    )


def stage_local_dataset(path: Path, shared_dir: Path) -> list[ResolvedResource]:
    """Copy a local dataset file or directory into the sandbox-visible shared data
    dir and return DATA resources (with data-card summaries) for each staged file.

    Names are sanitized; collisions get a numeric suffix. A directory stages up to
    ``_STAGE_MAX_DIR_FILES`` regular files (flat copy of the tree). Raises
    ``FileNotFoundError`` for a missing path — callers decide how loud to be.
    """
    import shutil as _shutil

    src = Path(path).expanduser()
    if not src.exists():
        raise FileNotFoundError(f"Dataset path not found: {src}")

    data_dir = shared_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    def _dest_for(name: str) -> Path:
        base = _sanitize_dataset_name(name)
        dest = data_dir / base
        counter = 1
        while dest.exists():
            stem, dot, ext = base.partition(".")
            dest = data_dir / f"{stem}-{counter}{dot}{ext}"
            counter += 1
        return dest

    sources: list[Path]
    if src.is_dir():
        sources = sorted(p for p in src.rglob("*") if p.is_file())[:_STAGE_MAX_DIR_FILES]
    else:
        sources = [src]

    staged: list[ResolvedResource] = []
    for f in sources:
        dest = _dest_for(f.name)
        _shutil.copy2(f, dest)
        staged.append(
            ResolvedResource(
                url=f"file://{f}",
                resource_type=ResourceType.DATA,
                name=dest.name,
                local_path=str(dest),
                sandbox_path=f"/data/shared/data/{dest.name}",
                summary=f"Attached dataset '{dest.name}'",
                size_bytes=dest.stat().st_size,
            )
        )
    return staged
