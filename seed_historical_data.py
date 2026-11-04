"""
Script to seed historical exchange rates and calculate monthly averages for 2000-2026.
Uses Frankfurter API v2 and stores the verified real data into SQLite.
"""

import sys
import time
from collections import defaultdict
from datetime import datetime
import requests
from database import (
    create_database,
    has_monthly_data_for_year,
    save_historical_rates_batch,
    save_monthly_rates_batch,
    DATABASE_NAME
)

CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AED"]
TARGET_CURRENCY = "INR"
START_YEAR = 2000
END_YEAR = 2026


def seed_currency_year(base_currency, year):
    """Fetch and store data for a single currency and year."""
    if has_monthly_data_for_year(base_currency, TARGET_CURRENCY, year):
        return True, "Already cached"

    start_date = f"{year:04d}-01-01"
    end_date = f"{year:04d}-12-31"

    url = (
        f"https://api.frankfurter.dev/v2/rates"
        f"?base={base_currency}"
        f"&quotes={TARGET_CURRENCY}"
        f"&from={start_date}"
        f"&to={end_date}"
    )

    try:
        resp = requests.get(url, timeout=20)
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}"

        data = resp.json()
        if not isinstance(data, list) or not data:
            return False, "No data returned"

        year_prefix = f"{year:04d}-"
        daily_records = []
        monthly_groups = defaultdict(list)

        for item in data:
            d = item.get("date")
            r = item.get("rate")
            if d and r is not None and d.startswith(year_prefix):
                daily_records.append((d, base_currency, TARGET_CURRENCY, float(r)))
                month_num = int(d[5:7])
                monthly_groups[month_num].append(float(r))

        if daily_records:
            save_historical_rates_batch(daily_records)

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        monthly_batch = []
        for m in range(1, 13):
            rates = monthly_groups.get(m, [])
            if rates:
                avg_rate = round(sum(rates) / len(rates), 4)
                obs_cnt = len(rates)
                monthly_batch.append((
                    base_currency,
                    TARGET_CURRENCY,
                    int(year),
                    int(m),
                    avg_rate,
                    obs_cnt,
                    "Frankfurter API",
                    now_str
                ))

        if monthly_batch:
            save_monthly_rates_batch(monthly_batch)
            return True, f"Saved {len(monthly_batch)} months, {len(daily_records)} daily rates"
        return False, "No monthly records formed"

    except Exception as e:
        return False, str(e)


def main():
    create_database()
    print("Starting historical data seeding for 2000-2026...")

    total = len(CURRENCIES) * (END_YEAR - START_YEAR + 1)
    current = 0

    for cur in CURRENCIES:
        print(f"\nProcessing currency: {cur} -> {TARGET_CURRENCY}")
        for y in range(START_YEAR, END_YEAR + 1):
            current += 1
            ok, msg = seed_currency_year(cur, y)
            status_symbol = "OK" if ok else "SKIP/FAIL"
            print(f"[{current}/{total}] {cur} {y}: {status_symbol} ({msg})")
            # Brief pause to respect API rate limits
            if "Already cached" not in msg:
                time.sleep(0.3)

    print("\nHistorical data seeding complete!")


if __name__ == "__main__":
    main()

