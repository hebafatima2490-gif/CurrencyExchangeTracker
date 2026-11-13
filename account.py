import os
import math
import secrets
import sqlite3
from functools import wraps
from urllib.parse import urlparse
from flask import (
    Blueprint,
    request,
    session,
    redirect,
    url_for,
    abort,
    render_template,
    flash
)
from werkzeug.security import generate_password_hash, check_password_hash
import database

ALLOWED_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AED"]

account_bp = Blueprint("account", __name__)


@account_bp.before_request
def csrf_protect_account_routes():
    """Verify CSRF token automatically for every POST request on account Blueprint."""
    if request.method == "POST":
        verify_csrf_token()


def generate_csrf_token():
    """Generate or retrieve a per-session CSRF token."""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


def verify_csrf_token():
    """Verify that the CSRF token in the request matches the session token."""
    token = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
    expected = session.get("_csrf_token")
    if not expected or not token or not secrets.compare_digest(token, expected):
        abort(400, description="Invalid or missing CSRF token.")


def is_safe_redirect_url(target):
    """
    Ensure the target URL is safe for local redirection:
    - Must be provided
    - Must not begin with '//' or '\\'
    - Must not have an external host/scheme
    - Must be a relative path beginning with '/'
    """
    if not target:
        return False
    # Reject Windows backslashes and scheme-relative URLs
    if target.startswith("//") or target.startswith("\\") or "\\" in target:
        return False
    
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return False
    
    return target.startswith("/")


def login_required(f):
    """
    Decorator to require login for account-protected routes.
    Also confirms user_id still exists in the users table using database.DATABASE_NAME at call time.
    If not, clears the session and redirects to /login.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            dest = request.full_path if request.query_string else request.path
            if dest.endswith("?"):
                dest = dest[:-1]
            return redirect(url_for("login", next=dest))
        
        # Verify user still exists in database
        conn = sqlite3.connect(database.DATABASE_NAME)
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        user_row = cur.fetchone()
        conn.close()
        
        if not user_row:
            session.clear()
            dest = request.full_path if request.query_string else request.path
            if dest.endswith("?"):
                dest = dest[:-1]
            return redirect(url_for("login", next=dest))

        return f(*args, **kwargs)
    return decorated_function


def validate_password_strength(password):
    """
    Validate that password meets length requirements:
    - Minimum 8 characters
    - Maximum 128 characters
    Returns (is_valid, error_message)
    """
    if not password:
        return False, "Password is required."
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if len(password) > 128:
        return False, "Password must not exceed 128 characters."
    return True, None


@account_bp.route("/dashboard")
@login_required
def dashboard():
    user_id = session.get("user_id")
    user_record = database.get_user_by_id(user_id)
    username = user_record[1] if user_record else session.get("username", "User")
    created_at = user_record[2] if user_record else "Unknown"

    prefs = database.get_user_preferences(user_id)
    watchlist_count = len(prefs.get("watchlist", []))

    conversions_count = database.count_saved_items(user_id, kind="conversion")
    travel_plans_count = database.count_saved_items(user_id, kind="trip")
    decisions_count = database.count_saved_items(user_id, kind="audit")

    triggered_alerts = database.check_user_alerts(user_id)

    return render_template(
        "dashboard.html",
        username=username,
        created_at=created_at,
        watchlist_count=watchlist_count,
        conversions_count=conversions_count,
        travel_plans_count=travel_plans_count,
        decisions_count=decisions_count,
        triggered_alerts=triggered_alerts,
        active="dashboard"
    )


@account_bp.route("/my-currencies")
@login_required
def my_currencies():
    user_id = session.get("user_id")
    # Check user alerts against newest stored rates
    database.check_user_alerts(user_id)

    prefs = database.get_user_preferences(user_id)
    default_curr = prefs.get("default_currency", "USD")
    raw_watchlist = prefs.get("watchlist", [])

    watchlist_data = []
    for c in raw_watchlist:
        rate_info = database.get_latest_rate_with_date(c, "INR")
        if rate_info:
            watchlist_data.append({
                "currency": c,
                "rate": rate_info[0],
                "date": rate_info[1]
            })
        else:
            watchlist_data.append({
                "currency": c,
                "rate": None,
                "date": None
            })

    alerts = database.get_rate_alerts(user_id)

    return render_template(
        "my_currencies.html",
        default_currency=default_curr,
        allowed_currencies=ALLOWED_CURRENCIES,
        watchlist=watchlist_data,
        alerts=alerts,
        active="my-currencies"
    )


@account_bp.route("/my-currencies/default", methods=["POST"])
@login_required
def set_default_currency():
    user_id = session.get("user_id")
    chosen = request.form.get("default_currency", "").strip().upper()
    if chosen not in ALLOWED_CURRENCIES:
        flash("Invalid currency selection.", "error")
        return redirect(url_for("account.my_currencies"))

    database.save_user_preferences(user_id, default_currency=chosen)
    flash(f"Default currency updated to {chosen}.", "success")
    return redirect(url_for("account.my_currencies"))


@account_bp.route("/my-currencies/watchlist/add", methods=["POST"])
@login_required
def add_to_watchlist():
    user_id = session.get("user_id")
    chosen = request.form.get("currency", "").strip().upper()
    if chosen not in ALLOWED_CURRENCIES:
        flash("Invalid currency code.", "error")
        return redirect(url_for("account.my_currencies"))

    prefs = database.get_user_preferences(user_id)
    current_watchlist = prefs.get("watchlist", [])
    if chosen in current_watchlist:
        flash(f"{chosen} is already in your watchlist.", "info")
        return redirect(url_for("account.my_currencies"))

    current_watchlist.append(chosen)
    database.save_user_preferences(user_id, watchlist=current_watchlist)
    flash(f"Added {chosen} to your watchlist.", "success")
    return redirect(url_for("account.my_currencies"))


@account_bp.route("/my-currencies/watchlist/remove", methods=["POST"])
@login_required
def remove_from_watchlist():
    user_id = session.get("user_id")
    chosen = request.form.get("currency", "").strip().upper()
    prefs = database.get_user_preferences(user_id)
    current_watchlist = prefs.get("watchlist", [])
    if chosen in current_watchlist:
        current_watchlist.remove(chosen)
        database.save_user_preferences(user_id, watchlist=current_watchlist)
        flash(f"Removed {chosen} from your watchlist.", "success")
    else:
        flash(f"{chosen} is not in your watchlist.", "error")
    return redirect(url_for("account.my_currencies"))


@account_bp.route("/my-currencies/alerts/create", methods=["POST"])
@login_required
def create_rate_alert():
    user_id = session.get("user_id")
    currency = request.form.get("currency", "").strip().upper()
    direction = request.form.get("direction", "").strip().lower()
    raw_rate = request.form.get("target_rate", "").strip()

    if currency not in ALLOWED_CURRENCIES:
        flash("Unsupported currency selected.", "error")
        return redirect(url_for("account.my_currencies"))

    if direction not in ("above", "below"):
        flash("Invalid alert direction. Must be 'above' or 'below'.", "error")
        return redirect(url_for("account.my_currencies"))

    try:
        target_rate = float(raw_rate)
        if math.isnan(target_rate) or math.isinf(target_rate) or target_rate <= 0:
            flash("Target rate must be a valid positive number.", "error")
            return redirect(url_for("account.my_currencies"))
    except (ValueError, TypeError):
        flash("Target rate must be a valid numeric value.", "error")
        return redirect(url_for("account.my_currencies"))

    if database.count_rate_alerts(user_id) >= 20:
        flash("Maximum limit of 20 rate alerts reached.", "error")
        return redirect(url_for("account.my_currencies"))

    success, err = database.add_rate_alert(user_id, currency, direction, target_rate)
    if success:
        database.check_user_alerts(user_id)
        flash(f"Rate alert for {currency} ({direction} {target_rate:.4f} INR) created.", "success")
    else:
        flash(err or "Failed to create rate alert.", "error")

    return redirect(url_for("account.my_currencies"))


@account_bp.route("/my-currencies/alerts/<int:alert_id>/delete", methods=["POST"])
@login_required
def delete_alert(alert_id):
    user_id = session.get("user_id")
    deleted = database.delete_rate_alert(user_id, alert_id)
    if deleted:
        flash("Rate alert deleted.", "success")
    else:
        flash("Alert not found or unauthorized.", "error")
    return redirect(url_for("account.my_currencies"))


@account_bp.route("/my-currencies/alerts/<int:alert_id>/dismiss", methods=["POST"])
@login_required
def dismiss_alert(alert_id):
    user_id = session.get("user_id")
    dismissed = database.dismiss_rate_alert(user_id, alert_id)
    if dismissed:
        flash("Rate alert dismissed.", "success")
    else:
        flash("Alert not found or unauthorized.", "error")
    return redirect(url_for("account.my_currencies"))


@account_bp.route("/my-currencies/alerts/<int:alert_id>/rearm", methods=["POST"])
@login_required
def rearm_alert(alert_id):
    user_id = session.get("user_id")
    rearmed = database.rearm_rate_alert(user_id, alert_id)
    if rearmed:
        database.check_user_alerts(user_id)
        flash("Rate alert re-armed.", "success")
    else:
        flash("Alert not found or unauthorized.", "error")
    return redirect(url_for("account.my_currencies"))


# ---------------------------------------------------------------------------
# Stage 6 — Saved Conversions, Travel Plans & Decisions
# ---------------------------------------------------------------------------

SAVED_ITEM_KINDS = ("conversion", "trip", "audit")
SAVED_ITEM_MAX = 100


def _build_reopen_url(kind, params):
    """
    Build a safe GET URL to prefill the original tool with saved params.
    Travel dates in the past are omitted.
    """
    from datetime import date as _date
    if kind == "conversion":
        from urllib.parse import urlencode
        qs = {}
        fc = params.get("from_currency", "")
        tc = params.get("to_currency", "")
        amt = params.get("amount", "")
        if fc:
            qs["from_currency"] = fc
        if tc:
            qs["to_currency"] = tc
        if amt != "" and amt is not None:
            qs["amount"] = str(amt)
        if qs:
            return url_for("converter") + "?" + urlencode(qs)
        return url_for("converter")
    if kind == "trip":
        qs = {
            "destination": params.get("destination", ""),
            "plan_by": params.get("plan_by", "daily"),
            "days": str(params.get("days", "")),
            "buffer_pct": str(params.get("buffer_pct", "")),
        }
        if params.get("plan_by") == "daily":
            qs["daily_spend"] = str(params.get("daily_spend", ""))
        else:
            qs["total_budget"] = str(params.get("total_budget", ""))
        travel_date_str = params.get("travel_date", "")
        if travel_date_str:
            try:
                td = _date.fromisoformat(travel_date_str)
                if td >= _date.today():
                    qs["travel_date"] = travel_date_str
            except (ValueError, TypeError):
                pass
        from urllib.parse import urlencode
        return url_for("travel_planner") + "?" + urlencode({k: v for k, v in qs.items() if v != ""})
    if kind == "audit":
        p = params
        qs = {
            "direction": p.get("direction", "buy"),
            "currency": p.get("currency", "USD"),
            "amount": str(p.get("amount", "")),
            "offer_rate": str(p.get("offer_rate", "")),
            "quote_unit": str(p.get("quote_unit", "1")),
            "flat_fee": str(p.get("flat_fee", "")),
            "percent_fee": str(p.get("percent_fee", "")),
            "other_charges": str(p.get("other_charges", "")),
        }
        from urllib.parse import urlencode
        return url_for("decision_assistant") + "?" + urlencode({k: v for k, v in qs.items() if v != ""})
    return "/"


# ----- Saved Conversions -----

@account_bp.route("/my-conversions")
@login_required
def my_conversions():
    user_id = session.get("user_id")
    database.check_user_alerts(user_id)
    import json
    raw_items = database.get_saved_items(user_id, kind="conversion")
    items = []
    for it in raw_items:
        try:
            params = json.loads(it["params"])
        except (ValueError, KeyError):
            params = {}
        items.append({**it, "parsed_params": params, "reopen_url": _build_reopen_url("conversion", params)})
    total_saved = database.count_saved_items(user_id)
    return render_template(
        "my_conversions.html",
        items=items,
        total_saved=total_saved,
        saved_max=SAVED_ITEM_MAX,
        active="my-conversions",
    )


@account_bp.route("/my-conversions/save", methods=["POST"])
@login_required
def save_conversion():
    import json
    user_id = session.get("user_id")

    # Whitelist and validate fields from the form
    try:
        from_currency = request.form.get("from_currency", "").strip().upper()
        to_currency = request.form.get("to_currency", "").strip().upper()
        amount = float(request.form.get("amount", "0"))
        converted_amount = float(request.form.get("converted_amount", "0"))
        rate = float(request.form.get("rate", "0"))
        rupee_status = request.form.get("rupee_status", "")[:200]
    except (ValueError, TypeError):
        flash("Could not save: invalid conversion data.", "error")
        return redirect(url_for("converter"))

    allowed = ["USD", "EUR", "GBP", "JPY", "AED", "INR"]
    if from_currency not in allowed or to_currency not in allowed:
        flash("Could not save: unsupported currency.", "error")
        return redirect(url_for("converter"))

    title = f"{amount:g} {from_currency} → {converted_amount:.2f} {to_currency}"
    summary = f"1 {from_currency} = {rate:.4f} {to_currency}"
    params = json.dumps({
        "from_currency": from_currency,
        "to_currency": to_currency,
        "amount": amount,
        "converted_amount": converted_amount,
        "rate": rate,
        "rupee_status": rupee_status,
    })

    ok, err = database.add_saved_item(user_id, "conversion", title, summary, params)
    if ok:
        flash("Conversion saved to My Conversions.", "success")
    else:
        flash(err or "Could not save conversion.", "error")
    return redirect(url_for("account.my_conversions"))


@account_bp.route("/my-conversions/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_conversion(item_id):
    user_id = session.get("user_id")
    deleted = database.delete_saved_item(user_id, item_id)
    if deleted:
        flash("Saved conversion deleted.", "success")
    else:
        flash("Item not found or unauthorized.", "error")
    return redirect(url_for("account.my_conversions"))


# ----- Saved Travel Plans -----

@account_bp.route("/my-travel-plans")
@login_required
def my_travel_plans():
    user_id = session.get("user_id")
    database.check_user_alerts(user_id)
    import json
    raw_items = database.get_saved_items(user_id, kind="trip")
    items = []
    for it in raw_items:
        try:
            params = json.loads(it["params"])
        except (ValueError, KeyError):
            params = {}
        items.append({**it, "parsed_params": params, "reopen_url": _build_reopen_url("trip", params)})
    total_saved = database.count_saved_items(user_id)
    return render_template(
        "my_travel_plans.html",
        items=items,
        total_saved=total_saved,
        saved_max=SAVED_ITEM_MAX,
        active="my-travel-plans",
    )


@account_bp.route("/my-travel-plans/save", methods=["POST"])
@login_required
def save_travel_plan():
    import json
    user_id = session.get("user_id")

    try:
        destination = request.form.get("destination", "").strip()[:10]
        destination_label = request.form.get("destination_label", "").strip()[:100]
        currency = request.form.get("currency", "").strip().upper()[:5]
        plan_by = request.form.get("plan_by", "daily").strip()
        days = int(float(request.form.get("days", "0")))
        buffer_pct = float(request.form.get("buffer_pct", "0"))
        suggested_inr = float(request.form.get("suggested_inr", "0"))
        suggested_foreign = float(request.form.get("suggested_foreign", "0"))
        rate = float(request.form.get("rate", "0"))
        travel_date = request.form.get("travel_date", "").strip()[:10]
    except (ValueError, TypeError):
        flash("Could not save: invalid travel plan data.", "error")
        return redirect(url_for("travel_planner"))

    daily_spend = None
    total_budget = None
    if plan_by == "daily":
        try:
            daily_spend = float(request.form.get("daily_spend", "0"))
        except (ValueError, TypeError):
            daily_spend = 0.0
    else:
        plan_by = "total"
        try:
            total_budget = float(request.form.get("total_budget", "0"))
        except (ValueError, TypeError):
            total_budget = 0.0

    allowed_currencies = ["USD", "EUR", "GBP", "JPY", "AED"]
    if currency not in allowed_currencies:
        flash("Could not save: unsupported currency.", "error")
        return redirect(url_for("travel_planner"))

    title = f"{days}-day trip to {destination_label} ({currency})"
    summary = f"Budget ₹{suggested_inr:,.0f} · Rate {rate:.4f} · {buffer_pct:.0f}% buffer"
    params = json.dumps({
        "destination": destination,
        "destination_label": destination_label,
        "currency": currency,
        "plan_by": plan_by,
        "days": days,
        "daily_spend": daily_spend,
        "total_budget": total_budget,
        "buffer_pct": buffer_pct,
        "travel_date": travel_date,
        "rate": rate,
        "suggested_inr": suggested_inr,
        "suggested_foreign": suggested_foreign,
    })

    ok, err = database.add_saved_item(user_id, "trip", title, summary, params)
    if ok:
        flash("Travel plan saved to My Travel Plans.", "success")
    else:
        flash(err or "Could not save travel plan.", "error")
    return redirect(url_for("account.my_travel_plans"))


@account_bp.route("/my-travel-plans/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_travel_plan(item_id):
    user_id = session.get("user_id")
    deleted = database.delete_saved_item(user_id, item_id)
    if deleted:
        flash("Saved travel plan deleted.", "success")
    else:
        flash("Item not found or unauthorized.", "error")
    return redirect(url_for("account.my_travel_plans"))


# ----- Saved Decisions -----

@account_bp.route("/my-decisions")
@login_required
def my_decisions():
    user_id = session.get("user_id")
    database.check_user_alerts(user_id)
    import json
    raw_items = database.get_saved_items(user_id, kind="audit")
    items = []
    for it in raw_items:
        try:
            params = json.loads(it["params"])
        except (ValueError, KeyError):
            params = {}
        items.append({**it, "parsed_params": params, "reopen_url": _build_reopen_url("audit", params)})
    total_saved = database.count_saved_items(user_id)
    return render_template(
        "my_decisions.html",
        items=items,
        total_saved=total_saved,
        saved_max=SAVED_ITEM_MAX,
        active="my-decisions",
    )


@account_bp.route("/my-decisions/save", methods=["POST"])
@login_required
def save_decision():
    import json
    user_id = session.get("user_id")

    try:
        direction = request.form.get("direction", "buy").strip()
        currency = request.form.get("currency", "").strip().upper()[:5]
        amount = float(request.form.get("amount", "0"))
        offer_rate = float(request.form.get("offer_rate", "0"))
        quote_unit = request.form.get("quote_unit", "1").strip()
        flat_fee = float(request.form.get("flat_fee", "0") or "0")
        percent_fee = float(request.form.get("percent_fee", "0") or "0")
        other_charges = float(request.form.get("other_charges", "0") or "0")
        effective_rate = float(request.form.get("effective_rate", "0"))
        reference_rate = float(request.form.get("reference_rate", "0"))
        markup_pct = float(request.form.get("markup_pct", "0"))
        extra_cost_inr = float(request.form.get("extra_cost_inr", "0"))
        verdict_title = request.form.get("verdict_title", "")[:200]
        verdict_level = request.form.get("verdict_level", "")[:20]
    except (ValueError, TypeError):
        flash("Could not save: invalid decision data.", "error")
        return redirect(url_for("decision_assistant"))

    allowed_currencies = ["USD", "EUR", "GBP", "JPY", "AED"]
    if currency not in allowed_currencies:
        flash("Could not save: unsupported currency.", "error")
        return redirect(url_for("decision_assistant"))
    if direction not in ("buy", "sell"):
        flash("Could not save: invalid direction.", "error")
        return redirect(url_for("decision_assistant"))
    if quote_unit not in ("1", "100"):
        quote_unit = "1"

    sign = "+" if extra_cost_inr <= 0 else ""
    title = f"{direction.capitalize()} {currency} — Offer ₹{offer_rate:.4f} ({markup_pct:.2f}% vs reference)"
    summary = f"Effective rate ₹{effective_rate:.4f} · Verdict: {verdict_title}"
    params = json.dumps({
        "direction": direction,
        "currency": currency,
        "amount": amount,
        "offer_rate": offer_rate,
        "quote_unit": quote_unit,
        "flat_fee": flat_fee,
        "percent_fee": percent_fee,
        "other_charges": other_charges,
        "effective_rate": effective_rate,
        "reference_rate": reference_rate,
        "markup_pct": markup_pct,
        "extra_cost_inr": extra_cost_inr,
        "verdict_title": verdict_title,
        "verdict_level": verdict_level,
    })

    ok, err = database.add_saved_item(user_id, "audit", title, summary, params)
    if ok:
        flash("Decision saved to My Decisions.", "success")
    else:
        flash(err or "Could not save decision.", "error")
    return redirect(url_for("account.my_decisions"))


@account_bp.route("/my-decisions/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_decision(item_id):
    user_id = session.get("user_id")
    deleted = database.delete_saved_item(user_id, item_id)
    if deleted:
        flash("Saved decision deleted.", "success")
    else:
        flash("Item not found or unauthorized.", "error")
    return redirect(url_for("account.my_decisions"))


# ---------------------------------------------------------------------------
# Stage 8 — Account Settings (Profile, Change Password, Delete Account)
# ---------------------------------------------------------------------------

@account_bp.route("/account")
@login_required
def account_settings():
    user_id = session.get("user_id")
    user_record = database.get_user_by_id(user_id)
    username = user_record[1] if user_record else session.get("username", "User")
    created_at = user_record[2] if user_record else "Unknown"
    join_date = created_at[:10] if created_at and len(created_at) >= 10 else created_at

    return render_template(
        "account_settings.html",
        username=username,
        join_date=join_date,
        active="account"
    )


@account_bp.route("/account/password", methods=["POST"])
@login_required
def change_password():
    user_id = session.get("user_id")
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not current_password or not new_password or not confirm_password:
        flash("All password fields are required.", "error")
        return redirect(url_for("account.account_settings"))

    # Fetch stored password hash for the authenticated user
    conn = sqlite3.connect(database.DATABASE_NAME)
    cur = conn.cursor()
    cur.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()

    if not row or not check_password_hash(row[0], current_password):
        conn.close()
        flash("Incorrect current password.", "error")
        return redirect(url_for("account.account_settings"))

    stored_hash = row[0]

    if new_password != confirm_password:
        conn.close()
        flash("New passwords do not match.", "error")
        return redirect(url_for("account.account_settings"))

    if check_password_hash(stored_hash, new_password):
        conn.close()
        flash("New password must be different from current password.", "error")
        return redirect(url_for("account.account_settings"))

    is_valid_pw, pw_err = validate_password_strength(new_password)
    if not is_valid_pw:
        conn.close()
        flash(pw_err, "error")
        return redirect(url_for("account.account_settings"))

    # Update password hash in users table
    new_hash = generate_password_hash(new_password)
    cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
    conn.commit()
    conn.close()

    flash("Password updated successfully.", "success")
    return redirect(url_for("account.account_settings"))


@account_bp.route("/account/delete", methods=["POST"])
@login_required
def delete_account():
    user_id = session.get("user_id")
    current_password = request.form.get("current_password", "")
    confirm_phrase = request.form.get("confirm_phrase", "").strip()

    if confirm_phrase != "DELETE":
        flash("You must type DELETE in all caps to confirm deletion.", "error")
        return redirect(url_for("account.account_settings"))

    # Verify current password before deletion
    conn = sqlite3.connect(database.DATABASE_NAME)
    cur = conn.cursor()
    cur.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()

    if not row or not check_password_hash(row[0], current_password):
        flash("Incorrect password. Account was not deleted.", "error")
        return redirect(url_for("account.account_settings"))

    # Explicitly delete all user data using the Stage 1 database helper
    database.delete_entire_user_account(user_id)

    # Invalidate session immediately
    session.clear()

    flash("Your account has been permanently deleted.", "info")
    return redirect(url_for("home"))


