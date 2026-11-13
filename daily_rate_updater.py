"""
daily_rate_updater.py
=====================
Standalone script that fetches the latest exchange-rate observations from the
Frankfurter API and saves them into the existing SQLite database.

Run manually:
    python daily_rate_updater.py

Dry-run (no DB writes):
    python daily_rate_updater.py --dry-run

Scheduled automatically via Windows Task Scheduler (see register_task.bat) or
a cron job / systemd timer on Linux.

Design principles
-----------------
* No Flask dependency — works while the web app is completely stopped.
* Reuses existing database helpers — no schema changes.
* Records the actual API observation date, never the wall-clock date.
* Idempotent — running twice on the same day inserts nothing the second time.
* Each currency pair is processed independently; a failure on one does not
  block the others.
* After saving new daily rows the current month's average is recalculated and
  upserted into monthly_exchange_rates so the 2000-2026 graph stays current.
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler

import requests

# ---------------------------------------------------------------------------
# Path setup — allow the script to be run from any working directory
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import database

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AED"]
TARGET = "INR"
API_BASE_URL = "https://api.frankfurter.dev/v2/rates"
REQUEST_TIMEOUT = 20          # seconds per HTTP request
MAX_RETRIES = 3               # attempts per currency pair before giving up
RETRY_WAIT_429 = 30           # seconds to wait after a 429 rate-limit response
RETRY_WAIT_OTHER = 5          # seconds to wait after any other failure
INTER_CURRENCY_DELAY = 2      # seconds between successive currency fetches
LOG_FILE = os.path.join(SCRIPT_DIR, "updater.log")
LOG_MAX_BYTES = 1_048_576     # 1 MB
LOG_BACKUP_COUNT = 3

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _build_logger() -> logging.Logger:
    logger = logging.getLogger("daily_rate_updater")
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        return logger  # already configured (e.g. during tests)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

    # Rotating file handler
    try:
        fh = RotatingFileHandler(LOG_FILE, maxBytes=LOG_MAX_BYTES,
                                  backupCount=LOG_BACKUP_COUNT, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError as exc:
        # Non-fatal — if we cannot write the log file, continue with console only
        print(f"[WARN] Cannot open log file {LOG_FILE}: {exc}")

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger


log = _build_logger()

# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _get_latest_stored_date(base: str, target: str) -> str | None:
    """
    Return the most recently stored observation date for a currency pair,
    or None if no records exist yet.
    """
    result = database.get_latest_rate_with_date(base, target)
    return result[1] if result else None


def _fetch_missing_rates(base: str, target: str,
                          dry_run: bool = False) -> dict:
    """
    Determine what dates are missing, fetch them from Frankfurter, and persist
    them to the database.

    Returns a summary dict:
        {
            "currency": str,
            "skipped": bool,       # True if already up-to-date
            "records_saved": int,
            "error": str | None
        }
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    latest = _get_latest_stored_date(base, target)

    if latest is None:
        # No data at all — start from a sensible default (90 days back)
        fetch_from = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        log.info("%s/%s: No existing records. Fetching from %s.", base, target, fetch_from)
    else:
        # Start from the day after the last stored observation
        next_day = (datetime.strptime(latest, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        if next_day > today_str:
            log.info("%s/%s: Already up-to-date (latest: %s).", base, target, latest)
            return {"currency": base, "skipped": True, "records_saved": 0, "error": None}
        fetch_from = next_day
        log.info("%s/%s: Fetching from %s to %s.", base, target, fetch_from, today_str)

    url = f"{API_BASE_URL}?base={base}&quotes={target}&from={fetch_from}&to={today_str}"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)

            if resp.status_code == 200:
                data = resp.json()
                if not isinstance(data, list) or not data:
                    log.info("%s/%s: API returned no observations for %s–%s "
                             "(weekend / holiday gap — normal).", base, target, fetch_from, today_str)
                    return {"currency": base, "skipped": False, "records_saved": 0, "error": None}

                # Build records list from API response
                records = []
                for item in data:
                    obs_date = item.get("date")
                    rate = item.get("rate")
                    if obs_date and rate is not None:
                        records.append((obs_date, base, target, float(rate)))

                if not records:
                    log.info("%s/%s: No parseable records in API response.", base, target)
                    return {"currency": base, "skipped": False, "records_saved": 0, "error": None}

                log.info("%s/%s: %d observation(s) received from API.", base, target, len(records))

                if dry_run:
                    log.info("%s/%s: DRY-RUN — skipping database write.", base, target)
                    return {"currency": base, "skipped": False,
                            "records_saved": 0, "error": None}

                # Persist daily records (idempotent upsert)
                saved = database.save_historical_rates_batch(records)
                log.info("%s/%s: %d record(s) upserted.", base, target, saved)

                # Recalculate the current month's average from stored daily rows
                current_year = datetime.now().year
                current_month = datetime.now().month
                database.compute_and_save_monthly_from_daily(base, target, current_year)
                log.debug("%s/%s: Monthly average recalculated for %d-%02d.",
                          base, target, current_year, current_month)

                return {"currency": base, "skipped": False,
                        "records_saved": saved, "error": None}

            elif resp.status_code == 429:
                log.warning("%s/%s: Rate-limited (429). Waiting %ds before retry %d/%d.",
                            base, target, RETRY_WAIT_429, attempt, MAX_RETRIES)
                time.sleep(RETRY_WAIT_429)

            else:
                log.warning("%s/%s: HTTP %d on attempt %d/%d. Body: %s",
                            base, target, resp.status_code, attempt, MAX_RETRIES,
                            resp.text[:120])
                time.sleep(RETRY_WAIT_OTHER)

        except requests.exceptions.RequestException as exc:
            log.warning("%s/%s: Network error on attempt %d/%d: %s",
                        base, target, attempt, MAX_RETRIES, exc)
            time.sleep(RETRY_WAIT_OTHER)

    err_msg = f"All {MAX_RETRIES} attempts failed for {base}/{target}."
    log.error(err_msg)
    return {"currency": base, "skipped": False, "records_saved": 0, "error": err_msg}


def run(dry_run: bool = False) -> list[dict]:
    """
    Entry point for the updater.  Processes all configured currency pairs
    sequentially and returns a list of per-currency summary dicts.
    """
    start_time = datetime.now()
    log.info("=== Daily Rate Updater started (dry_run=%s) ===", dry_run)

    # Ensure the database schema exists before anything else
    database.create_database()

    results = []
    for i, currency in enumerate(CURRENCIES):
        summary = _fetch_missing_rates(currency, TARGET, dry_run=dry_run)
        results.append(summary)
        if i < len(CURRENCIES) - 1:
            time.sleep(INTER_CURRENCY_DELAY)

    # --- Run summary ---
    total_saved = sum(r["records_saved"] for r in results)
    errors = [r for r in results if r["error"]]
    skipped = [r for r in results if r["skipped"]]

    elapsed = (datetime.now() - start_time).total_seconds()
    log.info(
        "=== Update complete — %d new record(s) saved, %d currency(ies) already "
        "up-to-date, %d error(s). Elapsed: %.1fs ===",
        total_saved, len(skipped), len(errors), elapsed
    )

    if errors:
        for e in errors:
            log.error("FAILED: %s — %s", e["currency"], e["error"])

    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch and store the latest Frankfurter exchange-rate observations."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch from the API but do not write anything to the database."
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run)

