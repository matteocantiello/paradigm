"""AST-based safety scanner for code execution."""

import ast
import re
from dataclasses import dataclass, field

from paradigm.sandbox.models import SafetyVerdict

# Modules that are never allowed in sandbox code
DENIED_MODULES: frozenset[str] = frozenset(
    {
        "subprocess",
        "os",
        "sys",
        "shutil",
        "socket",
        "http",
        "urllib",
        "requests",
        "ctypes",
        "multiprocessing",
        "pickle",
        "shelve",
        "tempfile",
        "signal",
        "threading",
        "webbrowser",
        "code",
        "codeop",
        "compileall",
        "importlib",
        "runpy",
        "pathlib",
        "glob",
        "fnmatch",
        "io",
    }
)

# Builtin functions/names that are never allowed
DENIED_BUILTINS: frozenset[str] = frozenset(
    {
        "exec",
        "eval",
        "compile",
        "__import__",
        "open",
        "breakpoint",
        "globals",
        "locals",
        "vars",
        "dir",
        "getattr",
        "setattr",
        "delattr",
    }
)

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
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            violations.append(f"Syntax error: {e.msg} (line {e.lineno})")
            return SafetyVerdict(safe=False, violations=violations)

        # AST-based checks
        self._check_imports(tree, violations)
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
