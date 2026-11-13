import unittest
import os
import sys
import shutil
import sqlite3
import re

APP_DIR = os.path.abspath(os.path.dirname(__file__))
SCRATCH_DIR = r"C:\Users\Mujtaba\.gemini\antigravity\brain\36dc7d33-4fb7-4539-8a19-736b6c7c82a8\scratch"
TEST_DB = os.path.join(SCRATCH_DIR, "test_dashboard_scratch.db")

# Setup isolated test database before importing app
shutil.copy2(os.path.join(SCRATCH_DIR, "db_copy.db"), TEST_DB)
sys.path.insert(0, APP_DIR)

import database
database.DATABASE_NAME = TEST_DB

from app import app
import app as app_module
app_module.DATABASE_NAME = TEST_DB


class TestDashboardSuite(unittest.TestCase):
    def setUp(self):
        # Fresh DB copy for each test
        shutil.copy2(os.path.join(SCRATCH_DIR, "db_copy.db"), TEST_DB)
        database.DATABASE_NAME = TEST_DB
        app_module.DATABASE_NAME = TEST_DB
        database.create_database()
        self.client = app.test_client()

        # Seed two distinct users in the test database for isolation testing
        conn = sqlite3.connect(TEST_DB)
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE username IN ('user_dash1', 'user_dash2')")
        cur.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            ("user_dash1", "hash_pw1", "2026-03-15 10:30:00")
        )
        self.user1_id = cur.lastrowid

        cur.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            ("user_dash2", "hash_pw2", "2026-04-20 14:45:00")
        )
        self.user2_id = cur.lastrowid
        conn.commit()
        conn.close()

    def test_01_unauthenticated_visitor_redirected_to_login(self):
        """Unauthenticated visitor accessing /dashboard is redirected to /login?next=%2Fdashboard."""
        resp = self.client.get("/dashboard")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])
        self.assertIn("next=", resp.headers["Location"])

    def test_02_logged_in_user_can_access_dashboard(self):
        """Logged-in user receives HTTP 200 on /dashboard."""
        with self.client as c:
            with c.session_transaction() as sess:
                sess["user_id"] = self.user1_id
                sess["username"] = "user_dash1"
            resp = c.get("/dashboard")
            self.assertEqual(resp.status_code, 200)

    def test_03_correct_username_displayed(self):
        """Dashboard displays the authenticated user's actual username."""
        with self.client as c:
            with c.session_transaction() as sess:
                sess["user_id"] = self.user1_id
                sess["username"] = "user_dash1"
            resp = c.get("/dashboard")
            html = resp.data.decode("utf-8")
            self.assertIn("user_dash1", html)

    def test_04_correct_membership_date_displayed(self):
        """Dashboard displays the user's actual registration/membership date."""
        with self.client as c:
            with c.session_transaction() as sess:
                sess["user_id"] = self.user1_id
                sess["username"] = "user_dash1"
            resp = c.get("/dashboard")
            html = resp.data.decode("utf-8")
            self.assertIn("2026-03-15 10:30:00", html)

    def test_05_watchlist_count_accurate(self):
        """Watchlist count matches the actual saved currencies in user_preferences."""
        database.save_user_preferences(self.user1_id, default_currency="USD", watchlist=["EUR", "GBP", "JPY"])
        with self.client as c:
            with c.session_transaction() as sess:
                sess["user_id"] = self.user1_id
                sess["username"] = "user_dash1"
            resp = c.get("/dashboard")
            html = resp.data.decode("utf-8")
            # Verify 3 is displayed for watchlist
            self.assertIn('Watchlist Currencies', html)
            self.assertIn('3', html)

    def test_06_saved_conversion_count_accurate(self):
        """Saved conversions count accurately reflects records of kind='conversion'."""
        database.add_saved_item(self.user1_id, "conversion", "USD to INR", "100 USD = 8850 INR", '{"amount": 100}')
        database.add_saved_item(self.user1_id, "conversion", "EUR to INR", "50 EUR = 4760 INR", '{"amount": 50}')
        with self.client as c:
            with c.session_transaction() as sess:
                sess["user_id"] = self.user1_id
                sess["username"] = "user_dash1"
            resp = c.get("/dashboard")
            html = resp.data.decode("utf-8")
            self.assertIn('Saved Conversions', html)
            self.assertIn('2', html)

    def test_07_saved_travel_plan_count_accurate(self):
        """Saved travel plans count accurately reflects records of kind='trip'."""
        database.add_saved_item(self.user1_id, "trip", "Europe Summer", "Budget 2000 EUR", '{"budget": 2000}')
        with self.client as c:
            with c.session_transaction() as sess:
                sess["user_id"] = self.user1_id
                sess["username"] = "user_dash1"
            resp = c.get("/dashboard")
            html = resp.data.decode("utf-8")
            self.assertIn('Saved Travel Plans', html)
            self.assertIn('1', html)

    def test_08_saved_decision_count_accurate(self):
        """Saved decision count accurately reflects records of kind='audit'."""
        database.add_saved_item(self.user1_id, "audit", "Hold EUR", "Volatility High", '{"action": "hold"}')
        with self.client as c:
            with c.session_transaction() as sess:
                sess["user_id"] = self.user1_id
                sess["username"] = "user_dash1"
            resp = c.get("/dashboard")
            html = resp.data.decode("utf-8")
            self.assertIn('Saved Decision History', html)
            self.assertIn('1', html)

    def test_09_empty_categories_display_zero(self):
        """When user has no records, all counts display 0."""
        with self.client as c:
            with c.session_transaction() as sess:
                sess["user_id"] = self.user1_id
                sess["username"] = "user_dash1"
            resp = c.get("/dashboard")
            html = resp.data.decode("utf-8")
            # All 4 cards should show 0 count
            counts = re.findall(r'<div class="acct-card-count">(\d+)</div>', html)
            self.assertEqual(len(counts), 4)
            for cnt in counts:
                self.assertEqual(cnt, "0")

    def test_10_triggered_unacknowledged_alerts_displayed(self):
        """Triggered and unacknowledged alerts appear on the dashboard with observation date."""
        # Add alert that will trigger against existing USD/INR rate in database
        database.add_rate_alert(self.user1_id, "USD", "above", 50.0)
        # Ensure latest rate exists in DB
        database.save_rate("USD", "INR", 88.50, date="2026-11-12")

        with self.client as c:
            with c.session_transaction() as sess:
                sess["user_id"] = self.user1_id
                sess["username"] = "user_dash1"
            resp = c.get("/dashboard")
            html = resp.data.decode("utf-8")
            self.assertIn("USD", html)
            self.assertIn("88.5000", html)
            self.assertIn("50.0000", html)
            self.assertIn("2026-11-12", html)

    def test_11_acknowledged_alerts_not_displayed(self):
        """Triggered alerts that have been acknowledged (dismissed) do not appear in the alert banner."""
        database.add_rate_alert(self.user1_id, "USD", "above", 50.0)
        database.save_rate("USD", "INR", 88.50, date="2026-11-12")
        # Trigger it
        alerts = database.check_user_alerts(self.user1_id)
        self.assertEqual(len(alerts), 1)
        alert_id = alerts[0]["id"]
        # Acknowledge (dismiss) it
        database.dismiss_rate_alert(self.user1_id, alert_id)

        with self.client as c:
            with c.session_transaction() as sess:
                sess["user_id"] = self.user1_id
                sess["username"] = "user_dash1"
            resp = c.get("/dashboard")
            html = resp.data.decode("utf-8")
            self.assertNotIn("acct-alert-card", html)
            self.assertIn("No active triggered rate alerts", html)

    def test_12_other_users_alerts_never_displayed(self):
        """User 1 never sees User 2's triggered alerts."""
        database.add_rate_alert(self.user2_id, "EUR", "above", 50.0)
        database.save_rate("EUR", "INR", 95.20, date="2026-11-12")
        # Trigger User 2's alerts
        database.check_user_alerts(self.user2_id)

        # Log in as User 1
        with self.client as c:
            with c.session_transaction() as sess:
                sess["user_id"] = self.user1_id
                sess["username"] = "user_dash1"
            resp = c.get("/dashboard")
            html = resp.data.decode("utf-8")
            self.assertNotIn("EUR", html)
            self.assertIn("No active triggered rate alerts", html)

    def test_13_other_users_saved_items_never_counted(self):
        """User 1's summary cards never count User 2's saved items."""
        # Add saved items for User 2 only
        database.add_saved_item(self.user2_id, "conversion", "EUR to INR", "50 EUR", "{}")
        database.add_saved_item(self.user2_id, "trip", "Tokyo", "Budget", "{}")
        database.add_saved_item(self.user2_id, "audit", "Hold USD", "Decision", "{}")
        database.save_user_preferences(self.user2_id, watchlist=["USD", "EUR", "GBP"])

        # View as User 1
        with self.client as c:
            with c.session_transaction() as sess:
                sess["user_id"] = self.user1_id
                sess["username"] = "user_dash1"
            resp = c.get("/dashboard")
            html = resp.data.decode("utf-8")
            counts = re.findall(r'<div class="acct-card-count">(\d+)</div>', html)
            self.assertEqual(len(counts), 4)
            for cnt in counts:
                self.assertEqual(cnt, "0")

    def test_14_return_to_live_rates_link_points_to_home(self):
        """Return to live exchange rates link points to '/'."""
        with self.client as c:
            with c.session_transaction() as sess:
                sess["user_id"] = self.user1_id
                sess["username"] = "user_dash1"
            resp = c.get("/dashboard")
            html = resp.data.decode("utf-8")
            self.assertIn('href="/" class="acct-action-btn"', html)
            self.assertIn('Return to Live Exchange Rates', html)

    def test_15_dashboard_renders_cleanly_when_empty(self):
        """Dashboard renders successfully and cleanly when user has no alerts and no saved items."""
        with self.client as c:
            with c.session_transaction() as sess:
                sess["user_id"] = self.user1_id
                sess["username"] = "user_dash1"
            resp = c.get("/dashboard")
            self.assertEqual(resp.status_code, 200)
            html = resp.data.decode("utf-8")
            self.assertIn("No active triggered rate alerts", html)
            self.assertIn("Watchlist Currencies", html)
            self.assertIn("Saved Conversions", html)
            self.assertIn("Saved Travel Plans", html)
            self.assertIn("Saved Decision History", html)


if __name__ == "__main__":
    unittest.main()
