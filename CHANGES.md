# What changed

## Fixed (the project was mid-refactor and the dashboard was unreachable)
- `app.py`: the `/` route decorator was stranded above `register()`, and the dashboard code sat
  unreachable after `logout()`. Restored it as `home()`. `url_for('home')` now works.
- Added the missing `templates/login.html`.

## New feature 1: Forex Decision Assistant  ->  /decision-assistant
Enter a provider's quote (buy or sell, rate, flat fee, commission %, taxes). See the amount received,
total fees, effective rate and the difference from the reference rate, plus a verification checklist.

## New feature 2: Travel Money Planner  ->  /travel-planner
Destination, trip length, daily spend or total budget, safety buffer, optional travel date. Shows the
budget in the destination currency and INR, a +/-1%, 2%, 5% rate scenario table, a suggested exchange
budget, and the app's existing 30-day average and volatility for that currency.

## Official resources
Shown on both pages (see `OFFICIAL_RESOURCES` in `forex_tools.py`, verified 4 Nov 2026).

## Files
- `forex_tools.py`        all calculations (no Flask, no network)
- `app.py`                two new routes + `get_reference_rate()` (live rate, falls back to saved rate)
- `database.py`           + `get_latest_rate_with_date()`
- `templates/`            `tool_base.html`, `decision_assistant.html`, `travel_planner.html`,
                          `_official_resources.html`, `login.html`; nav links added to index/history
- `test_new_features.py`  34 tests, no internet needed:  python -m unittest test_new_features -v

## Run
    pip install flask requests
    python app.py
