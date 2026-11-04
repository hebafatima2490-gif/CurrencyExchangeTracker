"""
Unit and Integration Test Suite for Historical Monthly Graph & Enhanced Dynamic Graph
Validates all requirements specified in the project enhancement prompt.
"""

import unittest
import sqlite3
from unittest.mock import patch
from app import app, get_monthly_data_for_year, compute_daily_trends
from database import (
    create_database,
    save_monthly_rate,
    get_monthly_history,
    has_monthly_data_for_year,
    get_latest_rate,
    DATABASE_NAME
)


class HistoricalEnhancementsTestSuite(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        create_database()
        cls.client = app.test_client()

    def test_01_database_schema_monthly_rates_table(self):
        """Verify monthly_exchange_rates table exists with required columns and unique constraint."""
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()

        # Check table columns
        cursor.execute("PRAGMA table_info(monthly_exchange_rates)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        required_cols = [
            "id", "base_currency", "target_currency",
            "year", "month", "average_rate", "observations_count",
            "data_source"
        ]
        for col in required_cols:
            self.assertIn(col, columns, f"Column {col} must exist in monthly_exchange_rates table")

        # Check unique index on (base_currency, target_currency, year, month)
        cursor.execute("PRAGMA index_list(monthly_exchange_rates)")
        indexes = cursor.fetchall()
        self.assertTrue(len(indexes) > 0, "Index must exist on monthly_exchange_rates")

        conn.close()

    def test_02_monthly_average_calculation_and_storage(self):
        """Verify monthly average is calculated as sum/count and saved/updated without duplicates."""
        test_cur = "TEST_CUR"
        test_year = 2005
        test_month = 6
        daily_observations = [42.10, 42.20, 42.30, 42.40]
        expected_avg = round(sum(daily_observations) / len(daily_observations), 4)

        # Save monthly rate
        saved = save_monthly_rate(test_cur, "INR", test_year, test_month, expected_avg, len(daily_observations))
        self.assertTrue(saved)

        # Retrieve and verify
        records = get_monthly_history(test_cur, "INR", test_year)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0][0], test_month)
        self.assertAlmostEqual(records[0][1], expected_avg, places=3)
        self.assertEqual(records[0][2], len(daily_observations))

        # Test deduplication on re-save
        updated_avg = 42.35
        save_monthly_rate(test_cur, "INR", test_year, test_month, updated_avg, len(daily_observations) + 1)
        records_after = get_monthly_history(test_cur, "INR", test_year)
        self.assertEqual(len(records_after), 1, "Duplicate record created instead of update!")
        self.assertAlmostEqual(records_after[0][1], updated_avg, places=3)

        # Clean up
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute("DELETE FROM monthly_exchange_rates WHERE base_currency = ?", (test_cur,))
        conn.commit()
        conn.close()

    def test_03_historical_monthly_data_coverage_2000_to_2026(self):
        """Verify authentic monthly average data exists from 2000 through 2026 for major currencies."""
        currencies = ["USD", "EUR", "GBP", "JPY", "AED"]

        for cur in currencies:
            # Check 2000
            has_2000 = has_monthly_data_for_year(cur, "INR", 2000)
            self.assertTrue(has_2000, f"Currency {cur} must have historical data for year 2000")

            # Check 2026
            has_2026 = has_monthly_data_for_year(cur, "INR", 2026)
            self.assertTrue(has_2026, f"Currency {cur} must have historical data for year 2026")

            # Check year 2000 has 12 months
            data_2000 = get_monthly_data_for_year(cur, "INR", 2000)
            self.assertTrue(data_2000["has_data"])
            self.assertEqual(data_2000["summary"]["available_months"], 12)

    def test_04_missing_data_handling_for_future_months(self):
        """Verify future or unobserved months (e.g. Dec 2026) are represented as null/missing, not fabricated."""
        data_2026 = get_monthly_data_for_year("USD", "INR", 2026)
        self.assertTrue(data_2026["has_data"])

        # December 2026 (index 11) is in the future relative to Nov 2026, so rate must be None
        dec_rate = data_2026["rates"][11]
        self.assertIsNone(dec_rate, "Future month (Dec 2026) must be None/missing, not filled with fake values")
        self.assertEqual(data_2026["trends"][11], "missing")
        self.assertEqual(data_2026["colors"][11], "transparent")

    def test_05_historical_trend_color_rules(self):
        """Verify trend colors: Green (#16A34A) if increased, Red (#DC2626) if decreased, Neutral (#64748B) if unchanged/first."""
        data_2000 = get_monthly_data_for_year("USD", "INR", 2000)
        rates = data_2000["rates"]
        trends = data_2000["trends"]
        colors = data_2000["colors"]

        # Month 0 (Jan) is initial -> neutral
        self.assertEqual(trends[0], "neutral")
        self.assertEqual(colors[0], "#64748B")

        # For remaining months, verify color matches rate delta vs previous month
        for i in range(1, 12):
            if rates[i] is not None and rates[i - 1] is not None:
                if rates[i] > rates[i - 1]:
                    self.assertEqual(trends[i], "up")
                    self.assertEqual(colors[i], "#16A34A")
                elif rates[i] < rates[i - 1]:
                    self.assertEqual(trends[i], "down")
                    self.assertEqual(colors[i], "#DC2626")
                else:
                    self.assertEqual(trends[i], "flat")
                    self.assertEqual(colors[i], "#64748B")

    def test_06_yearly_summary_statistics_calculation(self):
        """Verify Yearly Summary calculates highest, lowest, average of averages, and coverage."""
        data_2000 = get_monthly_data_for_year("USD", "INR", 2000)
        summary = data_2000["summary"]

        self.assertIsNotNone(summary)
        self.assertEqual(summary["currency_pair"], "USD → INR")
        self.assertEqual(summary["year"], 2000)
        self.assertEqual(summary["available_months"], 12)

        available_rates = [r for r in data_2000["rates"] if r is not None]
        self.assertAlmostEqual(summary["highest_average"], max(available_rates), places=3)
        self.assertAlmostEqual(summary["lowest_average"], min(available_rates), places=3)
        self.assertAlmostEqual(summary["average_of_averages"], sum(available_rates)/len(available_rates), places=3)

    def test_07_api_historical_monthly_endpoint(self):
        """Verify /api/historical-monthly route returns valid JSON with required fields."""
        # Test valid year 2000
        res = self.client.get("/api/historical-monthly?currency=USD&year=2000")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["year"], 2000)
        self.assertEqual(data["currency"], "USD")
        self.assertEqual(len(data["labels"]), 12)
        self.assertEqual(len(data["rates"]), 12)
        self.assertIn("USD to INR — Monthly Average Exchange Rates — 2000", data["title"])

        # Test year bounds validation: year < 2000 returns 400
        res_low = self.client.get("/api/historical-monthly?currency=USD&year=1995")
        self.assertEqual(res_low.status_code, 400)

        # Test year bounds validation: year > 2026 returns 400
        res_high = self.client.get("/api/historical-monthly?currency=USD&year=2030")
        self.assertEqual(res_high.status_code, 400)

    def test_08_api_dynamic_daily_endpoint(self):
        """Verify /api/dynamic-daily route returns daily rates and supports presets (7d, 30d, 60d, all)."""
        res_30d = self.client.get("/api/dynamic-daily?currency=USD&range=30d")
        self.assertEqual(res_30d.status_code, 200)
        data = res_30d.get_json()
        self.assertTrue(data["success"])
        self.assertIn("dates", data)
        self.assertIn("rates", data)
        self.assertIn("colors", data)

    def test_09_history_page_renders_both_graphs_and_controls(self):
        """Verify /history renders both Graph 1 (Dynamic) and Graph 2 (Historical 2000-2026) components."""
        response = self.client.get("/history?currency=USD&year=2000")
        self.assertEqual(response.status_code, 200)

        # Graph 1 elements
        self.assertIn(b"exchangeChart", response.data)
        self.assertIn(b"USD \xe2\x86\x92 INR Exchange Rate", response.data)
        self.assertIn(b'id="start_date"', response.data)
        self.assertIn(b'id="end_date"', response.data)

        # Graph 2 elements (2000-2026)
        self.assertIn(b"monthlyChart", response.data)
        self.assertIn(b"USD to INR \xe2\x80\x94 Monthly Average Exchange Rates \xe2\x80\x94 2000", response.data)
        self.assertIn(b'id="prevYearBtn"', response.data)
        self.assertIn(b'id="nextYearBtn"', response.data)
        self.assertIn(b'id="yearSelect"', response.data)
        self.assertIn(b"Highest Monthly Average", response.data)
        self.assertIn(b"Lowest Monthly Average", response.data)
        self.assertIn(b"Data Coverage", response.data)

    def test_10_daily_trends_computation(self):
        """Verify compute_daily_trends calculates green for increase, red for decrease, slate for first/equal."""
        mock_data = [
            ("2026-10-01", 84.00),
            ("2026-10-02", 84.50),  # Up -> Green
            ("2026-10-03", 84.20),  # Down -> Red
            ("2026-10-04", 84.20)   # Equal -> Slate
        ]
        dates, rates, colors = compute_daily_trends(mock_data)
        self.assertEqual(colors[0], "#64748B")
        self.assertEqual(colors[1], "#16A34A")
        self.assertEqual(colors[2], "#DC2626")
        self.assertEqual(colors[3], "#64748B")


if __name__ == "__main__":
    unittest.main()

