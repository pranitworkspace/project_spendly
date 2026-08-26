"""Root conftest.

Its presence puts the project root on sys.path, so tests can import the
`database` package and `app` the same way the running application does.

The `temp_db` fixture lives here rather than in tests/ so that isolation is
unconditional — any test file anywhere in the repo gets a throwaway database,
not the developer's real expense_tracker.db.
"""

import pytest

import database.db as db


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Point the data layer at a throwaway database for the duration of a test."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    return db.DB_PATH
