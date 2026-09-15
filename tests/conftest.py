# ABOUTME: Shared pytest fixtures, including the golden-file comparison used by characterisation tests.
# ABOUTME: Run pytest with --update-golden to rewrite golden files after a deliberate output change.
from collections.abc import Callable
from pathlib import Path

import pytest

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-golden",
        action="store_true",
        help="rewrite golden files from the current output instead of comparing against them",
    )


@pytest.fixture
def golden(request: pytest.FixtureRequest) -> Callable[[str, str], None]:
    """Return a function that compares text with tests/golden/<name>, or rewrites it with --update-golden."""
    update = request.config.getoption("--update-golden")

    def check(name: str, actual: str) -> None:
        path = GOLDEN_DIR / name
        if update:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(actual, encoding="utf-8", newline="")
            return
        assert path.exists(), f"missing golden file {path}; run `uv run pytest --update-golden` to create it"
        assert actual == path.read_text(encoding="utf-8", newline=""), f"output differs from golden file {path}"

    return check
