"""
tests/test_load.py
===================
Unit tests for the pure/deterministic helper functions in `warehouse/load.py`.

Deliberately NOT included here: tests that hit a real Postgres database
(load_dim_customers, load_fact_sales, etc.) — those are integration
concerns, not unit tests, and belong behind a docker-compose-backed test
database (see the README's "Testing" section for how to run those
separately). What's tested here is the logic that doesn't need a live
DB connection at all: config placeholder resolution and calendar math.

Run (from the project root):
    pytest tests/test_load.py -v
"""

import os
from datetime import date

from warehouse.load import resolve_env_placeholder, DAY_NAMES, MONTH_NAMES


class TestResolveEnvPlaceholder:
    def test_plain_value_passes_through_unchanged(self):
        assert resolve_env_placeholder("localhost") == "localhost"

    def test_placeholder_uses_default_when_env_var_unset(self):
        os.environ.pop("DW_TEST_VAR", None)
        assert resolve_env_placeholder("${DW_TEST_VAR:fallback}") == "fallback"

    def test_placeholder_uses_env_var_when_set(self):
        os.environ["DW_TEST_VAR"] = "overridden"
        try:
            assert resolve_env_placeholder("${DW_TEST_VAR:fallback}") == "overridden"
        finally:
            del os.environ["DW_TEST_VAR"]

    def test_non_string_value_passes_through_unchanged(self):
        assert resolve_env_placeholder(5432) == 5432


class TestCalendarConstants:
    """These back the dim_date generation — a bug here would silently
    mislabel every row in the date dimension, so it's worth pinning down."""

    def test_day_names_align_with_python_weekday_numbering(self):
        # date.weekday(): Monday=0 ... Sunday=6, same order load.py assumes.
        assert DAY_NAMES[date(2024, 1, 1).weekday()] == "Monday"  # 2024-01-01 was a Monday
        assert DAY_NAMES[date(2024, 1, 7).weekday()] == "Sunday"

    def test_month_names_align_with_month_number(self):
        assert MONTH_NAMES[0] == "January"
        assert MONTH_NAMES[11] == "December"

    def test_quarter_math(self):
        # Mirrors the (month - 1) // 3 + 1 formula used in load_dim_date.
        assert (1 - 1) // 3 + 1 == 1
        assert (4 - 1) // 3 + 1 == 2
        assert (9 - 1) // 3 + 1 == 3
        assert (12 - 1) // 3 + 1 == 4
