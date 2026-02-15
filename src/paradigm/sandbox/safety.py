"""AST-based safety scanner for code execution."""

import ast
import re
import warnings
from dataclasses import dataclass, field

from paradigm.sandbox.models import SafetyVerdict

# Modules that are never allowed in sandbox code.
# Docker with --network=none is the primary security boundary.
# Only block modules that enable process spawning, C-level escape, or
# code generation that bypasses the safety scanner itself.
DENIED_MODULES: frozenset[str] = frozenset(
    {
        "subprocess",  # shell command execution
        "ctypes",  # C-level access, potential sandbox escape
        "multiprocessing",  # fork bombs / resource abuse
        "signal",  # process signal manipulation
    }
)

# Builtin functions/names that are never allowed.
# Block dynamic code execution (makes agent code un-auditable).
# File I/O (open, getattr, etc.) is safe inside Docker.
DENIED_BUILTINS: frozenset[str] = frozenset(
    {
        "exec",  # dynamic code execution
        "eval",  # dynamic expression evaluation
        "compile",  # code compilation
        "__import__",  # dynamic import bypass
        "breakpoint",  # no debugger in container
    }
)

# Modules that attempt network access in a --network=none sandbox.
# Unlike DENIED_MODULES (which block dangerous operations), these block
# operations that will always fail, saving Docker execution time.
NETWORK_MODULES: frozenset[str] = frozenset(
    {
        "requests",  # HTTP library — always needs network
        "httpx",  # HTTP library — always needs network
        "aiohttp",  # HTTP library — always needs network
        "ftplib",  # FTP library — always needs network
    }
)

# Catch urllib.request and http.client usage via regex.
# We don't block the full 'urllib' or 'http' modules since
# urllib.parse and http.server are harmless.
_NETWORK_REGEX_PATTERNS: list[tuple[str, str]] = [
    (r"urllib\.request", "urllib.request cannot work in the sandbox (no network access)"),
    (r"http\.client", "http.client cannot work in the sandbox (no network access)"),
    (
        r"socket\.create_connection|socket\.socket\(",
        "socket connections cannot work in the sandbox (no network access)",
    ),
]

# Maximum code length (characters) to prevent abuse
MAX_CODE_LENGTH: int = 50_000


@dataclass
class SafetyConfig:
    """Configuration for the safety scanner."""

    denied_modules: frozenset[str] = field(default_factory=lambda: DENIED_MODULES)
    denied_builtins: frozenset[str] = field(default_factory=lambda: DENIED_BUILTINS)
    max_code_length: int = MAX_CODE_LENGTH


class SafetyScanner:
    """Scans Python code for dangerous patterns before execution.

    Uses AST-based analysis as the primary defense, with regex
    fallback for edge cases that the AST parser might miss.
    """

    def __init__(self, config: SafetyConfig | None = None) -> None:
        self.config = config or SafetyConfig()

    def scan(self, code: str) -> SafetyVerdict:
        """Scan code for safety violations.

        Args:
            code: Python source code to scan.

        Returns:
            SafetyVerdict with safe=True if code passes all checks.
        """
        violations: list[str] = []

        # Check code length
        if len(code) > self.config.max_code_length:
            violations.append(
                f"Code exceeds maximum length ({len(code)} > {self.config.max_code_length} chars)"
            )
            return SafetyVerdict(safe=False, violations=violations)

        # Try to parse AST
        # Suppress SyntaxWarning from invalid escape sequences (e.g. \o in
        # LaTeX strings like $M_\odot$).  These are harmless in Python 3.12
        # but will become SyntaxError in 3.14 — the execution prompt already
        # instructs agents to use raw strings.
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = ast.parse(code)
        except SyntaxError as e:
            violations.append(f"Syntax error: {e.msg} (line {e.lineno})")
            return SafetyVerdict(safe=False, violations=violations)

        # AST-based checks
        self._check_imports(tree, violations)
        self._check_network_imports(tree, violations)
        self._check_builtins(tree, violations)

        # Regex fallback for patterns AST might miss
        self._check_regex_patterns(code, violations)

        return SafetyVerdict(safe=len(violations) == 0, violations=violations)

    def _check_imports(self, tree: ast.AST, violations: list[str]) -> None:
        """Check for denied module imports via AST."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top_module = alias.name.split(".")[0]
                    if top_module in self.config.denied_modules:
                        violations.append(f"Denied import: '{alias.name}'")

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    top_module = node.module.split(".")[0]
                    if top_module in self.config.denied_modules:
                        violations.append(f"Denied import: 'from {node.module}'")

    def _check_network_imports(self, tree: ast.AST, violations: list[str]) -> None:
        """Check for network module imports that will fail in --network=none sandbox."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top_module = alias.name.split(".")[0]
                    if top_module in NETWORK_MODULES:
                        violations.append(
                            f"Network module '{alias.name}' cannot work in the sandbox "
                            f"(no network access). Use synthetic data or files from "
                            f"/data/shared/ instead."
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    top_module = node.module.split(".")[0]
                    if top_module in NETWORK_MODULES:
                        violations.append(
                            f"Network module 'from {node.module}' cannot work in the "
                            f"sandbox (no network access). Use synthetic data or files "
                            f"from /data/shared/ instead."
                        )

    def _check_builtins(self, tree: ast.AST, violations: list[str]) -> None:
        """Check for denied builtin function calls via AST."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = self._get_call_name(node)
                if name and name in self.config.denied_builtins:
                    violations.append(f"Denied builtin: '{name}()'")

            # Also catch bare name references (e.g., passing exec as an argument)
            elif isinstance(node, ast.Name):
                if node.id in self.config.denied_builtins:
                    # Only flag if used in a call context — the Call check above
                    # handles direct calls; here we catch indirect references
                    # like `f = exec` or `map(exec, ...)`
                    # Simple heuristic: flag __import__ and exec even as bare names
                    if node.id in ("__import__", "exec", "eval", "compile"):
                        violations.append(f"Denied builtin reference: '{node.id}'")

    def _get_call_name(self, node: ast.Call) -> str | None:
        """Extract the function name from a Call node."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return None

    def _check_regex_patterns(self, code: str, violations: list[str]) -> None:
        """Regex fallback for patterns AST analysis might miss."""
        # Catch string-based imports like __import__('os')
        if re.search(r"__import__\s*\(", code):
            if not any("__import__" in v for v in violations):
                violations.append("Denied pattern: '__import__()' call detected")

        # Catch os.system-style calls via string manipulation
        if re.search(r'getattr\s*\(.+["\']system["\']\s*\)', code):
            violations.append("Denied pattern: getattr-based system call detected")

        # Catch network access patterns via stdlib modules
        for pattern, message in _NETWORK_REGEX_PATTERNS:
            if re.search(pattern, code):
                violations.append(message)
