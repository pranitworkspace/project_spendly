"""Fixtures for the HTTP-level tests.

`temp_db` (root conftest.py) is autouse, but this fixture requests it by name
anyway: that guarantees DB_PATH is already patched the first time `app` is
imported, since importing app runs init_db()/seed_db() at module scope.
"""

import pytest

import database.db as db


@pytest.fixture
def client(temp_db):
    """A Flask test client talking to a freshly seeded throwaway database."""
    import app as app_module

    # `app` is imported once per session; DB_PATH is re-pointed per test, so
    # rebuild the schema and demo data every time. Both calls are idempotent.
    db.init_db()
    db.seed_db()

    app_module.app.config.update(TESTING=True)
    with app_module.app.test_client() as test_client:
        yield test_client
