"""
Tests for the Forex Decision Assistant and the Travel Money Planner.
No internet is needed: the exchange-rate API call is mocked.

Run with:   python -m unittest test_new_features -v
"""
import unittest
from datetime import date, timedelta
from unittest.mock import patch

import forex_tools as ft
from app import app


class CompareOfferMath(unittest.TestCase):

    def test_buy_with_fees(self):
        r = ft.compare_offer("buy", "USD", 50000, 96.0, 94.5, flat_fee=100, percent_fee=0.5)
        self.assertAlmostEqual(r["total_fees"], 350.0)                 # 100 + 0.5% of 50,000
        self.assertAlmostEqual(r["total_paid_inr"], 50350.0)
        self.assertAlmostEqual(r["received_value"], 50000 / 96.0)
        self.assertAlmostEqual(r["extra_cost_inr"], 50350 - (50000 / 96.0) * 94.5, places=6)
        self.assertAlmostEqual(r["rate_margin_inr"] + r["total_fees"], r["extra_cost_inr"], places=6)
        self.assertAlmostEqual(r["effective_rate"], 50350 / (50000 / 96.0), places=6)
        self.assertGreater(r["shortfall_foreign"], 0)

    def test_sell_with_fees(self):
        r = ft.compare_offer("sell", "USD", 500, 92.0, 94.5, flat_fee=100, percent_fee=1)
        self.assertAlmostEqual(r["gross_inr"], 46000.0)
        self.assertAlmostEqual(r["total_fees"], 560.0)                 # 100 + 1% of 46,000
        self.assertAlmostEqual(r["received_value"], 45440.0)
        self.assertAlmostEqual(r["extra_cost_inr"], 47250 - 45440)
        self.assertAlmostEqual(r["effective_rate"], 45440 / 500)

    def test_offer_equal_to_reference_without_fees_is_neutral(self):
        for direction in ("buy", "sell"):
            r = ft.compare_offer(direction, "EUR", 1000, 106.28, 106.28)
            self.assertAlmostEqual(r["extra_cost_inr"], 0, places=6)
            self.assertAlmostEqual(r["markup_pct"], 0, places=6)
            self.assertEqual(r["verdict_level"], "good")

    def test_verdict_bands(self):
        ref = 100.0
        level = lambda offer: ft.compare_offer("buy", "USD", 1000, offer, ref)["verdict_level"]
        self.assertEqual(level(100.5), "good")      # 0.5%
        self.assertEqual(level(102.0), "ok")        # 2%
        self.assertEqual(level(105.0), "bad")       # 5%
        self.assertEqual(level(99.0), "check")      # better than reference: suspicious

    def test_unit_mistake_is_flagged(self):
        # Yen quoted per 100 (59.9) but typed as per 1 would be fine; the reverse is the mistake.
        r = ft.compare_offer("buy", "JPY", 10000, 59.9, 0.599)
        self.assertEqual(r["verdict_level"], "check")

    def test_invalid_inputs_raise(self):
        with self.assertRaises(ValueError):
            ft.compare_offer("buy", "USD", 0, 90, 90)
        with self.assertRaises(ValueError):
            ft.compare_offer("swap", "USD", 100, 90, 90)

    def test_checklist_has_sell_specific_item_and_confirm_item(self):
        buy = [t for t, _ in ft.build_checklist("buy", "USD")]
        sell = [t for t, _ in ft.build_checklist("sell", "USD")]
        self.assertIn("Which rate applies to selling?", sell)
        self.assertNotIn("Which rate applies to selling?", buy)
        self.assertEqual(buy[-1], "Confirm directly with the provider")


class TripPlanMath(unittest.TestCase):

    def test_daily_mode(self):
        p = ft.plan_trip("AED", 25.0, 10, daily_spend_inr=5000, buffer_pct=10)
        self.assertAlmostEqual(p["base_inr"], 50000)
        self.assertAlmostEqual(p["suggested_inr"], 55000)
        self.assertAlmostEqual(p["suggested_foreign"], 2200)
        self.assertAlmostEqual(p["daily_foreign"], 200)

    def test_total_mode(self):
        p = ft.plan_trip("AED", 25.0, 5, total_budget_inr=50000, buffer_pct=0)
        self.assertAlmostEqual(p["daily_inr"], 10000)
        self.assertAlmostEqual(p["suggested_inr"], 50000)
        self.assertAlmostEqual(p["base_foreign"], 2000)

    def test_scenarios(self):
        p = ft.plan_trip("USD", 100.0, 1, total_budget_inr=10000, buffer_pct=0)
        by_pct = {s["pct"]: s for s in p["scenarios"]}
        self.assertEqual(sorted(by_pct), sorted(ft.SCENARIO_STEPS))
        self.assertAlmostEqual(by_pct[0]["received_foreign"], 100)
        self.assertAlmostEqual(by_pct[5]["rate"], 105)
        self.assertAlmostEqual(by_pct[5]["received_foreign"], 10000 / 105)
        self.assertLess(by_pct[5]["foreign_change"], 0)         # weaker rupee -> fewer USD
        self.assertGreater(by_pct[-5]["foreign_change"], 0)
        self.assertAlmostEqual(by_pct[5]["inr_needed"], 10500)
        self.assertAlmostEqual(p["cushion_inr"], 10500)
        self.assertAlmostEqual(p["cushion_extra_inr"], 500)

    def test_bad_inputs(self):
        with self.assertRaises(ValueError):
            ft.plan_trip("USD", 0, 3, daily_spend_inr=100)
        with self.assertRaises(ValueError):
            ft.plan_trip("USD", 90, 0, daily_spend_inr=100)


class ParsingAndFormatting(unittest.TestCase):

    def parse(self, raw, **kw):
        errors = []
        return ft.parse_number(raw, "Field", errors, **kw), errors

    def test_valid_and_commas(self):
        self.assertEqual(self.parse("1,000.5")[0], 1000.5)

    def test_rejects_bad_values(self):
        for bad in ["abc", "-5", "nan", "inf", "1e999"]:
            value, errors = self.parse(bad)
            self.assertIsNone(value, bad)
            self.assertTrue(errors, bad)

    def test_zero_rules(self):
        self.assertIsNone(self.parse("0", allow_zero=False)[0])
        self.assertEqual(self.parse("0")[0], 0.0)

    def test_optional_default(self):
        self.assertEqual(self.parse("", required=False, default=7.0), (7.0, []))

    def test_maximum(self):
        self.assertIsNone(self.parse("101", maximum=100)[0])

    def test_indian_grouping(self):
        self.assertEqual(ft.format_inr(1234567.5), "12,34,567.50")
        self.assertEqual(ft.format_inr(100000), "1,00,000.00")
        self.assertEqual(ft.format_inr(999), "999.00")
        self.assertEqual(ft.format_inr(-1500), "-1,500.00")
        self.assertEqual(ft.format_inr(55000, 0), "55,000")

    def test_foreign_format(self):
        self.assertEqual(ft.format_foreign(1234.5, "USD"), "1,234.50")
        self.assertEqual(ft.format_foreign(1234.5, "JPY"), "1,234")  # banker's rounding of .5 is fine for display


LIVE = "app.get_exchange_rate"


class Routes(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        cls.client = app.test_client()

    def test_pages_load(self):
        for url in ("/decision-assistant", "/travel-planner", "/login"):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_dashboard_is_the_home_page(self):
        with patch(LIVE, return_value=None):
            r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Smart Recommendation", r.data)
        self.assertIn(b"Decision Assistant", r.data)

    def test_official_links_are_shown(self):
        html = self.client.get("/decision-assistant").data.decode()
        for r in ft.OFFICIAL_RESOURCES:
            self.assertIn(r["url"], html)
        self.assertIn("not an authorised forex provider", html)

    @patch(LIVE, return_value=94.5)
    def test_decision_buy(self, _):
        r = self.client.post("/decision-assistant", data={
            "direction": "buy", "currency": "USD", "amount": "50000",
            "offer_rate": "96", "quote_unit": "1", "flat_fee": "100", "percent_fee": "0.5"})
        html = r.data.decode()
        self.assertEqual(r.status_code, 200)
        self.assertIn("Total fees", html)
        self.assertIn("₹50,350.00", html)                      # total paid, Indian grouping
        self.assertIn("Before you accept an offer", html)

    @patch(LIVE, return_value=94.5)
    def test_decision_sell(self, _):
        r = self.client.post("/decision-assistant", data={
            "direction": "sell", "currency": "USD", "amount": "500",
            "offer_rate": "92", "percent_fee": "1", "flat_fee": "100"})
        self.assertIn("₹45,440.00", r.data.decode())

    @patch(LIVE, return_value=0.6)
    def test_yen_quoted_per_100(self, _):
        r = self.client.post("/decision-assistant", data={
            "direction": "buy", "currency": "JPY", "amount": "10000",
            "offer_rate": "60.5", "quote_unit": "100"})
        html = r.data.decode()
        self.assertIn("Close to the reference rate", html)     # 0.605 vs 0.600 -> within ~1%

    @patch(LIVE, return_value=94.5)
    def test_decision_validation_errors(self, _):
        r = self.client.post("/decision-assistant", data={
            "direction": "buy", "currency": "USD", "amount": "abc", "offer_rate": "-3"})
        html = r.data.decode()
        self.assertEqual(r.status_code, 200)
        self.assertIn("Amount must be a number.", html)
        self.assertIn("Offered rate must be greater than 0.", html)
        self.assertNotIn("Total fees", html)

    @patch(LIVE, return_value=94.5)
    def test_decision_tampered_values_fall_back(self, _):
        r = self.client.post("/decision-assistant", data={
            "direction": "hack", "currency": "XXX", "amount": "1000", "offer_rate": "95"})
        self.assertEqual(r.status_code, 200)

    @patch(LIVE, return_value=None)
    def test_decision_uses_saved_rate_when_offline(self, _):
        with patch("app.get_latest_rate_with_date", return_value=(94.0, "2026-11-01")):
            r = self.client.post("/decision-assistant", data={
                "direction": "buy", "currency": "USD", "amount": "1000", "offer_rate": "95"})
        html = r.data.decode()
        self.assertIn("Live rates could not be loaded", html)
        self.assertIn("2026-11-01", html)

    @patch(LIVE, return_value=None)
    def test_decision_with_no_rate_at_all(self, _):
        with patch("app.get_latest_rate_with_date", return_value=None):
            r = self.client.post("/decision-assistant", data={
                "direction": "buy", "currency": "USD", "amount": "1000", "offer_rate": "95"})
        self.assertIn("could not get a reference rate", r.data.decode())

    def test_prefill_from_query_string(self):
        html = self.client.get("/decision-assistant?currency=AED&amount=55000&direction=buy").data.decode()
        self.assertIn('value="55000"', html)
        self.assertIn('<option value="AED" selected>', html)

    @patch(LIVE, return_value=25.77)
    def test_travel_daily(self, _):
        r = self.client.post("/travel-planner", data={
            "destination": "AE", "plan_by": "daily", "days": "10",
            "daily_spend": "5000", "buffer_pct": "10"})
        html = r.data.decode()
        self.assertEqual(r.status_code, 200)
        self.assertIn("₹55,000", html)                         # suggested exchange budget
        self.assertIn("Rupee weakens 5%", html)
        self.assertIn("planning estimate", html)
        self.assertIn("/decision-assistant?direction=buy&amp;currency=AED&amp;amount=55000", html)

    @patch(LIVE, return_value=25.77)
    def test_travel_total_with_future_date(self, _):
        d = (date.today() + timedelta(days=30)).isoformat()
        r = self.client.post("/travel-planner", data={
            "destination": "AE", "plan_by": "total", "days": "7",
            "total_budget": "50000", "buffer_pct": "10", "travel_date": d})
        html = r.data.decode()
        self.assertIn("30 days from today", html)
        self.assertIn("₹55,000", html)

    @patch(LIVE, return_value=25.77)
    def test_travel_validation(self, _):
        past = (date.today() - timedelta(days=1)).isoformat()
        r = self.client.post("/travel-planner", data={
            "destination": "AE", "plan_by": "daily", "days": "2.5",
            "daily_spend": "", "travel_date": past})
        html = r.data.decode()
        self.assertIn("whole number of days", html)
        self.assertIn("Daily spending is required.", html)
        self.assertIn("Travel date cannot be in the past.", html)

    @patch(LIVE, return_value=None)
    def test_travel_with_no_rate(self, _):
        with patch("app.get_latest_rate_with_date", return_value=None):
            r = self.client.post("/travel-planner", data={
                "destination": "JP", "plan_by": "daily", "days": "3", "daily_spend": "4000"})
        self.assertIn("could not get an exchange rate", r.data.decode())

    @patch(LIVE, return_value=0.6)
    def test_travel_japan_shows_whole_yen(self, _):
        r = self.client.post("/travel-planner", data={
            "destination": "JP", "plan_by": "daily", "days": "5", "daily_spend": "6000"})
        html = r.data.decode()
        self.assertEqual(r.status_code, 200)
        self.assertIn("JPY", html)


if __name__ == "__main__":
    unittest.main()
