#!/usr/bin/env python3
"""Verify Phase 0 setup is complete."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


def verify_structure():
    """Verify directory structure exists."""
    print("Checking directory structure...")

    required_dirs = [
        "src/paradigm",
        "src/paradigm/orchestrator",
        "src/paradigm/agents",
        "src/paradigm/agents/prompts",
        "src/paradigm/literature",
        "src/paradigm/sandbox",
        "src/paradigm/journal",
        "src/paradigm/storage",
        "src/paradigm/logging",
        "tests",
        "docker",
        "configs",
        "data",
    ]

    for dir_path in required_dirs:
        if not Path(dir_path).exists():
            print(f"  ✗ Missing: {dir_path}")
            return False
        print(f"  ✓ {dir_path}")

    return True


def verify_files():
    """Verify required files exist."""
    print("\nChecking required files...")

    required_files = [
        "pyproject.toml",
        "src/paradigm/__init__.py",
        "src/paradigm/__main__.py",
        "src/paradigm/main.py",
        "src/paradigm/config.py",
        "src/paradigm/storage/database.py",
        "src/paradigm/agents/base.py",
        "src/paradigm/logging/events.py",
        "configs/default.yaml",
        "tests/test_config.py",
        "tests/test_database.py",
        "tests/test_logging.py",
        "tests/test_agents.py",
    ]

    for file_path in required_files:
        if not Path(file_path).exists():
            print(f"  ✗ Missing: {file_path}")
            return False
        print(f"  ✓ {file_path}")

    return True


def verify_imports():
    """Verify core modules can be imported."""
    print("\nChecking imports...")

    try:
        import paradigm
        print(f"  ✓ paradigm (version {paradigm.__version__})")
    except ImportError as e:
        print(f"  ✗ Failed to import paradigm: {e}")
        return False

    try:
        from paradigm.storage.database import Database
        print("  ✓ paradigm.storage.database.Database")
    except ImportError as e:
        print(f"  ✗ Failed to import Database: {e}")
        return False

    # Note: Other imports require pydantic and other dependencies
    print("  ℹ Other imports require dependencies (install with pip install -e '.[dev]')")

    return True


def main():
    """Run all verification checks."""
    print("=" * 60)
    print("PARADIGM PHASE 0 SETUP VERIFICATION")
    print("=" * 60)

    checks = [
        ("Directory structure", verify_structure),
        ("Required files", verify_files),
        ("Basic imports", verify_imports),
    ]

    results = []
    for name, check in checks:
        try:
            result = check()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ {name} failed with error: {e}")
            results.append((name, False))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")

    all_passed = all(result for _, result in results)

    if all_passed:
        print("\n🎉 Phase 0 setup is complete!")
        print("\nNext steps:")
        print("1. Install dependencies: pip install -e '.[dev]'")
        print("2. Set ANTHROPIC_API_KEY environment variable")
        print("3. Run tests: pytest tests/")
        print("4. Try CLI: python -m paradigm --help")
        return 0
    else:
        print("\n❌ Some checks failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
