from unittest.mock import Mock

import pytest
from mcp.server.mcpserver import Context

from globus_mcp.core.context import GlobusContext
from globus_mcp.core.filesystem import resolve_filesystem_root
from tests.utils import random_string


@pytest.fixture(autouse=True)
def _clear_filesystem_root_cache():
    """resolve_filesystem_root() is memoized with @cache. It's called (indirectly, via
    main()/lifespan()/register_transfer()) from tests across multiple files, not just
    test_filesystem.py, so this must be repo-wide and autouse — a stale cached value
    from one test leaking into another is a real risk, not a hypothetical one."""
    resolve_filesystem_root.cache_clear()
    yield
    resolve_filesystem_root.cache_clear()


@pytest.fixture
def mock_app():
    app = Mock()
    app.config.environment = "sandbox"
    app.token_storage.identity_id = None
    return app


@pytest.fixture
def mock_ctx(mock_app: Mock):
    ctx = Mock(spec=Context)
    ctx.request_id = random_string()
    ctx.request_context.lifespan_context = GlobusContext(
        app=mock_app, server_session_id=random_string()
    )
    return ctx
