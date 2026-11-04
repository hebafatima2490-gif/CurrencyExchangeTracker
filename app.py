import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, request, render_template, jsonify, session, redirect, url_for, flash
from api import get_exchange_rate, get_historical_rates, fetch_and_cache_year_history
from database import (
    create_database,
    save_rate,
    get_history,
    save_historical_rate,
    get_previous_rate,
    get_latest_rate,
    get_latest_rate_with_date,
    get_average_rate,
    get_volatility,
    get_date_bounds,
    get_monthly_history,
    has_monthly_data_for_year,
    compute_and_save_monthly_from_daily
)
from datetime import datetime, timedelta, date
import forex_tools

app = Flask(__name__)
app.secret_key = "currency_tracker_local_dev_key_2026"

# Ensure tables and indexes are initialized
create_database()

ALLOWED_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AED"]
ALLOWED_YEARS = list(range(2000, 2027))
MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]
MONTH_ABBRS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
]


def load_historical_data(start_date="2026-09-01", end_date=None):
    currencies = ["USD", "EUR", "GBP", "JPY", "AED"]
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    for currency in currencies:
        try:
            historical_data = get_historical_rates(
                currency,
                "INR",
                start_date,
                end_date
            )

            for record in historical_data:
                if record and record.get("rate") is not None and record.get("date"):
                    save_historical_rate(
                        record["date"],
                        record.get("base", currency),
                        record.get("quote", "INR"),
                        record["rate"]
                    )
        except Exception as e:
            print(f"Error loading historical data for {currency}: {e}")


def get_percentage_difference(current_rate, average_rate):
    if current_rate is None or average_rate is None or average_rate == 0:
        return None

    return ((current_rate - average_rate) / average_rate) * 100


def get_buy_signal(current_rate, average_rate):
    if current_rate is None or average_rate is None:
        return "⚪ Not Available"

    if current_rate >= average_rate * 1.02:
        return "🟢 Buy Now"
    elif current_rate <= average_rate * 0.98:
        return "🔴 Wait"
    else:
        return "🟡 Hold"


def get_volatility_label(volatility):
    if volatility is None:
        return "⚪ Not Available"

    if volatility < 1:
        return "🟢 Low Volatility"
    elif volatility <= 2:
        return "🟡 Medium Volatility"
    else:
        return "🔴 High Volatility"


def get_monthly_data_for_year(currency, target_currency, year):
    """
    Retrieves and processes monthly exchange rate averages for a given year.
    Returns structured data with rates, trends, color coding, and summary statistics.
    Trend color rules:
      - Green (#16A34A): monthly average increased vs previous available month
      - Red (#DC2626): monthly average decreased vs previous available month
      - Neutral (#64748B): monthly average unchanged or first available month
      - Missing: None (handled as gaps, spanGaps: false)
    """
    # 1. Check if monthly data exists in SQLite
    records = get_monthly_history(currency, target_currency, year)

    # 2. If not in monthly table, attempt to fetch from API or aggregate from daily table
    if not records:
        # First attempt on-demand fetch & cache from API
        fetched = fetch_and_cache_year_history(currency, target_currency, year)
        if fetched:
            records = get_monthly_history(currency, target_currency, year)
        else:
            # Fall back to calculating from daily table if daily records exist
            compute_and_save_monthly_from_daily(currency, target_currency, year)
            records = get_monthly_history(currency, target_currency, year)

    # Initialize 12 months array (Jan to Dec)
    rates = [None] * 12
    counts = [0] * 12
    trends = ["missing"] * 12
    colors = ["#64748B"] * 12
    month_sources = [""] * 12

    for row in records:
        month_num = int(row[0])
        if 1 <= month_num <= 12:
            idx = month_num - 1
            rates[idx] = round(float(row[1]), 4)
            counts[idx] = int(row[2])
            month_sources[idx] = row[3] if len(row) > 3 else "Frankfurter API"

    # Determine trend by comparing each available month to the previous available month
    prev_available = None
    available_indices = []

    for i in range(12):
        val = rates[i]
        if val is None:
            trends[i] = "missing"
            colors[i] = "transparent"
            continue

        available_indices.append(i)
        if prev_available is None:
            trends[i] = "neutral"
            colors[i] = "#64748B"
        elif val > prev_available:
            trends[i] = "up"
            colors[i] = "#16A34A"  # Green
        elif val < prev_available:
            trends[i] = "down"
            colors[i] = "#DC2626"  # Red
        else:
            trends[i] = "flat"
            colors[i] = "#64748B"  # Neutral

        prev_available = val

    # Calculate Yearly Summary Statistics
    has_data = len(available_indices) > 0
    summary = None

    if has_data:
        available_rates = [rates[i] for i in available_indices]
        first_idx = available_indices[0]
        last_idx = available_indices[-1]

        highest_rate = max(available_rates)
        lowest_rate = min(available_rates)

        highest_month = MONTH_NAMES[rates.index(highest_rate)]
        lowest_month = MONTH_NAMES[rates.index(lowest_rate)]

        average_of_averages = round(sum(available_rates) / len(available_rates), 4)

        summary = {
            "currency_pair": f"{currency} → {target_currency}",
            "base_currency": currency,
            "target_currency": target_currency,
            "year": int(year),
            "first_average": rates[first_idx],
            "first_month": MONTH_NAMES[first_idx],
            "last_average": rates[last_idx],
            "last_month": MONTH_NAMES[last_idx],
            "highest_average": highest_rate,
            "highest_month": highest_month,
            "lowest_average": lowest_rate,
            "lowest_month": lowest_month,
            "average_of_averages": average_of_averages,
            "available_months": len(available_indices),
            "total_months": 12,
            "is_complete_year": len(available_indices) == 12
        }

    return {
        "labels": MONTH_ABBRS,
        "month_names": MONTH_NAMES,
        "rates": rates,
        "counts": counts,
        "trends": trends,
        "colors": colors,
        "summary": summary,
        "has_data": has_data,
        "currency": currency,
        "year": int(year)
    }


def compute_daily_trends(daily_records):
    """
    Computes trend direction and segment colors for daily records.
    Green (#16A34A) if rate > previous day.
    Red (#DC2626) if rate < previous day.
    Neutral (#64748B) if equal or first record.
    """
    if not daily_records:
        return [], [], []

    dates = [r[0] for r in daily_records]
    rates = [r[1] for r in daily_records]
    point_colors = []

    for i in range(len(rates)):
        if i == 0:
            point_colors.append("#64748B")
        elif rates[i] > rates[i - 1]:
            point_colors.append("#16A34A")
        elif rates[i] < rates[i - 1]:
            point_colors.append("#DC2626")
        else:
            point_colors.append("#64748B")

    return dates, rates, point_colors


# Authentication routes
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if not username or not password:
            flash('Username and password are required.', 'error')
            return render_template('register.html')
        # Check duplicate username
        conn = sqlite3.connect('currency_tracker.db')
        cur = conn.cursor()
        cur.execute('SELECT id FROM users WHERE username = ?', (username,))
        if cur.fetchone():
            flash('Username already taken.', 'error')
            conn.close()
            return render_template('register.html')
        password_hash = generate_password_hash(password)
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cur.execute('INSERT INTO users (username, password_hash, created_at) VALUES (?,?,?)',
                    (username, password_hash, created_at))
        conn.commit()
        conn.close()
        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        conn = sqlite3.connect('currency_tracker.db')
        cur = conn.cursor()
        cur.execute('SELECT id, password_hash FROM users WHERE username = ?', (username,))
        row = cur.fetchone()
        conn.close()
        if row and check_password_hash(row[1], password):
            session['user_id'] = row[0]
            session['username'] = username
            flash('Logged in successfully.', 'success')
            return redirect(url_for('home'))
        flash('Invalid credentials.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'success')
    return redirect(url_for('home'))


@app.route("/")
def home():
    usd_inr = get_exchange_rate("USD", "INR")
    usd_average = get_average_rate("USD", "INR")
    usd_signal = get_buy_signal(usd_inr, usd_average)
    usd_volatility = get_volatility("USD", "INR")
    usd_volatility_label = get_volatility_label(usd_volatility)

    eur_inr = get_exchange_rate("EUR", "INR")
    eur_average = get_average_rate("EUR", "INR")
    eur_signal = get_buy_signal(eur_inr, eur_average)
    eur_volatility = get_volatility("EUR", "INR")
    eur_volatility_label = get_volatility_label(eur_volatility)

    gbp_inr = get_exchange_rate("GBP", "INR")
    gbp_average = get_average_rate("GBP", "INR")
    gbp_signal = get_buy_signal(gbp_inr, gbp_average)
    gbp_volatility = get_volatility("GBP", "INR")
    gbp_volatility_label = get_volatility_label(gbp_volatility)

    jpy_inr = get_exchange_rate("JPY", "INR")
    jpy_average = get_average_rate("JPY", "INR")
    jpy_signal = get_buy_signal(jpy_inr, jpy_average)
    jpy_volatility = get_volatility("JPY", "INR")
    jpy_volatility_label = get_volatility_label(jpy_volatility)

    aed_inr = get_exchange_rate("AED", "INR")
    aed_average = get_average_rate("AED", "INR")
    aed_signal = get_buy_signal(aed_inr, aed_average)
    aed_volatility = get_volatility("AED", "INR")
    aed_volatility_label = get_volatility_label(aed_volatility)

    # Only save valid non-None rates to protect database integrity
    for currency, rate in [
        ("USD", usd_inr),
        ("EUR", eur_inr),
        ("GBP", gbp_inr),
        ("JPY", jpy_inr),
        ("AED", aed_inr)
    ]:
        if rate is not None:
            save_rate(currency, "INR", rate)

    return render_template(
        "index.html",
        usd_average=usd_average,
        usd_signal=usd_signal,
        usd_inr=usd_inr,
        usd_volatility=usd_volatility,
        usd_volatility_label=usd_volatility_label,

        eur_average=eur_average,
        eur_signal=eur_signal,
        eur_inr=eur_inr,
        eur_volatility=eur_volatility,
        eur_volatility_label=eur_volatility_label,

        gbp_average=gbp_average,
        gbp_signal=gbp_signal,
        gbp_inr=gbp_inr,
        gbp_volatility=gbp_volatility,
        gbp_volatility_label=gbp_volatility_label,

        jpy_average=jpy_average,
        jpy_signal=jpy_signal,
        jpy_inr=jpy_inr,
        jpy_volatility=jpy_volatility,
        jpy_volatility_label=jpy_volatility_label,

        aed_average=aed_average,
        aed_signal=aed_signal,
        aed_inr=aed_inr,
        aed_volatility=aed_volatility,
        aed_volatility_label=aed_volatility_label,

        last_updated=datetime.now().strftime("%d %B %Y, %I:%M %p")
    )


@app.route("/history")
def history():
    currency = request.args.get("currency", "USD").upper()
    if currency not in ALLOWED_CURRENCIES:
        currency = "USD"

    # Year parameter for Graph 2 (Historical Monthly Graph: 2000 to 2026)
    year_arg = request.args.get("year", "2026")
    try:
        selected_year = int(year_arg)
        if selected_year < 2000:
            selected_year = 2000
        elif selected_year > 2026:
            selected_year = 2026
    except ValueError:
        selected_year = 2026

    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()
    date_error = None

    valid_start = None
    valid_end = None

    if start_date:
        try:
            valid_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            date_error = "Invalid start date format. Please use YYYY-MM-DD."

    if end_date and not date_error:
        try:
            valid_end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            date_error = "Invalid end date format. Please use YYYY-MM-DD."

    if valid_start and valid_end and valid_start > valid_end:
        date_error = "Start date cannot be after end date."

    # Graph 1: Daily History Data
    if date_error:
        history_data = []
    else:
        history_data = get_history(
            currency,
            "INR",
            start_date=start_date if start_date else None,
            end_date=end_date if end_date else None
        )

    min_date, max_date = get_date_bounds(currency, "INR")

    # Compute daily trend colors for Graph 1
    daily_dates, daily_rates, daily_colors = compute_daily_trends(history_data)

    # Graph 2: Monthly Historical Averages (2000-2026)
    monthly_data = get_monthly_data_for_year(currency, "INR", selected_year)

    return render_template(
        "history.html",
        history=history_data,
        daily_dates=daily_dates,
        daily_rates=daily_rates,
        daily_colors=daily_colors,
        selected_currency=currency,
        currencies=ALLOWED_CURRENCIES,
        start_date=start_date,
        end_date=end_date,
        date_error=date_error,
        min_date=min_date,
        max_date=max_date,
        selected_year=selected_year,
        years=ALLOWED_YEARS,
        monthly_data=monthly_data
    )


# ==========================================
# REST API Endpoints for Dynamic AJAX Graphs
# ==========================================

@app.route("/api/historical-monthly")
def api_historical_monthly():
    """Returns monthly average rates and statistics for the historical graph without full page reload."""
    currency = request.args.get("currency", "USD").upper()
    if currency not in ALLOWED_CURRENCIES:
        currency = "USD"

    try:
        year = int(request.args.get("year", 2026))
        if year < 2000 or year > 2026:
            return jsonify({"success": False, "error": "Year must be between 2000 and 2026."}), 400
    except ValueError:
        return jsonify({"success": False, "error": "Invalid year format."}), 400

    data = get_monthly_data_for_year(currency, "INR", year)
    return jsonify({
        "success": True,
        "currency": currency,
        "target": "INR",
        "year": year,
        "title": f"{currency} to INR — Monthly Average Exchange Rates — {year}",
        "labels": data["labels"],
        "month_names": data["month_names"],
        "rates": data["rates"],
        "counts": data["counts"],
        "trends": data["trends"],
        "colors": data["colors"],
        "summary": data["summary"],
        "has_data": data["has_data"]
    })


@app.route("/api/dynamic-daily")
def api_dynamic_daily():
    """Returns daily historical rates for dynamic date range selection."""
    currency = request.args.get("currency", "USD").upper()
    if currency not in ALLOWED_CURRENCIES:
        currency = "USD"

    preset = request.args.get("range", "").lower()
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    today = datetime.now().date()

    if preset == "7d":
        start_date = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
    elif preset == "30d":
        start_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
    elif preset == "60d":
        start_date = (today - timedelta(days=60)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
    elif preset == "all":
        start_date = None
        end_date = None

    history_data = get_history(
        currency,
        "INR",
        start_date=start_date if start_date else None,
        end_date=end_date if end_date else None
    )

    dates, rates, colors = compute_daily_trends(history_data)

    return jsonify({
        "success": True,
        "currency": currency,
        "target": "INR",
        "dates": dates,
        "rates": rates,
        "colors": colors,
        "count": len(rates),
        "start_date": start_date or (dates[0] if dates else ""),
        "end_date": end_date or (dates[-1] if dates else "")
    })



# ==========================================
# Feature 1: Forex Decision Assistant
# Feature 2: Travel Money Planner
# ==========================================

app.jinja_env.filters["inr"] = forex_tools.format_inr
app.jinja_env.filters["foreign"] = forex_tools.format_foreign
app.jinja_env.filters["signed_pct"] = forex_tools.format_signed_pct


def get_reference_rate(currency):
    """
    Reference (mid-market) rate in INR per 1 unit of `currency`.

    Tries the live API first. If that fails, falls back to the newest rate saved in
    SQLite and reports how old it is. Returns a dict, or None if nothing is available.
    """
    live = get_exchange_rate(currency, "INR")
    if live is not None:
        return {
            "rate": float(live),
            "is_live": True,
            "as_of": datetime.now().strftime("%d %B %Y, %I:%M %p"),
            "source": "Frankfurter API, mid-market rate",
        }

    cached = get_latest_rate_with_date(currency, "INR")
    if cached:
        return {
            "rate": float(cached[0]),
            "is_live": False,
            "as_of": cached[1],
            "source": "Last rate saved in this app",
        }
    return None


@app.context_processor
def inject_site_context():
    return {
        "official_resources": forex_tools.OFFICIAL_RESOURCES,
        "links_checked_on": forex_tools.LINKS_CHECKED_ON,
        "supported_currencies": forex_tools.SUPPORTED_CURRENCIES,
    }


@app.route("/decision-assistant", methods=["GET", "POST"])
def decision_assistant():
    form = request.form if request.method == "POST" else request.args
    values = {
        "direction": form.get("direction", "buy"),
        "currency": form.get("currency", "USD").upper(),
        "amount": form.get("amount", ""),
        "offer_rate": form.get("offer_rate", ""),
        "quote_unit": form.get("quote_unit", "1"),
        "flat_fee": form.get("flat_fee", ""),
        "percent_fee": form.get("percent_fee", ""),
        "other_charges": form.get("other_charges", ""),
    }
    if values["direction"] not in ("buy", "sell"):
        values["direction"] = "buy"
    if values["currency"] not in forex_tools.SUPPORTED_CURRENCIES:
        values["currency"] = "USD"
    if values["quote_unit"] not in ("1", "100"):
        values["quote_unit"] = "1"

    result = None
    reference = None
    errors = []
    checklist = forex_tools.build_checklist(values["direction"], values["currency"])

    if request.method == "POST":
        amount = forex_tools.parse_number(
            values["amount"], "Amount", errors, allow_zero=False, maximum=1e9)
        offer_per_quote = forex_tools.parse_number(
            values["offer_rate"], "Offered rate", errors, allow_zero=False, maximum=1e7)
        flat_fee = forex_tools.parse_number(
            values["flat_fee"], "Flat fee", errors, required=False, default=0.0, maximum=1e9)
        percent_fee = forex_tools.parse_number(
            values["percent_fee"], "Commission %", errors, required=False, default=0.0, maximum=50)
        other_charges = forex_tools.parse_number(
            values["other_charges"], "Taxes and other charges", errors,
            required=False, default=0.0, maximum=1e9)

        if not errors:
            reference = get_reference_rate(values["currency"])
            if reference is None:
                errors.append(
                    "We could not get a reference rate right now. Check your internet "
                    "connection and try again.")

        if not errors:
            offer_rate = offer_per_quote / float(values["quote_unit"])
            result = forex_tools.compare_offer(
                values["direction"], values["currency"], amount, offer_rate,
                reference["rate"], flat_fee, percent_fee, other_charges)
            checklist = forex_tools.build_checklist(values["direction"], values["currency"])

    return render_template(
        "decision_assistant.html",
        active="decision",
        values=values,
        result=result,
        reference=reference,
        errors=errors,
        checklist=checklist,
        currencies=forex_tools.SUPPORTED_CURRENCIES,
    )


@app.route("/travel-planner", methods=["GET", "POST"])
def travel_planner():
    form = request.form if request.method == "POST" else request.args
    values = {
        "destination": form.get("destination", "AE"),
        "plan_by": form.get("plan_by", "daily"),
        "days": form.get("days", ""),
        "daily_spend": form.get("daily_spend", ""),
        "total_budget": form.get("total_budget", ""),
        "buffer_pct": form.get("buffer_pct", str(int(forex_tools.DEFAULT_BUFFER_PCT))),
        "travel_date": form.get("travel_date", ""),
    }
    dest_codes = {code: (label, cur) for code, label, cur in forex_tools.DESTINATIONS}
    if values["destination"] not in dest_codes:
        values["destination"] = "AE"
    if values["plan_by"] not in ("daily", "total"):
        values["plan_by"] = "daily"

    plan = None
    context = None
    errors = []

    if request.method == "POST":
        days = forex_tools.parse_number(
            values["days"], "Trip length (days)", errors, minimum=1, maximum=365)
        if days is not None and days != int(days):
            errors.append("Trip length must be a whole number of days.")
        buffer_pct = forex_tools.parse_number(
            values["buffer_pct"], "Safety buffer %", errors,
            required=False, default=forex_tools.DEFAULT_BUFFER_PCT, maximum=100)

        daily = total = None
        if values["plan_by"] == "daily":
            daily = forex_tools.parse_number(
                values["daily_spend"], "Daily spending", errors, allow_zero=False, maximum=1e8)
        else:
            total = forex_tools.parse_number(
                values["total_budget"], "Total budget", errors, allow_zero=False, maximum=1e9)

        travel_date = None
        if values["travel_date"]:
            try:
                travel_date = datetime.strptime(values["travel_date"], "%Y-%m-%d").date()
                if travel_date < date.today():
                    errors.append("Travel date cannot be in the past.")
            except ValueError:
                errors.append("Travel date must be a valid date.")

        currency = dest_codes[values["destination"]][1]
        reference = None
        if not errors:
            reference = get_reference_rate(currency)
            if reference is None:
                errors.append(
                    "We could not get an exchange rate right now. Check your internet "
                    "connection and try again.")

        if not errors:
            plan = forex_tools.plan_trip(
                currency, reference["rate"], int(days),
                daily_spend_inr=daily, total_budget_inr=total, buffer_pct=buffer_pct)
            average = get_average_rate(currency, "INR")
            volatility = get_volatility(currency, "INR")
            context = {
                "reference": reference,
                "average": average,
                "volatility_label": get_volatility_label(volatility),
                "days_until_travel": (travel_date - date.today()).days if travel_date else None,
                "travel_date": travel_date,
                "destination_label": dest_codes[values["destination"]][0],
            }

    return render_template(
        "travel_planner.html",
        active="travel",
        values=values,
        destinations=forex_tools.DESTINATIONS,
        plan=plan,
        context=context,
        errors=errors,
        today=date.today().isoformat(),
    )


@app.route("/convert", methods=["POST"])
def convert():
    from_currency = request.form["from_currency"].upper()
    to_currency = request.form["to_currency"].upper()
    amount = float(request.form["amount"])

    rate = get_exchange_rate(from_currency, to_currency)

    # Resilient offline/cache fallback if live API rate cannot be retrieved
    if rate is None:
        if to_currency == "INR":
            rate = get_previous_rate(from_currency, "INR") or get_latest_rate(from_currency, "INR")
        elif from_currency == "INR":
            inv = get_previous_rate(to_currency, "INR") or get_latest_rate(to_currency, "INR")
            if inv:
                rate = 1.0 / inv
        elif from_currency == to_currency:
            rate = 1.0

    if rate is None:
        return """
        <h1>Conversion Error</h1>

     <p>
        We could not retrieve the exchange rate right now.
        Please check your internet connection and try again.
        </p>

        <br>

        <a href="/">← Back to Dashboard</a>
        """

    converted_amount = amount * rate
    rupee_status = ""
    percentage_change = None
    comparison_rate = None
    previous_rate = None

    if to_currency == "INR":
        previous_rate = get_previous_rate(from_currency, "INR")
        comparison_rate = rate

        if previous_rate is not None:
            percentage_change = (
                abs((comparison_rate - previous_rate) / previous_rate) * 100
            )

            if comparison_rate > previous_rate:
                rupee_status = f"⬆️ Rupee weakened against {from_currency}"
            elif comparison_rate < previous_rate:
                rupee_status = f"⬇️ Rupee strengthened against {from_currency}"
            else:
                rupee_status = "➡️ Rupee remained stable"

    elif from_currency == "INR":
        previous_foreign_rate = get_previous_rate(to_currency, "INR")

        if previous_foreign_rate is not None:
            comparison_rate = 1 / rate
            previous_rate = previous_foreign_rate

            percentage_change = (
                abs((comparison_rate - previous_rate) / previous_rate) * 100
            )

            if comparison_rate > previous_rate:
                rupee_status = f"⬇️ Rupee weakened against {to_currency}"
            elif comparison_rate < previous_rate:
                rupee_status = f"⬆️ Rupee strengthened against {to_currency}"
            else:
                rupee_status = "➡️ Rupee remained stable"

    return render_template(
        "conversion_result.html",
        amount=amount,
        from_currency=from_currency,
        to_currency=to_currency,
        converted_amount=converted_amount,
        rate=rate,
        rupee_status=rupee_status,
        percentage_change=percentage_change,
        previous_rate=previous_rate,
        comparison_rate=comparison_rate
    )


@app.route("/converter")
def converter():
    return render_template("converter.html")


@app.route("/about")
def about():
    return render_template("about.html")


if __name__ == "__main__":
    create_database()
    load_historical_data()
    app.run(debug=True)
