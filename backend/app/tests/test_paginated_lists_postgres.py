"""Run the HTTP paging contract against the existing isolated PG schema fixture.

Without an explicit integration URL these cases skip rather than use a developer
database. matching_db creates, checks and drops only its random cp_test_* schema.
"""

import os

import pytest

from app.tests import test_real_matching as matching_fixtures
from app.tests.test_z57_pagination import (  # noqa: F401 - pytest collects these cases
    test_equal_timestamps_order_stably_without_duplicates,
    test_exact_last_page_clamping_empty_and_query_bounds,
    test_growth_page_counts_rows_it_could_not_read_without_widening_catches,
    test_job_candidates_page_excludes_withdrawn_and_denies_non_managers,
    test_job_filter_applies_before_count_and_stays_owner_scoped,
    test_match_report_history_pages_with_default_twenty,
    test_notification_page_size_aliases_and_conflict,
    test_owned_applications_page_reaches_past_the_first_hundred,
)

# Explicit fixture export is independent of whether pytest first collected the
# shared module as an ordinary test module or imported it as a plugin.
matching_db = matching_fixtures.matching_db
pytestmark = pytest.mark.skipif(
    not os.environ.get("CAREERPROOF_TEST_DATABASE_URL", "").startswith("postgresql+asyncpg://"),
    reason="requires an explicit isolated PostgreSQL integration database",
)


@pytest.fixture
async def jobs_db(matching_db):
    # Override Z57's SQLite fixture for the seven cases that use jobs_db.
    return matching_db
