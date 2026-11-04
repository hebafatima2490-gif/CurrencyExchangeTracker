import unittest
import sqlite3
from datetime import datetime
from unittest.mock import patch
from app import app, load_historical_data
from database import (
    create_database,
    save_rate,
    save_historical_rate,
    get_history,
    get_previous_rate,
    get_average_rate,
    get_volatility,
    get_date_bounds,
    DATABASE_NAME
)


class CurrencyTrackerTestSuite(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Ensure database is created and initialized
        create_database()
        cls.client = app.test_client()

    def test_01_flask_app_starts(self):
        """Check that Flask application starts and home dashboard route responds successfully."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"International Currency Exchange Rate Tracker", response.data)
        self.assertIn(b"Smart Recommendation", response.data)
        self.assertIn(b"Volatility Index", response.data)

    def test_02_historical_records_load_from_sqlite(self):
        """Check that historical records load correctly from SQLite."""
        # Check database records directly
        records = get_history("USD", "INR")
        self.assertIsInstance(records, list)
        self.assertGreater(len(records), 0, "Database should contain USD->INR historical records")

        # Verify dates are in ascending order
        dates = [r[0] for r in records]
        self.assertEqual(dates, sorted(dates), "Records must be sorted by date ASC")

        # Check /history route renders with these records
        response = self.client.get("/history?currency=USD")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"USD \xe2\x86\x92 INR Exchange Rate", response.data) # USD → INR
        # First record date should be in response
        self.assertIn(records[0][0].encode(), response.data)

    def test_03_newly_saved_records_appear_in_graph_and_deduplication(self):
        """Check that newly saved records appear in history graph and duplicate records are prevented."""
        test_date = "2026-11-15"
        test_rate = 99.85

        # Save new record
        saved = save_rate("USD", "INR", test_rate, date=test_date)
        self.assertTrue(saved)

        # Check that reloading history page includes the newly saved record
        response = self.client.get("/history?currency=USD")
        self.assertEqual(response.status_code, 200)
        self.assertIn(test_date.encode(), response.data)
        self.assertIn(str(test_rate).encode(), response.data)

        # Test duplicate avoidance: saving same date and currency pair must update, not create duplicate
        save_rate("USD", "INR", 99.90, date=test_date)
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute("""
            SELECT COUNT(*), rate FROM exchange_rates
            WHERE date = ? AND base_currency = ? AND target_currency = ?
        """, (test_date, "USD", "INR"))
        count, rate = c.fetchone()
        conn.close()

        self.assertEqual(count, 1, "Duplicate record was created!")
        self.assertEqual(rate, 99.90, "Existing record should be updated with new rate")

        # Clean up test record so we don't pollute data
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute("DELETE FROM exchange_rates WHERE date = ? AND base_currency = ?", (test_date, "USD"))
        conn.commit()
        conn.close()

    def test_04_currency_dropdown_and_date_filters(self):
        """Check the currency dropdown and start/end date range filters."""
        # 1. Switch to EUR
        response_eur = self.client.get("/history?currency=EUR")
        self.assertEqual(response_eur.status_code, 200)
        self.assertIn(b"EUR \xe2\x86\x92 INR", response_eur.data)

        # 2. Switch to GBP
        response_gbp = self.client.get("/history?currency=GBP")
        self.assertEqual(response_gbp.status_code, 200)
        self.assertIn(b"GBP \xe2\x86\x92 INR", response_gbp.data)

        # 3. Filter by date range (e.g. 2026-09-05 to 2026-09-10)
        response_filtered = self.client.get("/history?currency=USD&start_date=2026-09-05&end_date=2026-09-10")
        self.assertEqual(response_filtered.status_code, 200)
        self.assertIn(b"<td>2026-09-05</td>", response_filtered.data)
        self.assertIn(b"<td>2026-09-10</td>", response_filtered.data)
        # Dates outside the range should not be in the table or chart data
        self.assertNotIn(b"<td>2026-09-01</td>", response_filtered.data)
        self.assertNotIn(b"<td>2026-09-25</td>", response_filtered.data)

    def test_05_api_errors_and_empty_date_ranges(self):
        """Check that API errors, invalid dates, and empty date ranges are handled gracefully."""
        # 1. Empty date range (no records found)
        response_empty = self.client.get("/history?currency=USD&start_date=2021-01-01&end_date=2021-01-05")
        self.assertEqual(response_empty.status_code, 200)
        self.assertIn(b"No exchange-rate records", response_empty.data)

        # 2. Invalid date order (start_date > end_date)
        response_invalid_order = self.client.get("/history?currency=USD&start_date=2026-09-20&end_date=2026-09-10")
        self.assertEqual(response_invalid_order.status_code, 200)
        self.assertIn(b"Start date cannot be after end date", response_invalid_order.data)

        # 3. Malformed date format
        response_malformed = self.client.get("/history?currency=USD&start_date=bad-date")
        self.assertEqual(response_malformed.status_code, 200)
        self.assertIn(b"Invalid start date format", response_malformed.data)

        # 4. Save None rate (API failure) - verify it returns False and does not store None in DB
        result = save_rate("USD", "INR", None)
        self.assertFalse(result)

        # 5. Dashboard handles simulated API failure gracefully
        with patch("app.get_exchange_rate", return_value=None):
            response_api_down = self.client.get("/")
            self.assertEqual(response_api_down.status_code, 200)
            self.assertIn(b"International Currency Exchange Rate Tracker", response_api_down.data)

    def test_06_converter_route(self):
        """Check that currency converter feature is intact and works."""
        response = self.client.post("/convert", data={
            "from_currency": "USD",
            "to_currency": "INR",
            "amount": "100"
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Currency Conversion Result", response.data)
        self.assertIn(b"Exchange Rate", response.data)


if __name__ == "__main__":
    unittest.main()
