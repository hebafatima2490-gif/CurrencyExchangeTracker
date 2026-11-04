"""
Calculation logic for the two decision-support features:

  1. Forex Decision Assistant  - compares a provider's offer with a reference rate
  2. Travel Money Planner      - budget estimate + exchange-rate scenarios

Everything here is plain Python (no Flask, no network, no database) so it can be
unit-tested and explained easily.

Rate convention used everywhere in this file:
    rate = INR per 1 unit of foreign currency   (e.g. USD->INR = 94.56)
"""

# ---------------------------------------------------------------------------
# Static data
# ---------------------------------------------------------------------------

SUPPORTED_CURRENCIES = {
    "USD": "US Dollar",
    "EUR": "Euro",
    "GBP": "British Pound",
    "JPY": "Japanese Yen",
    "AED": "UAE Dirham",
}

# Destinations map to the currencies the tracker already supports.
DESTINATIONS = [
    ("AE", "UAE (Dubai, Abu Dhabi)", "AED"),
    ("US", "United States", "USD"),
    ("GB", "United Kingdom", "GBP"),
    ("EU", "Eurozone (France, Germany, Italy...)", "EUR"),
    ("JP", "Japan", "JPY"),
]

# Rupee-move scenarios shown in the Travel Money Planner (percent).
SCENARIO_STEPS = [5, 2, 1, 0, -1, -2, -5]   # +ve = rupee weakens (rate rises)

DEFAULT_BUFFER_PCT = 10.0

LINKS_CHECKED_ON = "4 November 2026"

# Official sources. Verified on LINKS_CHECKED_ON. The app links to these so users
# can verify things themselves; the app is NOT an authorised forex provider.
OFFICIAL_RESOURCES = [
    {
        "name": "RBI Master Direction: Money Changing Activities",
        "url": "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=11518",
        "note": "The rules that RBI-authorised money changers and banks follow. "
                "Use it to understand who is allowed to sell or buy foreign exchange.",
    },
    {
        "name": "FBIL: official INR reference rates",
        "url": "https://www.fbil.org.in/#/home",
        "note": "Since July 2018 the reference rates RBI used to publish are computed and "
                "published by FBIL (USD, EUR, GBP and JPY against INR; AED is not in that list).",
    },
    {
        "name": "Reserve Bank of India",
        "url": "https://www.rbi.org.in",
        "note": "Main RBI website for regulations, notices and public guidance.",
    },
    {
        "name": "Bank of Baroda: Multi Currency Forex Card",
        "url": "https://www.bankofbaroda.in/personal-banking/digital-products/cards/"
               "prepaid-cards/travel-card-multi-currency-forex-card",
        "note": "An example of a bank's official forex product page. It is shown as an "
                "example only, not a recommendation or a guarantee that forex is available.",
    },
]


# ---------------------------------------------------------------------------
# Input parsing
# ---------------------------------------------------------------------------

def parse_number(raw, label, errors, minimum=0.0, maximum=None, required=True,
                 allow_zero=True, default=None):
    """Parse a form value into a float. Appends a readable message to `errors`
    and returns None when the value is unusable."""
    text = (raw or "").strip().replace(",", "")
    if text == "":
        if required:
            errors.append(f"{label} is required.")
            return None
        return default
    try:
        value = float(text)
    except ValueError:
        errors.append(f"{label} must be a number.")
        return None
    if value != value or value in (float("inf"), float("-inf")):
        errors.append(f"{label} must be a valid number.")
        return None
    if value < minimum or (not allow_zero and value == 0):
        if allow_zero:
            errors.append(f"{label} cannot be less than {minimum:g}.")
        else:
            errors.append(f"{label} must be greater than {minimum:g}.")
        return None
    if maximum is not None and value > maximum:
        errors.append(f"{label} cannot be more than {maximum:g}.")
        return None
    return value


# ---------------------------------------------------------------------------
# Feature 1: Forex Decision Assistant
# ---------------------------------------------------------------------------

def compare_offer(direction, currency, amount, offer_rate, reference_rate,
                  flat_fee=0.0, percent_fee=0.0, other_charges=0.0):
    """
    Compare a provider's offer with a reference rate.

    direction = "buy"  : the user pays INR and receives foreign currency.
                         `amount` is the INR amount being exchanged.
                         Fees are charged ON TOP of `amount`.
    direction = "sell" : the user hands over foreign currency and receives INR.
                         `amount` is the foreign-currency amount.
                         Fees are DEDUCTED from the INR received.

    offer_rate / reference_rate are INR per 1 unit of foreign currency.

    Returns a dict with everything the template needs. All money is INR unless a
    key says otherwise. `extra_cost_inr` is positive when the offer is worse for
    the user than converting at the reference rate with no fees.
    """
    if direction not in ("buy", "sell"):
        raise ValueError("direction must be 'buy' or 'sell'")
    if offer_rate <= 0 or reference_rate <= 0 or amount <= 0:
        raise ValueError("amount and rates must be positive")

    r = {
        "direction": direction,
        "currency": currency,
        "amount": amount,
        "offer_rate": offer_rate,
        "reference_rate": reference_rate,
        "flat_fee": flat_fee,
        "percent_fee": percent_fee,
        "other_charges": other_charges,
    }

    if direction == "buy":
        percent_fee_inr = amount * percent_fee / 100.0
        total_fees = flat_fee + percent_fee_inr + other_charges
        total_paid_inr = amount + total_fees
        received_foreign = amount / offer_rate
        ideal_foreign = total_paid_inr / reference_rate     # same total outlay, no margin, no fees
        shortfall_foreign = ideal_foreign - received_foreign
        effective_rate = total_paid_inr / received_foreign   # INR actually paid per 1 unit
        # Compare what you paid with what the foreign money is worth at the reference rate.
        extra_cost_inr = total_paid_inr - received_foreign * reference_rate
        rate_margin_inr = amount - received_foreign * reference_rate   # part caused by the quoted rate
        markup_pct = (effective_rate - reference_rate) / reference_rate * 100.0
        r.update({
            "percent_fee_inr": percent_fee_inr,
            "total_paid_inr": total_paid_inr,
            "received_value": received_foreign,
            "received_unit": currency,
            "ideal_foreign": ideal_foreign,
            "shortfall_foreign": shortfall_foreign,
            "reference_value_inr": received_foreign * reference_rate,
        })
    else:
        gross_inr = amount * offer_rate
        percent_fee_inr = gross_inr * percent_fee / 100.0
        total_fees = flat_fee + percent_fee_inr + other_charges
        net_inr = gross_inr - total_fees
        ideal_inr = amount * reference_rate
        effective_rate = net_inr / amount                    # INR actually received per 1 unit
        extra_cost_inr = ideal_inr - net_inr
        rate_margin_inr = ideal_inr - gross_inr
        markup_pct = (reference_rate - effective_rate) / reference_rate * 100.0
        r.update({
            "percent_fee_inr": percent_fee_inr,
            "gross_inr": gross_inr,
            "received_value": net_inr,
            "received_unit": "INR",
            "ideal_inr": ideal_inr,
            "shortfall_inr": ideal_inr - net_inr,
            "reference_value_inr": ideal_inr,
        })

    r.update({
        "total_fees": total_fees,
        "effective_rate": effective_rate,
        "extra_cost_inr": extra_cost_inr,
        "rate_margin_inr": rate_margin_inr,
        "markup_pct": markup_pct,
        "offer_vs_reference_pct": (offer_rate - reference_rate) / reference_rate * 100.0,
    })
    r.update(_verdict(markup_pct, r["offer_vs_reference_pct"]))
    return r


def _verdict(markup_pct, offer_vs_reference_pct):
    """Plain-language reading of the total gap. The bands are a simple rule of
    thumb used by this app, not a regulatory or industry standard."""
    if abs(offer_vs_reference_pct) > 15:
        return {
            "verdict_level": "check",
            "verdict_title": "This quote is very far from the reference rate",
            "verdict_text": "Check the rate you typed. Make sure it is INR per 1 unit "
                            "(some providers quote Japanese yen per 100 yen).",
        }
    if markup_pct < -0.05:
        return {
            "verdict_level": "check",
            "verdict_title": "Better than the reference rate. Double-check this quote",
            "verdict_text": "Retail offers are rarely better than the reference rate. Confirm the "
                            "rate is per 1 unit, that all fees are included, and that "
                            "the rate is firm.",
        }
    if markup_pct < 1:
        return {
            "verdict_level": "good",
            "verdict_title": "Close to the reference rate",
            "verdict_text": "The total cost, including fees, is within 1% of the reference rate.",
        }
    if markup_pct <= 3:
        return {
            "verdict_level": "ok",
            "verdict_title": "A moderate gap to the reference rate",
            "verdict_text": "The total cost is 1% to 3% away from the reference rate. "
                            "Getting a second quote is worth the effort.",
        }
    return {
        "verdict_level": "bad",
        "verdict_title": "A large gap to the reference rate",
        "verdict_text": "The total cost is more than 3% away from the reference rate. "
                        "Compare other authorised providers before you commit.",
    }


def build_checklist(direction, currency):
    """Things to verify before accepting an offer. Each item is (title, detail)."""
    items = [
        ("Is the provider authorised?",
         "Banks (Authorised Dealer Category-I), Authorised Dealer Category-II entities and Full "
         "Fledged Money Changers are authorised by RBI. Ask to see the licence, or if the shop is "
         "a franchisee, which authorised provider it works for."),
        ("Is the rate per 1 unit?",
         "Confirm what the quoted rate applies to. Some providers quote per 100 units "
         "(common for yen)." if currency == "JPY" else
         "Confirm the quoted rate is per 1 unit of " + currency + " and ask whether it is the "
         "rate for cash, for a card, or for a bank transfer."),
        ("What is the total, in writing?",
         "Ask for the full amount you will pay or receive including service fee, commission, "
         "GST and any other taxes or charges (such as TCS, where it applies to you)."),
        ("How long is the rate valid?",
         "Rates change during the day. Ask whether the quote is locked for this transaction "
         "and until when."),
        ("Cash, card or transfer?",
         "Each product has its own rate and fees. For forex cards also ask about issue, reload, "
         "ATM and cross-currency charges, and about any unspent balance."),
        ("What documents are needed?",
         "Ask which ID, PAN and travel documents the provider needs, and whether any limits apply "
         "to your purpose of travel."),
        ("Compare at least two providers",
         "Get a second quote for the same amount and compare the total, not only the headline rate."),
        ("Keep the receipt",
         "The receipt should show the rate, the amount, the fees and the provider's name. "
         "Count the notes before you leave the counter."),
    ]
    if direction == "sell":
        items.insert(3, ("Which rate applies to selling?",
                         "Providers use a lower rate when they buy foreign currency from you than when "
                         "they sell it to you. Make sure you were quoted the buying rate."))
    items.append(("Confirm directly with the provider",
                  "This tool is a planning aid. Current fees, eligibility and availability must be "
                  "confirmed directly with the provider."))
    return items


# ---------------------------------------------------------------------------
# Feature 2: Travel Money Planner
# ---------------------------------------------------------------------------

def plan_trip(currency, rate, days, daily_spend_inr=None, total_budget_inr=None,
              buffer_pct=DEFAULT_BUFFER_PCT):
    """
    Build a planning estimate for a trip.

    Provide either `daily_spend_inr` (with `days`) or `total_budget_inr`.
    `rate` is INR per 1 unit of `currency`.

    A positive scenario percentage means the rupee weakens: each unit of foreign
    currency costs that much more INR, so a fixed INR budget buys less.
    """
    if rate <= 0:
        raise ValueError("rate must be positive")
    if days < 1:
        raise ValueError("days must be at least 1")

    if total_budget_inr is not None:
        base_inr = total_budget_inr
        daily_inr = base_inr / days
        mode = "total"
    else:
        daily_inr = daily_spend_inr
        base_inr = daily_inr * days
        mode = "daily"

    buffer_inr = base_inr * buffer_pct / 100.0
    suggested_inr = base_inr + buffer_inr

    base_foreign = base_inr / rate
    suggested_foreign = suggested_inr / rate
    daily_foreign = daily_inr / rate

    scenarios = []
    for pct in SCENARIO_STEPS:
        scenario_rate = rate * (1 + pct / 100.0)
        received = suggested_inr / scenario_rate
        inr_needed = suggested_foreign * scenario_rate
        if pct > 0:
            label = f"Rupee weakens {pct}%"
        elif pct < 0:
            label = f"Rupee strengthens {abs(pct)}%"
        else:
            label = "Today's rate"
        scenarios.append({
            "pct": pct,
            "label": label,
            "rate": scenario_rate,
            "received_foreign": received,
            "foreign_change": received - suggested_foreign,
            "inr_needed": inr_needed,
            "inr_change": inr_needed - suggested_inr,
        })

    worst = max(scenarios, key=lambda s: s["pct"])      # rupee weakens 5%
    return {
        "currency": currency,
        "rate": rate,
        "days": days,
        "mode": mode,
        "buffer_pct": buffer_pct,
        "daily_inr": daily_inr,
        "daily_foreign": daily_foreign,
        "base_inr": base_inr,
        "base_foreign": base_foreign,
        "buffer_inr": buffer_inr,
        "suggested_inr": suggested_inr,
        "suggested_foreign": suggested_foreign,
        "cushion_inr": worst["inr_needed"],      # INR to still get today's suggested foreign amount if rupee weakens 5%
        "cushion_extra_inr": worst["inr_change"],
        "scenarios": scenarios,
    }


# ---------------------------------------------------------------------------
# Formatting helpers (used as Jinja filters)
# ---------------------------------------------------------------------------

def format_inr(value, decimals=2):
    """Indian digit grouping: 1234567.5 -> '12,34,567.50'."""
    if value is None:
        return "N/A"
    negative = value < 0
    text = f"{abs(value):.{decimals}f}"
    whole, _, frac = text.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    out = whole + ("." + frac if frac else "")
    return ("-" if negative else "") + out


def format_foreign(value, currency):
    """Western grouping; yen has no minor unit so it is shown without decimals."""
    if value is None:
        return "N/A"
    decimals = 0 if currency == "JPY" else 2
    return f"{value:,.{decimals}f}"


def format_signed_pct(value, decimals=2):
    if value is None:
        return "N/A"
    return f"{value:+.{decimals}f}%"
