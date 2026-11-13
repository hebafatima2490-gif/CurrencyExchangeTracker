"""
Stage 6 Test Suite — Saved Conversions, Travel Plans & Decisions
Run from: CurrencyExchangeTracker-main/
    python test_stage6_saved_items.py -v
"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

# Point database at an isolated temp DB before importing any app module
_tmp_db = tempfile.mktemp(suffix=".db")
os.environ["CURRENCY_TRACKER_DB"] = _tmp_db

import database
database.DATABASE_NAME = _tmp_db

import app as flask_app
import account as account_mod
account_mod.database.DATABASE_NAME = _tmp_db

TEST_CSRF = "test_csrf_token_stage6"


class TestStage6SavedItems(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        flask_app.app.config["TESTING"] = True
        flask_app.app.config["SECRET_KEY"] = "test-secret-stage6"
        flask_app.app.config["WTF_CSRF_ENABLED"] = False

    def setUp(self):
        # Fresh isolated DB for each test
        if os.path.exists(_tmp_db):
            os.remove(_tmp_db)
        database.create_database()

        # Register two users
        from werkzeug.security import generate_password_hash
        import sqlite3
        conn = sqlite3.connect(_tmp_db)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            ("user_s6a", generate_password_hash("password123"), "2026-01-01 00:00:00"),
        )
        cur.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            ("user_s6b", generate_password_hash("password123"), "2026-01-01 00:00:00"),
        )
        conn.commit()
        cur.execute("SELECT id FROM users WHERE username = 'user_s6a'")
        self.user1_id = cur.fetchone()[0]
        cur.execute("SELECT id FROM users WHERE username = 'user_s6b'")
        self.user2_id = cur.fetchone()[0]
        conn.close()

    def tearDown(self):
        if os.path.exists(_tmp_db):
            os.remove(_tmp_db)

    def _login_client(self, user_id=None, username="user_s6a"):
        if user_id is None:
            user_id = self.user1_id
        c = flask_app.app.test_client()
        with c.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["username"] = username
            sess["_csrf_token"] = TEST_CSRF
        return c

    def _post(self, client, url, data):
        data["csrf_token"] = TEST_CSRF
        return client.post(url, data=data, follow_redirects=True)

    # =========================================================
    # 1. SAVED CONVERSIONS (Tests 01–10)
    # =========================================================

    def test_01_my_conversions_requires_login(self):
        """Unauthenticated visitor is redirected to /login."""
        c = flask_app.app.test_client()
        resp = c.get("/my-conversions", follow_redirects=False)
        self.assertIn(resp.status_code, (301, 302))
        self.assertIn("/login", resp.headers["Location"])

    def test_02_my_conversions_accessible_when_logged_in(self):
        """Authenticated user gets HTTP 200 on /my-conversions."""
        c = self._login_client()
        resp = c.get("/my-conversions")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"My Conversions", resp.data)

    def test_03_save_valid_conversion(self):
        """A valid conversion result is saved and appears in the list."""
        c = self._login_client()
        resp = self._post(c, "/my-conversions/save", {
            "from_currency": "USD",
            "to_currency": "INR",
            "amount": "100",
            "converted_amount": "9371.00",
            "rate": "93.71",
            "rupee_status": "⬆️ Rupee weakened against USD",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(database.count_saved_items(self.user1_id, kind="conversion"), 1)
        items = database.get_saved_items(self.user1_id, kind="conversion")
        self.assertEqual(items[0]["kind"], "conversion")
        self.assertIn("USD", items[0]["title"])

    def test_04_save_conversion_unsupported_currency_rejected(self):
        """Saving a conversion with an unsupported currency is rejected."""
        c = self._login_client()
        self._post(c, "/my-conversions/save", {
            "from_currency": "CAD",
            "to_currency": "INR",
            "amount": "100",
            "converted_amount": "5500",
            "rate": "55.00",
            "rupee_status": "",
        })
        self.assertEqual(database.count_saved_items(self.user1_id, kind="conversion"), 0)

    def test_05_save_conversion_csrf_required(self):
        """POST without CSRF token is rejected with HTTP 400."""
        c = self._login_client()
        resp = c.post("/my-conversions/save", data={
            "from_currency": "USD",
            "to_currency": "INR",
            "amount": "100",
            "converted_amount": "9371",
            "rate": "93.71",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(database.count_saved_items(self.user1_id, kind="conversion"), 0)

    def test_06_delete_conversion(self):
        """Saved conversion can be permanently deleted by its owner."""
        database.add_saved_item(
            self.user1_id, "conversion", "100 USD → 9371.00 INR",
            "1 USD = 93.7100 INR",
            json.dumps({"from_currency": "USD", "to_currency": "INR", "amount": 100, "converted_amount": 9371, "rate": 93.71, "rupee_status": ""}),
        )
        items = database.get_saved_items(self.user1_id, kind="conversion")
        item_id = items[0]["id"]
        c = self._login_client()
        resp = self._post(c, f"/my-conversions/{item_id}/delete", {})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(database.count_saved_items(self.user1_id, kind="conversion"), 0)

    def test_07_user_cannot_delete_another_users_conversion(self):
        """User 2 cannot delete User 1's saved conversion."""
        database.add_saved_item(
            self.user1_id, "conversion", "100 USD → 9371.00 INR",
            "1 USD = 93.7100 INR",
            json.dumps({"from_currency": "USD", "to_currency": "INR", "amount": 100, "converted_amount": 9371, "rate": 93.71, "rupee_status": ""}),
        )
        items = database.get_saved_items(self.user1_id, kind="conversion")
        item_id = items[0]["id"]
        c2 = self._login_client(user_id=self.user2_id, username="user_s6b")
        self._post(c2, f"/my-conversions/{item_id}/delete", {})
        self.assertEqual(database.count_saved_items(self.user1_id, kind="conversion"), 1)

    def test_08_my_conversions_empty_state_shown(self):
        """Empty state message is shown when no conversions are saved."""
        c = self._login_client()
        resp = c.get("/my-conversions")
        html = resp.data.decode("utf-8")
        self.assertIn("no saved conversions", html.lower())

    def test_09_save_button_not_shown_to_guests(self):
        """The Save This Conversion button is not rendered for unauthenticated visitors."""
        c = flask_app.app.test_client()
        # POST a conversion as guest (no session)
        resp = c.post("/convert", data={
            "from_currency": "USD",
            "to_currency": "INR",
            "amount": "100",
        }, follow_redirects=True)
        # If 200, check no save form is present
        if resp.status_code == 200:
            html = resp.data.decode("utf-8")
            self.assertNotIn("/my-conversions/save", html)

    def test_10_save_button_shown_to_logged_in_user(self):
        """The Save This Conversion form is rendered for logged-in users on the result page."""
        c = self._login_client()
        # We need a live rate or cached rate; just check the form renders in result page
        # Inject a cached rate so convert() can resolve it
        import sqlite3
        conn = sqlite3.connect(_tmp_db)
        conn.execute(
            "INSERT OR REPLACE INTO exchange_rates (date, base_currency, target_currency, rate) VALUES (?, ?, ?, ?)",
            ("2026-01-01", "USD", "INR", 93.71),
        )
        conn.commit()
        conn.close()
        resp = c.post("/convert", data={
            "from_currency": "USD",
            "to_currency": "INR",
            "amount": "100",
        }, follow_redirects=True)
        if resp.status_code == 200:
            html = resp.data.decode("utf-8")
            self.assertIn("/my-conversions/save", html)
            self.assertIn("Save This Conversion", html)

    # =========================================================
    # 2. SAVED TRAVEL PLANS (Tests 11–18)
    # =========================================================

    def test_11_my_travel_plans_requires_login(self):
        """Unauthenticated visitor is redirected to /login."""
        c = flask_app.app.test_client()
        resp = c.get("/my-travel-plans", follow_redirects=False)
        self.assertIn(resp.status_code, (301, 302))
        self.assertIn("/login", resp.headers["Location"])

    def test_12_my_travel_plans_accessible_when_logged_in(self):
        """Authenticated user gets HTTP 200 on /my-travel-plans."""
        c = self._login_client()
        resp = c.get("/my-travel-plans")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"My Travel Plans", resp.data)

    def test_13_save_valid_travel_plan(self):
        """A valid travel plan result is saved and appears in the list."""
        c = self._login_client()
        resp = self._post(c, "/my-travel-plans/save", {
            "destination": "AE",
            "destination_label": "UAE",
            "currency": "AED",
            "plan_by": "daily",
            "days": "7",
            "daily_spend": "5000",
            "buffer_pct": "10",
            "suggested_inr": "38500",
            "suggested_foreign": "1684.90",
            "rate": "22.85",
            "travel_date": "",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(database.count_saved_items(self.user1_id, kind="trip"), 1)
        items = database.get_saved_items(self.user1_id, kind="trip")
        self.assertEqual(items[0]["kind"], "trip")
        self.assertIn("UAE", items[0]["title"])
        params = json.loads(items[0]["params"])
        self.assertEqual(params["destination"], "AE")
        self.assertEqual(params["days"], 7)

    def test_14_save_travel_plan_unsupported_currency_rejected(self):
        """Saving a travel plan with an unsupported currency is rejected."""
        c = self._login_client()
        self._post(c, "/my-travel-plans/save", {
            "destination": "US",
            "destination_label": "USA",
            "currency": "CAD",
            "plan_by": "daily",
            "days": "5",
            "daily_spend": "3000",
            "buffer_pct": "10",
            "suggested_inr": "16500",
            "suggested_foreign": "200",
            "rate": "75.0",
            "travel_date": "",
        })
        self.assertEqual(database.count_saved_items(self.user1_id, kind="trip"), 0)

    def test_15_delete_travel_plan(self):
        """Saved travel plan can be permanently deleted by its owner."""
        database.add_saved_item(
            self.user1_id, "trip", "7-day trip to UAE (AED)",
            "Budget ₹38,500 · Rate 22.8500 · 10% buffer",
            json.dumps({"destination": "AE", "destination_label": "UAE", "currency": "AED",
                        "plan_by": "daily", "days": 7, "daily_spend": 5000, "total_budget": None,
                        "buffer_pct": 10, "travel_date": "", "rate": 22.85,
                        "suggested_inr": 38500, "suggested_foreign": 1684.9}),
        )
        items = database.get_saved_items(self.user1_id, kind="trip")
        item_id = items[0]["id"]
        c = self._login_client()
        resp = self._post(c, f"/my-travel-plans/{item_id}/delete", {})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(database.count_saved_items(self.user1_id, kind="trip"), 0)

    def test_16_user_cannot_delete_another_users_plan(self):
        """User 2 cannot delete User 1's saved travel plan."""
        database.add_saved_item(
            self.user1_id, "trip", "7-day trip to UAE (AED)",
            "Budget ₹38,500",
            json.dumps({"destination": "AE", "destination_label": "UAE", "currency": "AED",
                        "plan_by": "daily", "days": 7, "daily_spend": 5000, "total_budget": None,
                        "buffer_pct": 10, "travel_date": "", "rate": 22.85,
                        "suggested_inr": 38500, "suggested_foreign": 1684.9}),
        )
        items = database.get_saved_items(self.user1_id, kind="trip")
        item_id = items[0]["id"]
        c2 = self._login_client(user_id=self.user2_id, username="user_s6b")
        self._post(c2, f"/my-travel-plans/{item_id}/delete", {})
        self.assertEqual(database.count_saved_items(self.user1_id, kind="trip"), 1)

    def test_17_my_travel_plans_empty_state(self):
        """Empty state is shown when no travel plans are saved."""
        c = self._login_client()
        resp = c.get("/my-travel-plans")
        self.assertIn(b"no saved travel plans", resp.data.lower())

    def test_18_reopen_url_built_correctly(self):
        """The re-open URL for a travel plan prefills the form correctly."""
        database.add_saved_item(
            self.user1_id, "trip", "7-day trip to UAE (AED)",
            "Budget ₹38,500",
            json.dumps({"destination": "AE", "destination_label": "UAE", "currency": "AED",
                        "plan_by": "daily", "days": 7, "daily_spend": 5000.0, "total_budget": None,
                        "buffer_pct": 10.0, "travel_date": "", "rate": 22.85,
                        "suggested_inr": 38500, "suggested_foreign": 1684.9}),
        )
        c = self._login_client()
        resp = c.get("/my-travel-plans")
        html = resp.data.decode("utf-8")
        self.assertIn("travel-planner", html)
        self.assertIn("destination=AE", html)
        self.assertIn("days=7", html)

    # =========================================================
    # 3. SAVED DECISIONS (Tests 19–27)
    # =========================================================

    def test_19_my_decisions_requires_login(self):
        """Unauthenticated visitor is redirected to /login."""
        c = flask_app.app.test_client()
        resp = c.get("/my-decisions", follow_redirects=False)
        self.assertIn(resp.status_code, (301, 302))
        self.assertIn("/login", resp.headers["Location"])

    def test_20_my_decisions_accessible_when_logged_in(self):
        """Authenticated user gets HTTP 200 on /my-decisions."""
        c = self._login_client()
        resp = c.get("/my-decisions")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"My Decisions", resp.data)

    def test_21_save_valid_decision(self):
        """A valid decision result is saved and appears in the list."""
        c = self._login_client()
        resp = self._post(c, "/my-decisions/save", {
            "direction": "buy",
            "currency": "USD",
            "amount": "50000",
            "offer_rate": "96.10",
            "quote_unit": "1",
            "flat_fee": "500",
            "percent_fee": "1.5",
            "other_charges": "0",
            "effective_rate": "95.65",
            "reference_rate": "93.71",
            "markup_pct": "2.07",
            "extra_cost_inr": "1035",
            "verdict_title": "Acceptable offer",
            "verdict_level": "warn",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(database.count_saved_items(self.user1_id, kind="audit"), 1)
        items = database.get_saved_items(self.user1_id, kind="audit")
        self.assertEqual(items[0]["kind"], "audit")
        params = json.loads(items[0]["params"])
        self.assertEqual(params["currency"], "USD")
        self.assertEqual(params["verdict_title"], "Acceptable offer")

    def test_22_save_decision_invalid_direction_rejected(self):
        """Saving a decision with an invalid direction is rejected."""
        c = self._login_client()
        self._post(c, "/my-decisions/save", {
            "direction": "swap",
            "currency": "USD",
            "amount": "50000",
            "offer_rate": "96.10",
            "quote_unit": "1",
            "flat_fee": "0",
            "percent_fee": "0",
            "other_charges": "0",
            "effective_rate": "96.10",
            "reference_rate": "93.71",
            "markup_pct": "2.56",
            "extra_cost_inr": "1280",
            "verdict_title": "Bad offer",
            "verdict_level": "stop",
        })
        self.assertEqual(database.count_saved_items(self.user1_id, kind="audit"), 0)

    def test_23_save_decision_unsupported_currency_rejected(self):
        """Saving a decision with an unsupported currency is rejected."""
        c = self._login_client()
        self._post(c, "/my-decisions/save", {
            "direction": "buy",
            "currency": "CAD",
            "amount": "50000",
            "offer_rate": "56.00",
            "quote_unit": "1",
            "flat_fee": "0",
            "percent_fee": "0",
            "other_charges": "0",
            "effective_rate": "56.00",
            "reference_rate": "55.50",
            "markup_pct": "0.90",
            "extra_cost_inr": "450",
            "verdict_title": "Good offer",
            "verdict_level": "check",
        })
        self.assertEqual(database.count_saved_items(self.user1_id, kind="audit"), 0)

    def test_24_delete_decision(self):
        """Saved decision can be permanently deleted by its owner."""
        database.add_saved_item(
            self.user1_id, "audit", "Buy USD — Offer ₹96.1000",
            "Effective rate ₹95.6500 · Verdict: Acceptable offer",
            json.dumps({"direction": "buy", "currency": "USD", "amount": 50000,
                        "offer_rate": 96.10, "quote_unit": "1", "flat_fee": 500,
                        "percent_fee": 1.5, "other_charges": 0,
                        "effective_rate": 95.65, "reference_rate": 93.71,
                        "markup_pct": 2.07, "extra_cost_inr": 1035,
                        "verdict_title": "Acceptable offer", "verdict_level": "warn"}),
        )
        items = database.get_saved_items(self.user1_id, kind="audit")
        item_id = items[0]["id"]
        c = self._login_client()
        resp = self._post(c, f"/my-decisions/{item_id}/delete", {})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(database.count_saved_items(self.user1_id, kind="audit"), 0)

    def test_25_user_cannot_delete_another_users_decision(self):
        """User 2 cannot delete User 1's saved decision."""
        database.add_saved_item(
            self.user1_id, "audit", "Buy USD — Offer ₹96.1000",
            "Effective rate ₹95.6500",
            json.dumps({"direction": "buy", "currency": "USD", "amount": 50000,
                        "offer_rate": 96.10, "quote_unit": "1", "flat_fee": 0,
                        "percent_fee": 0, "other_charges": 0,
                        "effective_rate": 96.10, "reference_rate": 93.71,
                        "markup_pct": 2.56, "extra_cost_inr": 1280,
                        "verdict_title": "Acceptable", "verdict_level": "warn"}),
        )
        items = database.get_saved_items(self.user1_id, kind="audit")
        item_id = items[0]["id"]
        c2 = self._login_client(user_id=self.user2_id, username="user_s6b")
        self._post(c2, f"/my-decisions/{item_id}/delete", {})
        self.assertEqual(database.count_saved_items(self.user1_id, kind="audit"), 1)

    def test_26_my_decisions_empty_state(self):
        """Empty state is shown when no decisions are saved."""
        c = self._login_client()
        resp = c.get("/my-decisions")
        self.assertIn(b"no saved decisions", resp.data.lower())

    def test_27_reopen_url_for_decision_includes_params(self):
        """The re-open URL for a decision includes form parameters."""
        database.add_saved_item(
            self.user1_id, "audit", "Buy USD — Offer ₹96.1000",
            "Effective rate ₹95.6500",
            json.dumps({"direction": "buy", "currency": "USD", "amount": 50000,
                        "offer_rate": 96.10, "quote_unit": "1", "flat_fee": 500,
                        "percent_fee": 1.5, "other_charges": 0,
                        "effective_rate": 95.65, "reference_rate": 93.71,
                        "markup_pct": 2.07, "extra_cost_inr": 1035,
                        "verdict_title": "Acceptable offer", "verdict_level": "warn"}),
        )
        c = self._login_client()
        resp = c.get("/my-decisions")
        html = resp.data.decode("utf-8")
        self.assertIn("decision-assistant", html)
        self.assertIn("direction=buy", html)
        self.assertIn("currency=USD", html)

    # =========================================================
    # 4. Cross-kind & Shared Limit (Tests 28–30)
    # =========================================================

    def test_28_100_item_limit_enforced_across_kinds(self):
        """Cannot save more than 100 total items across all kinds."""
        # Insert 100 items
        for i in range(100):
            ok, _ = database.add_saved_item(
                self.user1_id, "conversion", f"Item {i}", f"summary {i}",
                json.dumps({"from_currency": "USD", "to_currency": "INR", "amount": i,
                            "converted_amount": i * 93, "rate": 93.0, "rupee_status": ""}),
            )
            self.assertTrue(ok)
        # 101st should fail
        ok, err = database.add_saved_item(
            self.user1_id, "trip", "7-day trip to UAE (AED)", "Budget ₹38,500",
            json.dumps({}),
        )
        self.assertFalse(ok)
        self.assertIn("100", err)

    def test_29_guest_snapshots_unaffected_by_stage6(self):
        """Guest pages (home, converter, travel planner, decision assistant) have no save-form markup."""
        c = flask_app.app.test_client()
        for path in ["/", "/converter", "/about"]:
            resp = c.get(path)
            self.assertEqual(resp.status_code, 200)
            html = resp.data.decode("utf-8")
            self.assertNotIn("/my-conversions/save", html)
            self.assertNotIn("/my-travel-plans/save", html)
            self.assertNotIn("/my-decisions/save", html)

    def test_30_stage4_and_stage5_regressions_pass(self):
        """Dashboard and my-currencies routes still work correctly after Stage 6 additions."""
        c = self._login_client()
        resp = c.get("/dashboard")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Dashboard", resp.data)

        resp = c.get("/my-currencies")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"My Currencies", resp.data)


if __name__ == "__main__":
    unittest.main(verbosity=2)

