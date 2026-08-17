"""
tests/test_ingest.py
=====================
Unit tests for `lake/ingest.py`.

These tests build small in-memory Polars DataFrames by hand instead of
reading the real generated CSVs — that keeps them fast (no disk I/O,
no dependency on having run generate_data.py) and, more importantly,
lets each test control exactly which edge case it's checking, instead
of hoping the random synthetic data happens to contain that case.

Run (from the project root):
    pytest tests/test_ingest.py -v
"""

import polars as pl
import pytest

from lake.ingest import check_referential_integrity, parse_messy_date


class TestParseMessyDate:
    """`parse_messy_date` must handle every format generate_data.py can
    produce, and fail safely (return None) on anything else."""

    def test_iso_format(self):
        assert parse_messy_date("2024-03-05").isoformat() == "2024-03-05"

    def test_us_slash_format(self):
        assert parse_messy_date("03/05/2024").isoformat() == "2024-03-05"

    def test_day_month_abbrev_format(self):
        assert parse_messy_date("05-Mar-2024").isoformat() == "2024-03-05"

    def test_year_slash_format(self):
        assert parse_messy_date("2024/03/05").isoformat() == "2024-03-05"

    def test_unparseable_returns_none(self):
        assert parse_messy_date("not-a-date") is None

    def test_none_input_returns_none(self):
        assert parse_messy_date(None) is None

    def test_empty_string_returns_none(self):
        assert parse_messy_date("") is None


class TestReferentialIntegrity:
    """Orders that reference a customer/product/store_id absent from the
    cleaned dimensions must be split out, not silently kept or dropped."""

    @pytest.fixture
    def dimensions(self):
        customers = pl.DataFrame({"customer_id": [1, 2, 3]})
        products = pl.DataFrame({"product_id": [10, 20]})
        stores = pl.DataFrame({"store_id": [100]})
        return customers, products, stores

    def test_all_valid_fks_pass_through(self, dimensions):
        customers, products, stores = dimensions
        orders = pl.DataFrame({
            "order_id": [1, 2],
            "customer_id": [1, 2],
            "product_id": [10, 20],
            "store_id": [100, 100],
        })
        valid, orphans = check_referential_integrity(orders, customers, products, stores)
        assert valid.height == 2
        assert orphans.height == 0

    def test_orphan_customer_id_is_quarantined(self, dimensions):
        customers, products, stores = dimensions
        orders = pl.DataFrame({
            "order_id": [1, 2],
            "customer_id": [1, 999],  # 999 doesn't exist
            "product_id": [10, 20],
            "store_id": [100, 100],
        })
        valid, orphans = check_referential_integrity(orders, customers, products, stores)
        assert valid.height == 1
        assert orphans.height == 1
        assert orphans["order_id"].to_list() == [2]

    def test_orphan_rows_are_tagged_with_reason(self, dimensions):
        customers, products, stores = dimensions
        orders = pl.DataFrame({
            "order_id": [1],
            "customer_id": [1],
            "product_id": [999],  # doesn't exist
            "store_id": [100],
        })
        _, orphans = check_referential_integrity(orders, customers, products, stores)
        assert orphans["rejection_reason"].to_list() == ["orphan_foreign_key"]


class TestOrderQuantityValidation:
    """These mirror the validity rule used inside clean_orders: a row is
    only usable if quantity is present and positive."""

    def test_positive_quantity_is_valid(self):
        df = pl.DataFrame({"quantity": [1, 5, 100]})
        assert df.filter(pl.col("quantity") > 0).height == 3

    def test_null_quantity_is_invalid(self):
        df = pl.DataFrame({"quantity": [1, None, 5]})
        assert df.filter(pl.col("quantity").is_null()).height == 1

    def test_negative_quantity_is_invalid(self):
        df = pl.DataFrame({"quantity": [1, -3, 5]})
        assert df.filter(pl.col("quantity") <= 0).height == 1

    def test_zero_quantity_is_invalid(self):
        df = pl.DataFrame({"quantity": [0]})
        assert df.filter(pl.col("quantity") > 0).height == 0
