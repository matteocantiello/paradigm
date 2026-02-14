"""Docker container management for sandboxed code execution."""

import asyncio
import time
from pathlib import Path

from docker.errors import ContainerError, DockerException, ImageNotFound

import docker
from paradigm.config import SandboxConfig
from paradigm.sandbox.models import ExecutionRequest, ExecutionResult, ExecutionStatus, OutputFile


class ContainerManager:
    """Manages Docker containers for code execution.

    All Docker SDK calls are wrapped in asyncio.to_thread() since
    the Docker SDK is synchronous but the project uses async.
    """

    def __init__(self, config: SandboxConfig) -> None:
        self.config = config
        self._client: docker.DockerClient | None = None

    async def _get_client(self) -> docker.DockerClient:
        """Get or create Docker client."""
        if self._client is None:
            self._client = await asyncio.to_thread(docker.from_env)
        return self._client

    async def ensure_image(self) -> bool:
        """Ensure the sandbox Docker image exists.

        Returns:
            True if image is available, False otherwise.
        """
        client = await self._get_client()
        try:
            await asyncio.to_thread(client.images.get, self.config.image_name)
            return True
        except ImageNotFound:
            return False

    async def build_image(self, dockerfile_path: Path) -> None:
        """Build the sandbox Docker image.

        Args:
            dockerfile_path: Path to the Dockerfile.

        Raises:
            DockerException: If the build fails.
        """
        client = await self._get_client()
        build_dir = str(dockerfile_path.parent)
        dockerfile_name = dockerfile_path.name
        await asyncio.to_thread(
            client.images.build,
            path=build_dir,
            dockerfile=dockerfile_name,
            tag=self.config.image_name,
            rm=True,
        )

    async def execute(
        self,
        request: ExecutionRequest,
        results_dir: Path,
        shared_dir: Path | None = None,
        environment: dict[str, str] | None = None,
    ) -> ExecutionResult:
        """Execute code in an isolated Docker container.

        Args:
            request: The execution request with code and metadata.
            results_dir: Directory where output files will be written.
            shared_dir: Optional read-only shared data directory.
            environment: Optional environment variables to set in the container.

        Returns:
            ExecutionResult with execution outcome.
        """
        client = await self._get_client()
        container = None
        start_time = time.monotonic()
        timeout = request.timeout or self.config.execution_timeout

        # Ensure results directory exists
        results_dir.mkdir(parents=True, exist_ok=True)

        # Write code to a temporary script file in results_dir
        script_path = results_dir / "script.py"
        script_path.write_text(request.code)

        # Set up volumes
        volumes: dict[str, dict[str, str]] = {
            str(results_dir): {"bind": "/data/results", "mode": "rw"},
        }
        if shared_dir and shared_dir.exists():
            volumes[str(shared_dir)] = {"bind": "/data/shared", "mode": "ro"}

        try:
            container = await asyncio.to_thread(
                client.containers.create,
                image=self.config.image_name,
                command=["python", "/data/results/script.py"],
                volumes=volumes,
                network_mode=self.config.network_mode,
                mem_limit=self.config.memory_limit,
                nano_cpus=int(self.config.cpu_limit * 1e9),
                user="sandbox",
                working_dir="/data/results",
                environment=environment or {},
                detach=True,
            )

            await asyncio.to_thread(container.start)

            # Wait for completion with timeout
            try:
                result = await asyncio.to_thread(container.wait, timeout=timeout)
                exit_code = result.get("StatusCode", -1)
            except Exception:
                # Timeout or other error — kill the container
                try:
                    await asyncio.to_thread(container.kill)
                except Exception:
                    pass
                duration = time.monotonic() - start_time
                return ExecutionResult(
                    request=request,
                    status=ExecutionStatus.TIMEOUT,
                    error_message=f"Execution timed out after {timeout}s",
                    duration_seconds=duration,
                )

            duration = time.monotonic() - start_time

            # Collect logs
            stdout = await asyncio.to_thread(container.logs, stdout=True, stderr=False)
            stderr = await asyncio.to_thread(container.logs, stdout=False, stderr=True)

            stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
            stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

            # Truncate output if needed
            max_size = self.config.max_output_size
            if len(stdout_str) > max_size:
                stdout_str = stdout_str[:max_size] + "\n... [truncated]"
            if len(stderr_str) > max_size:
                stderr_str = stderr_str[:max_size] + "\n... [truncated]"

            # Collect output files (anything created in results_dir that isn't script.py)
            output_files: list[OutputFile] = []
            for f in results_dir.iterdir():
                if f.name != "script.py" and f.is_file():
                    output_files.append(
                        OutputFile(
                            filename=f.name,
                            path=str(f),
                            size_bytes=f.stat().st_size,
                        )
                    )

            status = ExecutionStatus.SUCCESS if exit_code == 0 else ExecutionStatus.FAILURE
            return ExecutionResult(
                request=request,
                status=status,
                stdout=stdout_str,
                stderr=stderr_str,
                exit_code=exit_code,
                duration_seconds=duration,
                output_files=output_files,
            )

        except ImageNotFound:
            return ExecutionResult(
                request=request,
                status=ExecutionStatus.ERROR,
                error_message=f"Docker image not found: {self.config.image_name}",
                duration_seconds=time.monotonic() - start_time,
            )

        except (ContainerError, DockerException) as e:
            return ExecutionResult(
                request=request,
                status=ExecutionStatus.ERROR,
                error_message=f"Docker error: {e}",
                duration_seconds=time.monotonic() - start_time,
            )

        finally:
            if container is not None:
                try:
                    await asyncio.to_thread(container.remove, force=True)
                except Exception:
                    pass  # Best-effort cleanup

    async def cleanup(self) -> None:
        """Close the Docker client connection."""
        if self._client is not None:
            try:
                await asyncio.to_thread(self._client.close)
            except Exception:
                pass
            self._client = None
