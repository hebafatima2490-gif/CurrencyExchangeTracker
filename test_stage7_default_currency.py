"""
Stage 7 — Default Currency Integration Tests
=============================================
Tests cover:
  - Converter GET: guest defaults unchanged
  - Converter GET: logged-in user gets saved default currency preselected
  - Converter GET: explicit query params override saved preference
  - Converter GET: invalid/missing params fall back gracefully
  - Converter GET: saved-conversion reopen restores From, To, Amount
  - Converter GET: form is NOT auto-submitted (GET only, no conversion performed)
  - Decision Assistant GET: guest defaults unchanged
  - Decision Assistant GET: logged-in user gets saved default currency
  - Decision Assistant GET: explicit ?currency= param overrides preference
  - Decision Assistant POST: unaffected by preference logic
  - User preference isolation between accounts
  - Regression: Stages 2-6 test suites pass (called separately)
"""

import sys
import os
import json
import unittest
import re
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as flask_app
import database


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register_and_login(client, username, password="Password1"):
    with client.session_transaction() as sess:
        sess["_csrf_token"] = "testtoken"
    client.post("/register", data={
        "username": username,
        "password": password,
        "csrf_token": "testtoken",
    }, follow_redirects=True)
    with client.session_transaction() as sess:
        sess["_csrf_token"] = "testtoken"
    client.post("/login", data={
        "username": username,
        "password": password,
        "csrf_token": "testtoken",
    }, follow_redirects=True)


def _set_default_currency(client, currency):
    """Set the user's default currency via the My Currencies POST route."""
    with client.session_transaction() as sess:
        sess["_csrf_token"] = "testtoken"
    client.post("/my-currencies/default", data={
        "default_currency": currency,
        "csrf_token": "testtoken",
    }, follow_redirects=True)


def _selected_from(html_text):
    """Return the value of the selected From-currency option."""
    m = re.search(
        r'<option value="([^"]+)"[^>]*selected[^>]*>(?:.*?)</option>',
        html_text,
        re.DOTALL,
    )
    # More robust: find all options in from_currency select, return the selected one
    from_block = re.search(
        r'id="from_currency"[^>]*>(.*?)</select>',
        html_text, re.DOTALL,
    )
    if from_block:
        opts = re.findall(
            r'<option value="([^"]+)"[^>]*selected[^>]*>',
            from_block.group(1),
        )
        return opts[0] if opts else None
    return None


def _selected_to(html_text):
    """Return the value of the selected To-currency option."""
    to_block = re.search(
        r'id="to_currency"[^>]*>(.*?)</select>',
        html_text, re.DOTALL,
    )
    if to_block:
        opts = re.findall(
            r'<option value="([^"]+)"[^>]*selected[^>]*>',
            to_block.group(1),
        )
        return opts[0] if opts else None
    return None


def _amount_value(html_text):
    """Return the value attribute of the amount input."""
    m = re.search(r'id="amount"[^>]*value="([^"]*)"', html_text)
    return m.group(1) if m else None


def _selected_decision_currency(html_text):
    """Return the selected currency in the decision assistant form."""
    cur_block = re.search(
        r'id="currency"[^>]*>(.*?)</select>',
        html_text, re.DOTALL,
    )
    if cur_block:
        opts = re.findall(
            r'<option value="([^"]+)"[^>]*selected[^>]*>',
            cur_block.group(1),
        )
        return opts[0] if opts else None
    return None


# ---------------------------------------------------------------------------
# Base test case
# ---------------------------------------------------------------------------

class Stage7TestCase(unittest.TestCase):
    def setUp(self):
        flask_app.app.config["TESTING"] = True
        flask_app.app.config["WTF_CSRF_ENABLED"] = False
        flask_app.app.config["SECRET_KEY"] = "test-secret-stage7"
        self.client = flask_app.app.test_client()
        # Restore a clean database state
        database.create_database()

    def tearDown(self):
        pass


# ---------------------------------------------------------------------------
# 1. Converter — guest behaviour (unchanged)
# ---------------------------------------------------------------------------

class TestConverterGuest(Stage7TestCase):

    def test_01_guest_converter_from_defaults_to_usd(self):
        """Guest GET /converter: From currency must default to USD."""
        r = self.client.get("/converter")
        self.assertEqual(r.status_code, 200)
        html = r.data.decode()
        self.assertEqual(_selected_from(html), "USD",
                         "Guest From currency must default to USD")

    def test_02_guest_converter_to_defaults_to_inr(self):
        """Guest GET /converter: To currency must default to INR."""
        r = self.client.get("/converter")
        html = r.data.decode()
        self.assertEqual(_selected_to(html), "INR",
                         "Guest To currency must default to INR")

    def test_03_guest_converter_amount_defaults_to_100(self):
        """Guest GET /converter: Amount field must default to 100."""
        r = self.client.get("/converter")
        html = r.data.decode()
        self.assertEqual(_amount_value(html), "100",
                         "Guest amount must default to 100")

    def test_04_guest_converter_explicit_param_from_eur(self):
        """Guest GET /converter?from_currency=EUR: EUR should be preselected."""
        r = self.client.get("/converter?from_currency=EUR")
        html = r.data.decode()
        self.assertEqual(_selected_from(html), "EUR",
                         "Valid explicit param should be respected for guests too")

    def test_05_guest_converter_invalid_param_falls_back_to_usd(self):
        """Guest GET /converter?from_currency=XYZ: invalid param → USD fallback."""
        r = self.client.get("/converter?from_currency=XYZ")
        html = r.data.decode()
        self.assertEqual(_selected_from(html), "USD",
                         "Invalid param must fall back to USD for guests")

    def test_06_guest_no_account_ui_in_converter(self):
        """Guest converter page must not contain account-specific UI."""
        r = self.client.get("/converter")
        html = r.data.decode()
        self.assertNotIn("acct-save-result-block", html,
                         "Guest converter must not show save-result block")


# ---------------------------------------------------------------------------
# 2. Converter — authenticated user defaults
# ---------------------------------------------------------------------------

class TestConverterAuthenticated(Stage7TestCase):

    def _login_with_pref(self, username, currency):
        _register_and_login(self.client, username)
        _set_default_currency(self.client, currency)

    def test_07_logged_in_default_eur_preselected(self):
        """Logged-in user with default EUR: converter From shows EUR."""
        self._login_with_pref("user_eur_7", "EUR")
        r = self.client.get("/converter")
        html = r.data.decode()
        self.assertEqual(_selected_from(html), "EUR")

    def test_08_logged_in_default_gbp_preselected(self):
        """Logged-in user with default GBP: converter From shows GBP."""
        self._login_with_pref("user_gbp_7", "GBP")
        r = self.client.get("/converter")
        html = r.data.decode()
        self.assertEqual(_selected_from(html), "GBP")

    def test_09_logged_in_default_jpy_preselected(self):
        """Logged-in user with default JPY: converter From shows JPY."""
        self._login_with_pref("user_jpy_7", "JPY")
        r = self.client.get("/converter")
        html = r.data.decode()
        self.assertEqual(_selected_from(html), "JPY")

    def test_10_logged_in_default_aed_preselected(self):
        """Logged-in user with default AED: converter From shows AED."""
        self._login_with_pref("user_aed_7", "AED")
        r = self.client.get("/converter")
        html = r.data.decode()
        self.assertEqual(_selected_from(html), "AED")

    def test_11_logged_in_default_usd_preselected(self):
        """Logged-in user with default USD: converter From shows USD."""
        self._login_with_pref("user_usd_7", "USD")
        r = self.client.get("/converter")
        html = r.data.decode()
        self.assertEqual(_selected_from(html), "USD")

    def test_12_to_currency_always_inr_regardless_of_preference(self):
        """To currency must always default to INR regardless of user preference."""
        self._login_with_pref("user_to_7", "GBP")
        r = self.client.get("/converter")
        html = r.data.decode()
        self.assertEqual(_selected_to(html), "INR")

    def test_13_amount_still_defaults_to_100_for_logged_in(self):
        """Amount field defaults to 100 for logged-in users with no param."""
        self._login_with_pref("user_amt_7", "EUR")
        r = self.client.get("/converter")
        html = r.data.decode()
        self.assertEqual(_amount_value(html), "100")


# ---------------------------------------------------------------------------
# 3. Converter — explicit param priority over preference
# ---------------------------------------------------------------------------

class TestConverterParamPriority(Stage7TestCase):

    def setUp(self):
        super().setUp()
        _register_and_login(self.client, "prio_user_7")
        _set_default_currency(self.client, "JPY")

    def test_14_explicit_from_param_beats_preference(self):
        """?from_currency=EUR with default JPY → EUR selected (param wins)."""
        r = self.client.get("/converter?from_currency=EUR")
        html = r.data.decode()
        self.assertEqual(_selected_from(html), "EUR")

    def test_15_explicit_to_param_beats_default_inr(self):
        """?to_currency=USD → USD selected as To."""
        r = self.client.get("/converter?to_currency=USD")
        html = r.data.decode()
        self.assertEqual(_selected_to(html), "USD")

    def test_16_explicit_amount_param_prefills_amount(self):
        """?amount=750 → amount field shows 750."""
        r = self.client.get("/converter?amount=750")
        html = r.data.decode()
        self.assertEqual(_amount_value(html), "750")

    def test_17_inr_valid_as_explicit_from(self):
        """?from_currency=INR → INR selected as From (INR is valid in converter)."""
        r = self.client.get("/converter?from_currency=INR")
        html = r.data.decode()
        self.assertEqual(_selected_from(html), "INR")

    def test_18_invalid_from_param_falls_back_to_preference(self):
        """?from_currency=INVALID with default JPY → JPY shown (invalid param discarded)."""
        r = self.client.get("/converter?from_currency=INVALID")
        html = r.data.decode()
        self.assertEqual(_selected_from(html), "JPY")

    def test_19_negative_amount_falls_back_to_100(self):
        """?amount=-50 → amount falls back to 100 (negative rejected)."""
        r = self.client.get("/converter?amount=-50")
        html = r.data.decode()
        self.assertEqual(_amount_value(html), "100")

    def test_20_zero_amount_falls_back_to_100(self):
        """?amount=0 → amount falls back to 100 (zero rejected)."""
        r = self.client.get("/converter?amount=0")
        html = r.data.decode()
        self.assertEqual(_amount_value(html), "100")

    def test_21_non_numeric_amount_falls_back_to_100(self):
        """?amount=abc → amount falls back to 100 (non-numeric rejected)."""
        r = self.client.get("/converter?amount=abc")
        html = r.data.decode()
        self.assertEqual(_amount_value(html), "100")

    def test_22_invalid_to_param_falls_back_to_inr(self):
        """?to_currency=BOGUS → To falls back to INR."""
        r = self.client.get("/converter?to_currency=BOGUS")
        html = r.data.decode()
        self.assertEqual(_selected_to(html), "INR")


# ---------------------------------------------------------------------------
# 4. Saved-conversion reopening
# ---------------------------------------------------------------------------

class TestConverterReopenSavedConversion(Stage7TestCase):

    def setUp(self):
        super().setUp()
        _register_and_login(self.client, "reopen_user_7")
        _set_default_currency(self.client, "GBP")  # preference ≠ saved conversion currency

    def test_23_reopen_url_contains_from_to_amount(self):
        """_build_reopen_url for conversion includes from_currency, to_currency, amount."""
        from account import _build_reopen_url
        params = {
            "from_currency": "EUR",
            "to_currency": "INR",
            "amount": 500.0,
            "converted_amount": 44950.0,
            "rate": 89.9,
            "rupee_status": "",
        }
        with flask_app.app.test_request_context():
            url = _build_reopen_url("conversion", params)
        self.assertIn("from_currency=EUR", url)
        self.assertIn("to_currency=INR", url)
        self.assertIn("amount=500.0", url)
        self.assertNotIn("converted_amount", url,
                         "Historical snapshot fields must not appear in reopen URL")
        self.assertNotIn("rate=", url)

    def test_24_reopen_url_restores_from_currency_over_preference(self):
        """Converter loaded via reopen URL shows saved From currency, not user preference."""
        # User preference = GBP, saved conversion was EUR
        r = self.client.get("/converter?from_currency=EUR&to_currency=INR&amount=500")
        html = r.data.decode()
        self.assertEqual(_selected_from(html), "EUR",
                         "Saved EUR must win over GBP preference")

    def test_25_reopen_url_restores_to_currency(self):
        """Converter loaded via reopen URL shows saved To currency."""
        r = self.client.get("/converter?from_currency=EUR&to_currency=USD&amount=200")
        html = r.data.decode()
        self.assertEqual(_selected_to(html), "USD")

    def test_26_reopen_url_restores_amount(self):
        """Converter loaded via reopen URL shows saved amount."""
        r = self.client.get("/converter?from_currency=JPY&to_currency=INR&amount=10000")
        html = r.data.decode()
        self.assertEqual(_amount_value(html), "10000")

    def test_27_reopen_does_not_auto_submit(self):
        """GET /converter (reopen) must not contain a conversion result — no auto-submit."""
        r = self.client.get("/converter?from_currency=EUR&to_currency=INR&amount=500")
        html = r.data.decode()
        # Conversion result page contains "Exchange Voucher" — converter form page does not
        self.assertNotIn("Exchange Voucher", html,
                         "GET /converter must never auto-submit conversion")
        self.assertNotIn("converted_amount", html.lower())

    def test_28_reopen_url_empty_params_falls_back_to_preference(self):
        """_build_reopen_url with empty params returns plain /converter (no crash)."""
        from account import _build_reopen_url
        with flask_app.app.test_request_context():
            url = _build_reopen_url("conversion", {})
        self.assertEqual(url, "/converter")

    def test_29_my_conversions_page_shows_reopen_link(self):
        """My Conversions table row must contain a Reopen link (not 'New Conversion')."""
        # Save a conversion via the DB helper directly
        user_id = None
        with flask_app.app.test_request_context():
            with self.client.session_transaction() as sess:
                user_id = sess.get("user_id")
        if user_id is None:
            # Obtain from DB
            import sqlite3
            conn = sqlite3.connect(database.DATABASE_NAME)
            cur = conn.cursor()
            cur.execute("SELECT id FROM users WHERE username = ?", ("reopen_user_7",))
            row = cur.fetchone()
            conn.close()
            user_id = row[0] if row else None
        self.assertIsNotNone(user_id)
        params = json.dumps({
            "from_currency": "AED",
            "to_currency": "INR",
            "amount": 300.0,
            "converted_amount": 6900.0,
            "rate": 23.0,
            "rupee_status": "",
        })
        database.add_saved_item(user_id, "conversion", "300 AED → 6900.00 INR",
                                "1 AED = 23.0000 INR", params)
        r = self.client.get("/my-conversions")
        html = r.data.decode()
        self.assertIn("Reopen", html, "My Conversions must show Reopen link")
        self.assertIn("from_currency=AED", html, "Reopen link must include from_currency=AED")
        self.assertNotIn(">New Conversion<", html,
                         "Old 'New Conversion' text must not appear in table rows")


# ---------------------------------------------------------------------------
# 5. Decision Assistant — guest behaviour (unchanged)
# ---------------------------------------------------------------------------

class TestDecisionAssistantGuest(Stage7TestCase):

    def test_30_guest_decision_assistant_defaults_to_usd(self):
        """Guest GET /decision-assistant: currency defaults to USD."""
        r = self.client.get("/decision-assistant")
        self.assertEqual(r.status_code, 200)
        html = r.data.decode()
        self.assertEqual(_selected_decision_currency(html), "USD")

    def test_31_guest_decision_assistant_explicit_param_respected(self):
        """Guest GET /decision-assistant?currency=GBP: GBP selected."""
        r = self.client.get("/decision-assistant?currency=GBP")
        html = r.data.decode()
        self.assertEqual(_selected_decision_currency(html), "GBP")

    def test_32_guest_decision_invalid_param_falls_back_to_usd(self):
        """Guest GET /decision-assistant?currency=XYZ: falls back to USD."""
        r = self.client.get("/decision-assistant?currency=XYZ")
        html = r.data.decode()
        self.assertEqual(_selected_decision_currency(html), "USD")


# ---------------------------------------------------------------------------
# 6. Decision Assistant — authenticated user preference
# ---------------------------------------------------------------------------

class TestDecisionAssistantAuthenticated(Stage7TestCase):

    def _login_with_pref(self, username, currency):
        _register_and_login(self.client, username)
        _set_default_currency(self.client, currency)

    def test_33_logged_in_decision_uses_saved_default_eur(self):
        """Logged-in user with default EUR: decision assistant shows EUR on fresh GET."""
        self._login_with_pref("da_eur_7", "EUR")
        r = self.client.get("/decision-assistant")
        html = r.data.decode()
        self.assertEqual(_selected_decision_currency(html), "EUR")

    def test_34_logged_in_decision_uses_saved_default_gbp(self):
        """Logged-in user with default GBP: decision assistant shows GBP on fresh GET."""
        self._login_with_pref("da_gbp_7", "GBP")
        r = self.client.get("/decision-assistant")
        html = r.data.decode()
        self.assertEqual(_selected_decision_currency(html), "GBP")

    def test_35_logged_in_decision_uses_saved_default_jpy(self):
        """Logged-in user with default JPY: decision assistant shows JPY."""
        self._login_with_pref("da_jpy_7", "JPY")
        r = self.client.get("/decision-assistant")
        html = r.data.decode()
        self.assertEqual(_selected_decision_currency(html), "JPY")

    def test_36_logged_in_decision_uses_saved_default_aed(self):
        """Logged-in user with default AED: decision assistant shows AED."""
        self._login_with_pref("da_aed_7", "AED")
        r = self.client.get("/decision-assistant")
        html = r.data.decode()
        self.assertEqual(_selected_decision_currency(html), "AED")

    def test_37_explicit_currency_param_beats_preference_in_decision(self):
        """?currency=USD with preference GBP → USD shown (param wins)."""
        self._login_with_pref("da_prio_7", "GBP")
        r = self.client.get("/decision-assistant?currency=USD")
        html = r.data.decode()
        self.assertEqual(_selected_decision_currency(html), "USD")

    def test_38_reopen_saved_decision_preserves_original_currency(self):
        """Reopen URL ?currency=JPY with preference EUR → JPY selected."""
        self._login_with_pref("da_reopen_7", "EUR")
        reopen_url = "/decision-assistant?currency=JPY&direction=buy&amount=50000&offer_rate=0.68"
        r = self.client.get(reopen_url)
        html = r.data.decode()
        self.assertEqual(_selected_decision_currency(html), "JPY")

    def test_39_decision_post_calculation_unaffected_by_preference(self):
        """POST to decision assistant still processes correctly; preference not applied to POST."""
        self._login_with_pref("da_post_7", "AED")
        with self.client.session_transaction() as sess:
            sess["_csrf_token"] = "testtoken"
        r = self.client.post("/decision-assistant", data={
            "direction": "buy",
            "currency": "USD",
            "amount": "10000",
            "offer_rate": "84.5",
            "quote_unit": "1",
            "flat_fee": "",
            "percent_fee": "",
            "other_charges": "",
            "csrf_token": "testtoken",
        }, follow_redirects=True)
        # Either shows result or rate-unavailable message — must not 500
        self.assertIn(r.status_code, [200, 503])
        html = r.data.decode()
        # Form should echo back USD (the POSTed currency), not AED preference
        self.assertIn("USD", html)


# ---------------------------------------------------------------------------
# 7. User preference isolation
# ---------------------------------------------------------------------------

class TestUserPreferenceIsolation(Stage7TestCase):

    def test_40_preferences_isolated_between_accounts(self):
        """Two users with different preferences each see their own default currency."""
        # User A: EUR
        client_a = flask_app.app.test_client()
        _register_and_login(client_a, "iso_user_a_7")
        _set_default_currency(client_a, "EUR")
        r_a = client_a.get("/converter")
        html_a = r_a.data.decode()
        self.assertEqual(_selected_from(html_a), "EUR")

        # User B: AED — different client, different session
        client_b = flask_app.app.test_client()
        _register_and_login(client_b, "iso_user_b_7")
        _set_default_currency(client_b, "AED")
        r_b = client_b.get("/converter")
        html_b = r_b.data.decode()
        self.assertEqual(_selected_from(html_b), "AED")

        # User A's preference unchanged
        r_a2 = client_a.get("/converter")
        html_a2 = r_a2.data.decode()
        self.assertEqual(_selected_from(html_a2), "EUR")


# ---------------------------------------------------------------------------
# 8. Protected files and historical route integrity
# ---------------------------------------------------------------------------

class TestProtectedFilesIntegrity(Stage7TestCase):

    def test_41_history_route_still_loads(self):
        """/history route still responds 200 — historical graph unaffected."""
        r = self.client.get("/history")
        self.assertEqual(r.status_code, 200)

    def test_42_home_route_still_loads(self):
        """/ route still responds — live rate cards unaffected."""
        r = self.client.get("/")
        self.assertIn(r.status_code, [200, 503])  # 503 if API offline

    def test_43_decision_calculations_unchanged_for_guest(self):
        """Decision Assistant calculation logic unchanged — guest POST route still works."""
        with self.client.session_transaction() as sess:
            sess["_csrf_token"] = "testtoken"
        r = self.client.post("/decision-assistant", data={
            "direction": "buy",
            "currency": "USD",
            "amount": "5000",
            "offer_rate": "85.00",
            "quote_unit": "1",
            "flat_fee": "",
            "percent_fee": "",
            "other_charges": "",
            "csrf_token": "testtoken",
        }, follow_redirects=True)
        self.assertIn(r.status_code, [200, 503])

    def test_44_converter_post_route_still_works(self):
        """/convert POST still accepts valid form submission."""
        with self.client.session_transaction() as sess:
            sess["_csrf_token"] = "testtoken"
        r = self.client.post("/convert", data={
            "from_currency": "USD",
            "to_currency": "INR",
            "amount": "100",
        })
        self.assertIn(r.status_code, [200, 503])


# ---------------------------------------------------------------------------
# 9. Stage 2–6 regression smoke tests (critical routes)
# ---------------------------------------------------------------------------

class TestRegression(Stage7TestCase):

    def test_45_login_route_still_works(self):
        """/login GET still returns 200."""
        r = self.client.get("/login")
        self.assertEqual(r.status_code, 200)

    def test_46_register_route_still_works(self):
        """/register GET still returns 200."""
        r = self.client.get("/register")
        self.assertEqual(r.status_code, 200)

    def test_47_dashboard_requires_login(self):
        """/dashboard redirects to login for unauthenticated users."""
        r = self.client.get("/dashboard")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers.get("Location", ""))

    def test_48_my_currencies_requires_login(self):
        """/my-currencies redirects to login for unauthenticated users."""
        r = self.client.get("/my-currencies")
        self.assertEqual(r.status_code, 302)

    def test_49_my_conversions_requires_login(self):
        """/my-conversions redirects to login for unauthenticated users."""
        r = self.client.get("/my-conversions")
        self.assertEqual(r.status_code, 302)

    def test_50_my_travel_plans_requires_login(self):
        """/my-travel-plans redirects to login for unauthenticated users."""
        r = self.client.get("/my-travel-plans")
        self.assertEqual(r.status_code, 302)

    def test_51_my_decisions_requires_login(self):
        """/my-decisions redirects to login for unauthenticated users."""
        r = self.client.get("/my-decisions")
        self.assertEqual(r.status_code, 302)

    def test_52_csrf_required_for_account_post(self):
        """Account blueprint POST routes reject requests without CSRF token (400)."""
        _register_and_login(self.client, "csrf_check_7")
        r = self.client.post("/my-currencies/default", data={
            "default_currency": "EUR",
            # deliberately omitting csrf_token
        })
        self.assertEqual(r.status_code, 400)

    def test_53_about_page_unaffected(self):
        """/about still loads."""
        r = self.client.get("/about")
        self.assertEqual(r.status_code, 200)

    def test_54_travel_planner_still_loads(self):
        """/travel-planner GET still loads."""
        r = self.client.get("/travel-planner")
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)

