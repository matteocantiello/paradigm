"""Tests for resource classification, resolution, and context building."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from paradigm.literature.resources import (
    ResolvedResource,
    ResourceType,
    _github_to_raw_url,
    _html_to_text,
    build_code_context,
    build_data_context,
    build_reference_context,
    classify_resource,
    resolve_resource,
)


class TestClassifyResource:
    """Tests for classify_resource() — URL pattern matching."""

    def test_arxiv_abs(self):
        assert classify_resource("https://arxiv.org/abs/2401.12345") == ResourceType.PAPER

    def test_arxiv_pdf(self):
        assert classify_resource("https://arxiv.org/pdf/2401.12345") == ResourceType.PAPER

    def test_direct_pdf(self):
        assert classify_resource("https://example.com/paper.pdf") == ResourceType.PAPER

    def test_github_repo_root(self):
        assert classify_resource("https://github.com/owner/repo") == ResourceType.CODE_REPO

    def test_github_repo_with_git(self):
        assert classify_resource("https://github.com/owner/repo.git") == ResourceType.CODE_REPO

    def test_github_repo_tree(self):
        url = "https://github.com/owner/repo/tree/main/src"
        assert classify_resource(url) == ResourceType.CODE_REPO

    def test_github_blob_py(self):
        url = "https://github.com/owner/repo/blob/main/script.py"
        assert classify_resource(url) == ResourceType.CODE_FILE

    def test_github_blob_csv(self):
        url = "https://github.com/owner/repo/blob/main/data.csv"
        assert classify_resource(url) == ResourceType.DATA

    def test_raw_githubusercontent_py(self):
        url = "https://raw.githubusercontent.com/owner/repo/main/lib.py"
        assert classify_resource(url) == ResourceType.CODE_FILE

    def test_raw_githubusercontent_fits(self):
        url = "https://raw.githubusercontent.com/owner/repo/main/data.fits"
        assert classify_resource(url) == ResourceType.DATA

    def test_zenodo(self):
        url = "https://zenodo.org/records/12345/files/dataset.tar.gz"
        assert classify_resource(url) == ResourceType.DATA

    def test_bare_csv(self):
        assert classify_resource("https://example.com/data.csv") == ResourceType.DATA

    def test_bare_ipynb(self):
        assert classify_resource("https://example.com/notebook.ipynb") == ResourceType.CODE_FILE

    def test_plain_html(self):
        assert classify_resource("https://docs.python.org/3/library/") == ResourceType.REFERENCE

    def test_unknown_url(self):
        assert classify_resource("https://example.com/page") == ResourceType.REFERENCE

    def test_github_blob_unknown_ext(self):
        """GitHub blob with unrecognized extension defaults to code_file."""
        url = "https://github.com/owner/repo/blob/main/README.md"
        assert classify_resource(url) == ResourceType.CODE_FILE


class TestGithubToRawUrl:
    """Tests for _github_to_raw_url()."""

    def test_blob_to_raw(self):
        url = "https://github.com/owner/repo/blob/main/src/lib.py"
        expected = "https://raw.githubusercontent.com/owner/repo/main/src/lib.py"
        assert _github_to_raw_url(url) == expected

    def test_non_blob_unchanged(self):
        url = "https://example.com/file.py"
        assert _github_to_raw_url(url) == url


class TestHtmlToText:
    """Tests for _html_to_text()."""

    def test_strips_script_style(self):
        html = "<html><script>var x=1;</script><style>.a{}</style><p>Hello</p></html>"
        text = _html_to_text(html)
        assert "var x" not in text
        assert ".a{}" not in text
        assert "Hello" in text

    def test_converts_block_tags(self):
        html = "<p>Para 1</p><p>Para 2</p>"
        text = _html_to_text(html)
        assert "Para 1" in text
        assert "Para 2" in text

    def test_decodes_entities(self):
        html = "<p>A &amp; B &lt; C</p>"
        text = _html_to_text(html)
        assert "A & B < C" in text


class TestBuildCodeContext:
    """Tests for build_code_context()."""

    def test_empty_returns_empty(self):
        assert build_code_context([]) == ""

    def test_no_code_resources(self):
        ref = ResolvedResource(
            url="https://example.com",
            resource_type=ResourceType.REFERENCE,
            name="example",
            content="text",
        )
        assert build_code_context([ref]) == ""

    def test_single_repo(self):
        repo = ResolvedResource(
            url="https://github.com/owner/mesa",
            resource_type=ResourceType.CODE_REPO,
            name="mesa",
            local_path="/tmp/data/shared/repos/mesa",
            sandbox_path="/data/shared/repos/mesa",
            summary="Cloned 'mesa': src, README.md",
        )
        result = build_code_context([repo])
        assert "Available Code Resources" in result
        assert "mesa" in result
        assert "/data/shared/repos/mesa" in result
        assert "import mesa" in result

    def test_filters_errored(self):
        errored = ResolvedResource(
            url="https://github.com/owner/bad",
            resource_type=ResourceType.CODE_REPO,
            name="bad",
            error="Clone failed",
        )
        assert build_code_context([errored]) == ""

    def test_code_file(self):
        code_file = ResolvedResource(
            url="https://example.com/plot.py",
            resource_type=ResourceType.CODE_FILE,
            name="plot.py",
            local_path="/tmp/code/plot.py",
            sandbox_path="/data/shared/code/plot.py",
            summary="Downloaded 'plot.py' (1234 bytes)",
        )
        result = build_code_context([code_file])
        assert "File: plot.py" in result
        assert "/data/shared/code/plot.py" in result


class TestBuildDataContext:
    """Tests for build_data_context()."""

    def test_empty_returns_empty(self):
        assert build_data_context([]) == ""

    def test_single_file_with_size(self):
        data = ResolvedResource(
            url="https://example.com/data.csv",
            resource_type=ResourceType.DATA,
            name="data.csv",
            local_path="/tmp/data/shared/data/data.csv",
            sandbox_path="/data/shared/data/data.csv",
            size_bytes=2048,
        )
        result = build_data_context([data])
        assert "Available Data Files" in result
        assert "data.csv" in result
        assert "2.0 KB" in result

    def test_large_file_shows_mb(self):
        data = ResolvedResource(
            url="https://example.com/model.hdf5",
            resource_type=ResourceType.DATA,
            name="model.hdf5",
            local_path="/tmp/data.hdf5",
            sandbox_path="/data/shared/data/model.hdf5",
            size_bytes=50 * 1024 * 1024,
        )
        result = build_data_context([data])
        assert "50.0 MB" in result

    def test_filters_errored(self):
        errored = ResolvedResource(
            url="https://example.com/huge.fits",
            resource_type=ResourceType.DATA,
            name="huge.fits",
            error="File too large",
        )
        assert build_data_context([errored]) == ""


class TestBuildReferenceContext:
    """Tests for build_reference_context()."""

    def test_empty_returns_empty(self):
        assert build_reference_context([]) == ""

    def test_single_reference(self):
        ref = ResolvedResource(
            url="https://docs.astropy.org/en/stable/",
            resource_type=ResourceType.REFERENCE,
            name="docs.astropy.org",
            content="Astropy is a community-developed Python package for astronomy.",
        )
        result = build_reference_context([ref])
        assert "Web Reference Materials" in result
        assert "docs.astropy.org" in result
        assert "Astropy" in result

    def test_truncates_long_content(self):
        ref = ResolvedResource(
            url="https://example.com",
            resource_type=ResourceType.REFERENCE,
            name="example.com",
            content="A" * 10_000,
        )
        result = build_reference_context([ref])
        assert "(truncated)" in result

    def test_filters_no_content(self):
        ref = ResolvedResource(
            url="https://example.com",
            resource_type=ResourceType.REFERENCE,
            name="example.com",
            content=None,
        )
        assert build_reference_context([ref]) == ""


class TestResolveResource:
    """Tests for resolve_resource() with mocked I/O."""

    @pytest.mark.asyncio
    async def test_resolve_code_repo(self, tmp_path):
        """Code repo resolution runs git clone."""
        shared_dir = tmp_path / "shared"
        logger = MagicMock()

        # Pre-create the clone target with some fake files (simulates git clone output)
        repos_dir = shared_dir / "repos" / "mesa"
        repos_dir.mkdir(parents=True)
        (repos_dir / "README.md").write_text("# MESA")
        (repos_dir / "src").mkdir()

        with patch("paradigm.literature.resources.asyncio.create_subprocess_exec") as mock_exec:
            proc = AsyncMock()
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(b"Cloning...", b""))
            mock_exec.return_value = proc

            result = await resolve_resource(
                "https://github.com/MESAHub/mesa",
                ResourceType.CODE_REPO,
                shared_dir,
                logger,
            )

        assert result.resource_type == ResourceType.CODE_REPO
        assert result.name == "mesa"
        assert result.sandbox_path == "/data/shared/repos/mesa"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_resolve_code_repo_clone_fail(self, tmp_path):
        """Failed git clone returns error in resource."""
        shared_dir = tmp_path / "shared"
        logger = MagicMock()

        with patch("paradigm.literature.resources.asyncio.create_subprocess_exec") as mock_exec:
            proc = AsyncMock()
            proc.returncode = 128
            proc.communicate = AsyncMock(return_value=(b"", b"fatal: repo not found"))
            mock_exec.return_value = proc

            result = await resolve_resource(
                "https://github.com/owner/nonexistent",
                ResourceType.CODE_REPO,
                shared_dir,
                logger,
            )

        assert result.error is not None
        assert "repo not found" in result.error

    @pytest.mark.asyncio
    async def test_resolve_code_file(self, tmp_path):
        """Code file resolution downloads via httpx."""
        shared_dir = tmp_path / "shared"
        logger = MagicMock()

        mock_response = MagicMock()
        mock_response.content = b"import numpy as np\nprint('hello')\n"
        mock_response.raise_for_status = MagicMock()

        with patch("paradigm.literature.resources.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await resolve_resource(
                "https://github.com/owner/repo/blob/main/plot.py",
                ResourceType.CODE_FILE,
                shared_dir,
                logger,
            )

        assert result.resource_type == ResourceType.CODE_FILE
        assert result.name == "plot.py"
        assert result.sandbox_path == "/data/shared/code/plot.py"
        assert result.error is None
        # File should have been written
        assert (shared_dir / "code" / "plot.py").exists()

    @pytest.mark.asyncio
    async def test_resolve_reference(self):
        """Reference resolution fetches HTML and strips tags."""
        logger = MagicMock()

        mock_response = MagicMock()
        mock_response.text = "<html><body><p>Important docs</p></body></html>"
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status = MagicMock()

        with patch("paradigm.literature.resources.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await resolve_resource(
                "https://docs.example.com/guide",
                ResourceType.REFERENCE,
                Path("/unused"),
                logger,
            )

        assert result.resource_type == ResourceType.REFERENCE
        assert "Important docs" in (result.content or "")
        assert result.error is None

    @pytest.mark.asyncio
    async def test_resolve_data_file(self, tmp_path):
        """Data file resolution downloads and checks size."""
        shared_dir = tmp_path / "shared"
        logger = MagicMock()

        # Mock streaming response
        mock_response = MagicMock()
        mock_response.headers = {"content-length": "100"}
        mock_response.raise_for_status = MagicMock()

        async def aiter_bytes():
            yield b"col1,col2\n1,2\n3,4\n"

        mock_response.aiter_bytes = aiter_bytes

        with patch("paradigm.literature.resources.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.stream = MagicMock()

            # Set up the context manager chain: client.stream("GET", ...) -> response
            stream_cm = AsyncMock()
            stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
            stream_cm.__aexit__ = AsyncMock(return_value=False)
            mock_client.stream.return_value = stream_cm

            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await resolve_resource(
                "https://example.com/data.csv",
                ResourceType.DATA,
                shared_dir,
                logger,
            )

        assert result.resource_type == ResourceType.DATA
        assert result.name == "data.csv"
        assert result.sandbox_path == "/data/shared/data/data.csv"
        assert result.error is None
        assert (shared_dir / "data" / "data.csv").exists()

    @pytest.mark.asyncio
    async def test_resolve_catches_exception(self, tmp_path):
        """Exceptions during resolution are captured, not raised."""
        shared_dir = tmp_path / "shared"
        logger = MagicMock()

        with patch("paradigm.literature.resources.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await resolve_resource(
                "https://example.com/broken.py",
                ResourceType.CODE_FILE,
                shared_dir,
                logger,
            )

        assert result.error is not None


# Need httpx import for the exception test
import httpx  # noqa: E402
