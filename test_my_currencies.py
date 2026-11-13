import unittest
import os
import sys
import shutil
import sqlite3
import re
from unittest.mock import patch

APP_DIR = os.path.abspath(os.path.dirname(__file__))
SCRATCH_DIR = r"C:\Users\Mujtaba\.gemini\antigravity\brain\36dc7d33-4fb7-4539-8a19-736b6c7c82a8\scratch"
TEST_DB = os.path.join(SCRATCH_DIR, "test_my_currencies_scratch.db")

# Setup isolated test database before importing app
shutil.copy2(os.path.join(SCRATCH_DIR, "db_copy.db"), TEST_DB)
sys.path.insert(0, APP_DIR)

import database
database.DATABASE_NAME = TEST_DB

from app import app
import app as app_module
app_module.DATABASE_NAME = TEST_DB


class TestMyCurrenciesSuite(unittest.TestCase):
    def setUp(self):
        shutil.copy2(os.path.join(SCRATCH_DIR, "db_copy.db"), TEST_DB)
        database.DATABASE_NAME = TEST_DB
        app_module.DATABASE_NAME = TEST_DB
        database.create_database()
        self.client = app.test_client()

        # Seed two distinct users in the test database for isolation testing
        conn = sqlite3.connect(TEST_DB)
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE username IN ('user_curr1', 'user_curr2')")
        cur.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            ("user_curr1", "hash_pw1", "2026-03-15 10:30:00")
        )
        self.user1_id = cur.lastrowid

        cur.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            ("user_curr2", "hash_pw2", "2026-04-20 14:45:00")
        )
        self.user2_id = cur.lastrowid
        conn.commit()
        conn.close()

    def _login_client(self, user_id=None, username=None):
        uid = user_id or self.user1_id
        uname = username or "user_curr1"
        c = self.client
        with c.session_transaction() as sess:
            sess["user_id"] = uid
            sess["username"] = uname
            sess["_csrf_token"] = "test_csrf_token_123"
        return c, "test_csrf_token_123"

    # ---------------------------------------------------------
    # 1. Access and Authentication (Tests 1-3)
    # ---------------------------------------------------------

    def test_01_unauthenticated_visitor_redirected_to_login(self):
        """Unauthenticated visitor accessing /my-currencies is redirected to login."""
        resp = self.client.get("/my-currencies")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])
        self.assertIn("next=", resp.headers["Location"])

    def test_02_authenticated_user_can_access_my_currencies(self):
        """Authenticated user receives HTTP 200 on /my-currencies."""
        c, _ = self._login_client()
        resp = c.get("/my-currencies")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("My Currencies &amp; Rate Alerts", html)

    def test_03_csrf_protection_rejects_missing_or_invalid_tokens(self):
        """POST without valid CSRF token is rejected with HTTP 400."""
        c, _ = self._login_client()
        # Missing token
        resp1 = c.post("/my-currencies/default", data={"default_currency": "EUR"})
        self.assertEqual(resp1.status_code, 400)

        # Invalid token
        resp2 = c.post("/my-currencies/default", data={"default_currency": "EUR", "csrf_token": "wrong_token"})
        self.assertEqual(resp2.status_code, 400)

    # ---------------------------------------------------------
    # 2. Default Currency (Tests 4-7)
    # ---------------------------------------------------------

    def test_04_default_currency_displayed_correctly(self):
        """Default currency (initial or saved) is displayed correctly."""
        database.save_user_preferences(self.user1_id, default_currency="GBP")
        c, _ = self._login_client()
        resp = c.get("/my-currencies")
        html = resp.data.decode("utf-8")
        self.assertIn('value="GBP" selected', html)

    def test_05_supported_currency_can_be_saved(self):
        """A supported currency (e.g. EUR) can be saved as default."""
        c, token = self._login_client()
        resp = c.post("/my-currencies/default", data={"default_currency": "EUR", "csrf_token": token}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        prefs = database.get_user_preferences(self.user1_id)
        self.assertEqual(prefs["default_currency"], "EUR")

    def test_06_invalid_currency_codes_are_rejected(self):
        """Invalid or unsupported currency codes are rejected for default currency."""
        c, token = self._login_client()
        resp = c.post("/my-currencies/default", data={"default_currency": "XYZ", "csrf_token": token}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Invalid currency selection.", resp.data.decode("utf-8"))
        prefs = database.get_user_preferences(self.user1_id)
        self.assertNotEqual(prefs["default_currency"], "XYZ")

    def test_07_one_user_preference_does_not_affect_another(self):
        """User 1's default currency does not overwrite User 2's default currency."""
        database.save_user_preferences(self.user1_id, default_currency="GBP")
        database.save_user_preferences(self.user2_id, default_currency="JPY")

        c, token = self._login_client(self.user1_id, "user_curr1")
        c.post("/my-currencies/default", data={"default_currency": "EUR", "csrf_token": token})

        prefs1 = database.get_user_preferences(self.user1_id)
        prefs2 = database.get_user_preferences(self.user2_id)
        self.assertEqual(prefs1["default_currency"], "EUR")
        self.assertEqual(prefs2["default_currency"], "JPY")

    # ---------------------------------------------------------
    # 3. Watchlist (Tests 8-15)
    # ---------------------------------------------------------

    def test_08_currency_can_be_added_to_watchlist(self):
        """A supported currency can be added to the user's watchlist."""
        c, token = self._login_client()
        resp = c.post("/my-currencies/watchlist/add", data={"currency": "USD", "csrf_token": token}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        prefs = database.get_user_preferences(self.user1_id)
        self.assertIn("USD", prefs["watchlist"])

    def test_09_duplicate_currencies_prevented(self):
        """Adding an already watched currency is prevented and informs the user."""
        database.save_user_preferences(self.user1_id, watchlist=["USD"])
        c, token = self._login_client()
        resp = c.post("/my-currencies/watchlist/add", data={"currency": "USD", "csrf_token": token}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("already in your watchlist", resp.data.decode("utf-8"))
        prefs = database.get_user_preferences(self.user1_id)
        self.assertEqual(prefs["watchlist"].count("USD"), 1)

    def test_10_unsupported_currencies_rejected_from_watchlist(self):
        """Unsupported currency codes are rejected when adding to watchlist."""
        c, token = self._login_client()
        resp = c.post("/my-currencies/watchlist/add", data={"currency": "BITCOIN", "csrf_token": token}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Invalid currency code.", resp.data.decode("utf-8"))
        prefs = database.get_user_preferences(self.user1_id)
        self.assertNotIn("BITCOIN", prefs["watchlist"])

    def test_11_currency_can_be_removed_from_watchlist(self):
        """A currency can be removed from the user's watchlist."""
        database.save_user_preferences(self.user1_id, watchlist=["USD", "EUR"])
        c, token = self._login_client()
        resp = c.post("/my-currencies/watchlist/remove", data={"currency": "USD", "csrf_token": token}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        prefs = database.get_user_preferences(self.user1_id)
        self.assertNotIn("USD", prefs["watchlist"])
        self.assertIn("EUR", prefs["watchlist"])

    def test_12_empty_watchlist_displays_clean_message(self):
        """When watchlist is empty, a clean informational message is displayed."""
        database.save_user_preferences(self.user1_id, watchlist=[])
        c, _ = self._login_client()
        resp = c.get("/my-currencies")
        html = resp.data.decode("utf-8")
        self.assertIn("Your watchlist is currently empty.", html)

    def test_13_latest_saved_rates_displayed_with_actual_dates(self):
        """Watchlist displays the latest stored rate and actual observation date from SQLite."""
        database.save_user_preferences(self.user1_id, watchlist=["USD"])
        database.save_rate("USD", "INR", 88.50, date="2026-11-12")

        c, _ = self._login_client()
        resp = c.get("/my-currencies")
        html = resp.data.decode("utf-8")
        self.assertIn("88.5000", html)
        self.assertIn("Observed: 2026-11-12", html)

    def test_14_missing_saved_rates_handled_gracefully(self):
        """If a watched currency has no stored exchange rate, it displays gracefully."""
        database.save_user_preferences(self.user1_id, watchlist=["AED"])
        # Remove AED rates if any
        conn = sqlite3.connect(TEST_DB)
        cur = conn.cursor()
        cur.execute("DELETE FROM exchange_rates WHERE base_currency = 'AED'")
        conn.commit()
        conn.close()

        c, _ = self._login_client()
        resp = c.get("/my-currencies")
        html = resp.data.decode("utf-8")
        self.assertIn("No rate recorded", html)

    def test_15_one_user_cannot_view_or_modify_another_users_watchlist(self):
        """User 1's watchlist is isolated from User 2."""
        database.save_user_preferences(self.user1_id, watchlist=["USD"])
        database.save_user_preferences(self.user2_id, watchlist=["JPY"])

        c, token = self._login_client(self.user1_id, "user_curr1")
        resp = c.get("/my-currencies")
        html = resp.data.decode("utf-8")
        badges = re.findall(r'<span class="acct-currency-badge">([A-Z]{3})</span>', html)
        self.assertIn("USD", badges)
        self.assertNotIn("JPY", badges)

        # User 1 attempting to remove JPY (which is only in User 2's watchlist)
        c.post("/my-currencies/watchlist/remove", data={"currency": "JPY", "csrf_token": token}, follow_redirects=True)
        u2_prefs = database.get_user_preferences(self.user2_id)
        self.assertIn("JPY", u2_prefs["watchlist"])

    # ---------------------------------------------------------
    # 4. Rate Alerts (Tests 16-27)
    # ---------------------------------------------------------

    def test_16_valid_above_alert_can_be_created(self):
        """Valid alert with direction='above' is created in database."""
        c, token = self._login_client()
        resp = c.post("/my-currencies/alerts/create", data={
            "currency": "USD",
            "direction": "above",
            "target_rate": "92.50",
            "csrf_token": token
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        alerts = database.get_rate_alerts(self.user1_id)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["currency"], "USD")
        self.assertEqual(alerts[0]["direction"], "above")
        self.assertEqual(alerts[0]["target_rate"], 92.50)

    def test_17_valid_below_alert_can_be_created(self):
        """Valid alert with direction='below' is created in database."""
        c, token = self._login_client()
        resp = c.post("/my-currencies/alerts/create", data={
            "currency": "EUR",
            "direction": "below",
            "target_rate": "90.00",
            "csrf_token": token
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        alerts = database.get_rate_alerts(self.user1_id)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["currency"], "EUR")
        self.assertEqual(alerts[0]["direction"], "below")

    def test_18_invalid_directions_rejected(self):
        """Invalid alert direction strings (not 'above' or 'below') are rejected."""
        c, token = self._login_client()
        resp = c.post("/my-currencies/alerts/create", data={
            "currency": "USD",
            "direction": "equal",
            "target_rate": "90.00",
            "csrf_token": token
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Invalid alert direction.", resp.data.decode("utf-8"))
        alerts = database.get_rate_alerts(self.user1_id)
        self.assertEqual(len(alerts), 0)

    def test_19_invalid_zero_negative_nan_inf_rates_rejected(self):
        """Target rates <= 0, NaN, Inf, and non-numeric are rejected; small positive accepted."""
        c, token = self._login_client()
        invalid_rates = ["0", "-10", "NaN", "Infinity", "-Infinity", "abc", ""]
        for bad_rate in invalid_rates:
            resp = c.post("/my-currencies/alerts/create", data={
                "currency": "USD",
                "direction": "above",
                "target_rate": bad_rate,
                "csrf_token": token
            }, follow_redirects=True)
            self.assertEqual(resp.status_code, 200)
            alerts = database.get_rate_alerts(self.user1_id)
            self.assertEqual(len(alerts), 0, f"Expected rejection for rate: {bad_rate}")

        # A small positive value like 0.00005 must be ACCEPTED
        resp = c.post("/my-currencies/alerts/create", data={
            "currency": "USD",
            "direction": "above",
            "target_rate": "0.00005",
            "csrf_token": token
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        alerts = database.get_rate_alerts(self.user1_id)
        self.assertEqual(len(alerts), 1, "Expected 0.00005 to be accepted as a valid target rate")
        self.assertAlmostEqual(alerts[0]["target_rate"], 0.00005)

    def test_20_unsupported_currencies_rejected_for_alerts(self):
        """Unsupported currency codes are rejected when creating rate alerts."""
        c, token = self._login_client()
        resp = c.post("/my-currencies/alerts/create", data={
            "currency": "CAD",
            "direction": "above",
            "target_rate": "60.00",
            "csrf_token": token
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Unsupported currency selected.", resp.data.decode("utf-8"))
        alerts = database.get_rate_alerts(self.user1_id)
        self.assertEqual(len(alerts), 0)

    def test_21_twenty_alert_limit_enforced(self):
        """User cannot create more than 20 rate alerts."""
        for i in range(20):
            database.add_rate_alert(self.user1_id, "USD", "above", 80.0 + i)
        self.assertEqual(database.count_rate_alerts(self.user1_id), 20)

        c, token = self._login_client()
        resp = c.post("/my-currencies/alerts/create", data={
            "currency": "EUR",
            "direction": "above",
            "target_rate": "95.00",
            "csrf_token": token
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Maximum limit of 20 rate alerts reached.", resp.data.decode("utf-8"))
        self.assertEqual(database.count_rate_alerts(self.user1_id), 20)

    def test_22_triggered_alerts_display_correctly(self):
        """Triggered alerts display triggered status, rate, and observation date."""
        database.add_rate_alert(self.user1_id, "USD", "above", 85.0)
        database.save_rate("USD", "INR", 88.50, date="2026-11-12")
        database.check_user_alerts(self.user1_id)

        c, _ = self._login_client()
        resp = c.get("/my-currencies")
        html = resp.data.decode("utf-8")
        self.assertIn("TRIGGERED: 88.5000 INR", html)
        self.assertIn("2026-11-12", html)

    def test_23_acknowledged_alerts_not_shown_as_active_triggered(self):
        """Acknowledged (dismissed) alerts show dismissed status, not active triggered."""
        database.add_rate_alert(self.user1_id, "USD", "above", 85.0)
        database.save_rate("USD", "INR", 88.50, date="2026-11-12")
        triggered = database.check_user_alerts(self.user1_id)
        alert_id = triggered[0]["id"]
        database.dismiss_rate_alert(self.user1_id, alert_id)

        c, _ = self._login_client()
        resp = c.get("/my-currencies")
        html = resp.data.decode("utf-8")
        self.assertIn("Dismissed", html)
        self.assertNotIn("acct-status-triggered", html)

    def test_24_an_alert_can_be_dismissed(self):
        """POST to dismiss alert sets acknowledged=1."""
        database.add_rate_alert(self.user1_id, "USD", "above", 85.0)
        database.save_rate("USD", "INR", 88.50, date="2026-11-12")
        triggered = database.check_user_alerts(self.user1_id)
        alert_id = triggered[0]["id"]

        c, token = self._login_client()
        resp = c.post(f"/my-currencies/alerts/{alert_id}/dismiss", data={"csrf_token": token}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        alerts = database.get_rate_alerts(self.user1_id)
        self.assertTrue(alerts[0]["acknowledged"])

    def test_25_an_alert_can_be_rearmed(self):
        """POST to re-arm alert clears triggered fields and resets acknowledged=0."""
        database.add_rate_alert(self.user1_id, "USD", "above", 120.0) # threshold high so it won't re-trigger right away
        # Manually trigger it
        conn = sqlite3.connect(TEST_DB)
        cur = conn.cursor()
        cur.execute("UPDATE rate_alerts SET triggered_at = '2026-11-12 12:00:00', acknowledged = 1 WHERE user_id = ?", (self.user1_id,))
        conn.commit()
        alert_id = cur.execute("SELECT id FROM rate_alerts WHERE user_id = ?", (self.user1_id,)).fetchone()[0]
        conn.close()

        c, token = self._login_client()
        resp = c.post(f"/my-currencies/alerts/{alert_id}/rearm", data={"csrf_token": token}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        alerts = database.get_rate_alerts(self.user1_id)
        self.assertIsNone(alerts[0]["triggered_at"])
        self.assertFalse(alerts[0]["acknowledged"])

    def test_26_an_alert_can_be_deleted(self):
        """POST to delete alert permanently removes it from SQLite."""
        database.add_rate_alert(self.user1_id, "USD", "above", 90.0)
        alerts = database.get_rate_alerts(self.user1_id)
        alert_id = alerts[0]["id"]

        c, token = self._login_client()
        resp = c.post(f"/my-currencies/alerts/{alert_id}/delete", data={"csrf_token": token}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(database.count_rate_alerts(self.user1_id), 0)

    def test_27_one_user_cannot_view_dismiss_rearm_or_delete_another_users_alert(self):
        """User 1 cannot view, delete, dismiss, or re-arm User 2's alert."""
        database.add_rate_alert(self.user2_id, "EUR", "above", 95.0)
        alerts2 = database.get_rate_alerts(self.user2_id)
        u2_alert_id = alerts2[0]["id"]

        c, token = self._login_client(self.user1_id, "user_curr1")

        # View: User 1 does not see User 2's alert
        resp_view = c.get("/my-currencies")
        html = resp_view.data.decode("utf-8")
        self.assertNotIn(f"/my-currencies/alerts/{u2_alert_id}/delete", html)
        self.assertNotIn("95.0000", html)
        self.assertIn("Rate Alerts (0/20)", html)

        # Delete: User 1 attempting to delete User 2's alert fails
        resp_del = c.post(f"/my-currencies/alerts/{u2_alert_id}/delete", data={"csrf_token": token}, follow_redirects=True)
        self.assertIn("Alert not found or unauthorized.", resp_del.data.decode("utf-8"))
        self.assertEqual(len(database.get_rate_alerts(self.user2_id)), 1)

        # Dismiss: User 1 attempting to dismiss User 2's alert fails
        resp_dis = c.post(f"/my-currencies/alerts/{u2_alert_id}/dismiss", data={"csrf_token": token}, follow_redirects=True)
        self.assertIn("Alert not found or unauthorized.", resp_dis.data.decode("utf-8"))

        # Re-arm: User 1 attempting to rearm User 2's alert fails
        resp_re = c.post(f"/my-currencies/alerts/{u2_alert_id}/rearm", data={"csrf_token": token}, follow_redirects=True)
        self.assertIn("Alert not found or unauthorized.", resp_re.data.decode("utf-8"))

    # ---------------------------------------------------------
    # 5. Integration (Tests 28-30)
    # ---------------------------------------------------------

    def test_28_visiting_dashboard_and_my_currencies_checks_alerts_using_saved_rates_only(self):
        """Visiting /dashboard and /my-currencies automatically evaluates active alerts against saved rates."""
        database.add_rate_alert(self.user1_id, "USD", "above", 85.0)
        database.save_rate("USD", "INR", 88.50, date="2026-11-12")

        # Prior to visit, alert not triggered
        alerts_before = database.get_rate_alerts(self.user1_id)
        self.assertIsNone(alerts_before[0]["triggered_at"])

        # Visit /my-currencies
        c, _ = self._login_client()
        c.get("/my-currencies")

        # After visit, alert is marked triggered
        alerts_after = database.get_rate_alerts(self.user1_id)
        self.assertIsNotNone(alerts_after[0]["triggered_at"])
        self.assertEqual(alerts_after[0]["triggered_rate"], 88.50)

    def test_29_no_external_api_calls_made_for_alert_checking(self):
        """Verify check_user_alerts makes ZERO calls to external api functions."""
        with patch("api.get_exchange_rate") as mock_api:
            database.add_rate_alert(self.user1_id, "USD", "above", 85.0)
            database.save_rate("USD", "INR", 88.50, date="2026-11-12")

            c, _ = self._login_client()
            c.get("/my-currencies")
            c.get("/dashboard")

            # Must never call external API
            mock_api.assert_not_called()

    def test_30_existing_stage4_dashboard_tests_still_pass(self):
        """Confirm that dashboard integration works and counts watchlist correctly."""
        database.save_user_preferences(self.user1_id, watchlist=["USD", "EUR"])
        c, _ = self._login_client()
        resp = c.get("/dashboard")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Watchlist Currencies", html)
        self.assertIn("2", html)


if __name__ == "__main__":
    unittest.main()
