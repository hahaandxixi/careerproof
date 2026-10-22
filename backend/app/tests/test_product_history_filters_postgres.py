"""Same endpoint contracts on an explicitly allocated disposable PG schema."""

import os

import pytest

from app.tests import test_real_matching as shared_matching
from app.tests.test_product_history_filters import (  # noqa: F401 - collected cases
    test_application_views_and_keyword_count_across_pages,
    test_enterprise_filters_use_same_snapshot_item_before_count_and_page,
    test_report_history_search_is_owned_global_and_preserves_material_versions,
)

matching_db = shared_matching.matching_db
pytestmark = pytest.mark.skipif(
    not os.environ.get("CAREERPROOF_TEST_DATABASE_URL", "").startswith("postgresql+asyncpg://"),
    reason="requires an explicit isolated PostgreSQL integration database",
)


@pytest.fixture
async def jobs_db(matching_db):
    return matching_db
