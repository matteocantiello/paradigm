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
