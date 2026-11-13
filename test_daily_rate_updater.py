"""
test_daily_rate_updater.py
==========================
Isolated test suite for the daily_rate_updater module.

All tests use a temporary SQLite database — the real currency_tracker.db
is never touched.  The Frankfurter API is mocked throughout; no network
access is required.
"""

import os
import sys
import sqlite3
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, call

# ---------------------------------------------------------------------------
# Path setup — both files live in the same directory
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import database
import daily_rate_updater as updater

# ---------------------------------------------------------------------------
# Helper: temporary isolated database
# ---------------------------------------------------------------------------

class _TempDB:
    """Context manager that patches database.DATABASE_NAME to a temp file."""

    def __enter__(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._orig = database.DATABASE_NAME
        database.DATABASE_NAME = self._tmp.name
        database.create_database()
        return self._tmp.name

    def __exit__(self, *_):
        database.DATABASE_NAME = self._orig
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass


def _make_response(status_code: int, json_data=None, raise_exc=None):
    """Build a mock requests.Response-like object."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data or []
    mock_resp.text = str(json_data)
    if raise_exc:
        mock_resp.raise_for_status.side_effect = raise_exc
    return mock_resp


def _api_data(dates_rates: list[tuple]) -> list[dict]:
    """Shorthand for Frankfurter-style list of observations."""
    return [{"date": d, "base": "USD", "quote": "INR", "rate": r}
            for d, r in dates_rates]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDailyRateUpdater(unittest.TestCase):

    # ------------------------------------------------------------------
    # 1. Already up-to-date — no API call made
    # ------------------------------------------------------------------
    def test_01_skips_when_already_up_to_date(self):
        """If latest stored date == today, the currency is skipped (no API call)."""
        today = datetime.now().strftime("%Y-%m-%d")
        with _TempDB():
            database.save_historical_rates_batch([
                (today, "USD", "INR", 84.0)
            ])
            with patch("requests.get") as mock_get:
                result = updater._fetch_missing_rates("USD", "INR")
            mock_get.assert_not_called()
        self.assertTrue(result["skipped"])
        self.assertEqual(result["records_saved"], 0)
        self.assertIsNone(result["error"])

    # ------------------------------------------------------------------
    # 2. Fetches only missing dates
    # ------------------------------------------------------------------
    def test_02_fetches_only_missing_dates(self):
        """The API is called with fetch_from = latest_stored + 1 day."""
        stored_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        expected_from = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")

        with _TempDB():
            database.save_historical_rates_batch([
                (stored_date, "USD", "INR", 84.0)
            ])
            mock_resp = _make_response(200, _api_data([
                (expected_from, 84.1),
                (today, 84.2),
            ]))
            with patch("requests.get", return_value=mock_resp) as mock_get:
                result = updater._fetch_missing_rates("USD", "INR")

        # Verify the URL contains the correct from= parameter
        called_url = mock_get.call_args[0][0]
        self.assertIn(f"from={expected_from}", called_url)
        self.assertEqual(result["records_saved"], 2)
        self.assertFalse(result["skipped"])
        self.assertIsNone(result["error"])

    # ------------------------------------------------------------------
    # 3. Empty API response (weekend / holiday) — no DB write, no error
    # ------------------------------------------------------------------
    def test_03_handles_empty_api_response(self):
        """An empty response (holiday/weekend) is logged but causes no error."""
        stored_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        with _TempDB():
            database.save_historical_rates_batch([
                (stored_date, "EUR", "INR", 90.0)
            ])
            mock_resp = _make_response(200, [])
            with patch("requests.get", return_value=mock_resp):
                result = updater._fetch_missing_rates("EUR", "INR")

        self.assertFalse(result["skipped"])
        self.assertEqual(result["records_saved"], 0)
        self.assertIsNone(result["error"])

    # ------------------------------------------------------------------
    # 4. HTTP 429 rate-limit triggers retry and eventually succeeds
    # ------------------------------------------------------------------
    def test_04_retries_on_429_then_succeeds(self):
        """Two 429 responses followed by 200 — the third attempt succeeds."""
        stored_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        resp_429 = _make_response(429)
        resp_ok = _make_response(200, _api_data([(yesterday, 85.0)]))

        with _TempDB():
            database.save_historical_rates_batch([
                (stored_date, "GBP", "INR", 100.0)
            ])
            with patch("requests.get", side_effect=[resp_429, resp_429, resp_ok]):
                with patch("time.sleep"):  # skip real waits in tests
                    result = updater._fetch_missing_rates("GBP", "INR")

        self.assertEqual(result["records_saved"], 1)
        self.assertIsNone(result["error"])

    # ------------------------------------------------------------------
    # 5. All retries exhausted — error reported, script does not crash
    # ------------------------------------------------------------------
    def test_05_reports_error_after_all_retries_exhausted(self):
        """If all MAX_RETRIES fail, error is returned — no exception raised."""
        stored_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        resp_500 = _make_response(500, [])

        with _TempDB():
            database.save_historical_rates_batch([
                (stored_date, "JPY", "INR", 0.60)
            ])
            with patch("requests.get", return_value=resp_500):
                with patch("time.sleep"):
                    result = updater._fetch_missing_rates("JPY", "INR")

        self.assertIsNotNone(result["error"])
        self.assertEqual(result["records_saved"], 0)

    # ------------------------------------------------------------------
    # 6. Network exception — handled gracefully, script continues
    # ------------------------------------------------------------------
    def test_06_handles_network_exception_gracefully(self):
        """A ConnectionError is caught; error is reported without crashing."""
        import requests as req_module
        stored_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")

        with _TempDB():
            database.save_historical_rates_batch([
                (stored_date, "AED", "INR", 23.0)
            ])
            with patch("requests.get",
                       side_effect=req_module.exceptions.ConnectionError("no network")):
                with patch("time.sleep"):
                    result = updater._fetch_missing_rates("AED", "INR")

        self.assertIsNotNone(result["error"])
        self.assertEqual(result["records_saved"], 0)

    # ------------------------------------------------------------------
    # 7. Actual API observation dates are stored verbatim
    # ------------------------------------------------------------------
    def test_07_stores_actual_api_observation_dates(self):
        """Dates come from the API response, not the wall-clock."""
        # The API returns a Friday date even though today might be Monday
        api_date = "2026-11-06"  # a Friday

        with _TempDB() as db_path:
            mock_resp = _make_response(200, _api_data([(api_date, 84.5)]))
            with patch("requests.get", return_value=mock_resp):
                updater._fetch_missing_rates("USD", "INR")

            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute(
                "SELECT date FROM exchange_rates WHERE base_currency='USD' AND rate=84.5"
            )
            row = cur.fetchone()
            conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], api_date)

    # ------------------------------------------------------------------
    # 8. Idempotent — running twice with the same data inserts one row
    # ------------------------------------------------------------------
    def test_08_idempotent_double_run(self):
        """Running the updater twice on the same day does not duplicate rows.

        Strategy: pre-seed today's date so the first call is already up-to-date,
        then confirm the same row is upserted (not duplicated) when re-inserted
        directly via save_historical_rates_batch. The key invariant is that the
        UNIQUE index prevents a second row for the same (date, base, target).
        """
        today = datetime.now().strftime("%Y-%m-%d")

        with _TempDB() as db_path:
            # First insert
            database.save_historical_rates_batch([
                (today, "USD", "INR", 84.0)
            ])
            # Second insert with the same date — idempotent upsert should not add a row
            database.save_historical_rates_batch([
                (today, "USD", "INR", 84.0)
            ])
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM exchange_rates WHERE date=?", (today,))
            count = cur.fetchone()[0]
            conn.close()

        # Only 1 row despite two identical inserts
        self.assertEqual(count, 1)

        # Also confirm that _fetch_missing_rates skips the API when already up-to-date
        with _TempDB():
            database.save_historical_rates_batch([(today, "USD", "INR", 84.0)])
            with patch("requests.get") as mock_get:
                result = updater._fetch_missing_rates("USD", "INR")
            mock_get.assert_not_called()
            self.assertTrue(result["skipped"])

    # ------------------------------------------------------------------
    # 9. --dry-run does NOT write to database
    # ------------------------------------------------------------------
    def test_09_dry_run_does_not_write_to_db(self):
        """With dry_run=True, no rows are inserted even when API returns data."""
        stored_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        with _TempDB() as db_path:
            database.save_historical_rates_batch([
                (stored_date, "USD", "INR", 84.0)
            ])
            mock_resp = _make_response(200, _api_data([(yesterday, 84.5)]))
            with patch("requests.get", return_value=mock_resp):
                result = updater._fetch_missing_rates("USD", "INR", dry_run=True)

            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM exchange_rates WHERE date=?", (yesterday,))
            count = cur.fetchone()[0]
            conn.close()

        self.assertEqual(count, 0)
        self.assertEqual(result["records_saved"], 0)

    # ------------------------------------------------------------------
    # 10. Monthly average is recalculated after new daily rows are saved
    # ------------------------------------------------------------------
    def test_10_monthly_average_recalculated_after_insert(self):
        """After inserting daily rows, monthly_exchange_rates is updated."""
        this_year = datetime.now().year
        this_month = datetime.now().month
        base_date = f"{this_year}-{this_month:02d}-01"
        stored_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        # Build a date in the current month that is in the past
        obs_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        with _TempDB() as db_path:
            database.save_historical_rates_batch([
                (stored_date, "USD", "INR", 84.0)
            ])
            mock_resp = _make_response(200, _api_data([(obs_date, 85.0)]))
            with patch("requests.get", return_value=mock_resp):
                updater._fetch_missing_rates("USD", "INR")

            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute(
                "SELECT average_rate FROM monthly_exchange_rates "
                "WHERE base_currency='USD' AND year=? AND month=?",
                (this_year, this_month)
            )
            row = cur.fetchone()
            conn.close()

        self.assertIsNotNone(row, "Monthly record should exist after update")
        self.assertGreater(row[0], 0)

    # ------------------------------------------------------------------
    # 11. No existing data — defaults to 90-day lookback
    # ------------------------------------------------------------------
    def test_11_no_existing_data_fetches_90_day_default(self):
        """With no prior data the fetch_from is 90 days ago."""
        expected_from = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")

        with _TempDB():
            mock_resp = _make_response(200, _api_data([(today, 84.0)]))
            with patch("requests.get", return_value=mock_resp) as mock_get:
                updater._fetch_missing_rates("USD", "INR")

        called_url = mock_get.call_args[0][0]
        self.assertIn(f"from={expected_from}", called_url)

    # ------------------------------------------------------------------
    # 12. run() processes all 5 currencies and returns one result per pair
    # ------------------------------------------------------------------
    def test_12_run_processes_all_currencies(self):
        """run() returns a summary entry for each configured currency."""
        today = datetime.now().strftime("%Y-%m-%d")

        # Seed all currencies as already up-to-date
        with _TempDB():
            for currency in updater.CURRENCIES:
                database.save_historical_rates_batch([
                    (today, currency, updater.TARGET, 84.0)
                ])
            with patch("time.sleep"):
                results = updater.run()

        self.assertEqual(len(results), len(updater.CURRENCIES))
        for r in results:
            self.assertTrue(r["skipped"])

    # ------------------------------------------------------------------
    # 13. One failure does not prevent other currencies from processing
    # ------------------------------------------------------------------
    def test_13_one_failure_does_not_block_others(self):
        """If USD fails all retries, EUR and others are still attempted."""
        import requests as req_module
        stored_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")

        def selective_error(url, **kwargs):
            if "base=USD" in url:
                raise req_module.exceptions.ConnectionError("USD offline")
            # Other currencies: return today (already up to date)
            return _make_response(200, _api_data([(today, 84.0)]))

        with _TempDB():
            # Seed a date 2 days ago for all currencies so they all try to fetch
            for c in updater.CURRENCIES:
                database.save_historical_rates_batch([
                    (stored_date, c, updater.TARGET, 84.0)
                ])
            with patch("requests.get", side_effect=selective_error):
                with patch("time.sleep"):
                    results = updater.run()

        usd_result = next(r for r in results if r["currency"] == "USD")
        eur_result = next(r for r in results if r["currency"] == "EUR")
        self.assertIsNotNone(usd_result["error"])
        # EUR should not have an error (it returned today's data successfully)
        self.assertIsNone(eur_result["error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

