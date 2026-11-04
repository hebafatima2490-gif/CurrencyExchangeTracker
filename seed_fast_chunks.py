"""
High-efficiency seeder for 2000-2026 historical exchange rate data.
Uses 3 chunk queries per currency to stay well within Frankfurter API rate limits.
"""

from collections import defaultdict
from datetime import datetime
import time
import requests
from database import (
    create_database,
    has_monthly_data_for_year,
    save_historical_rates_batch,
    save_monthly_rates_batch,
    DATABASE_NAME
)

CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AED"]
TARGET = "INR"

CHUNKS = [
    ("2000-01-01", "2009-12-31", 2000, 2009),
    ("2010-01-01", "2020-12-31", 2010, 2020),
    ("2021-01-01", "2026-11-01", 2021, 2026),
]


def process_chunk(base_currency, start_date, end_date, start_year, end_year):
    # Check if all years in this chunk are already cached
    all_cached = all(has_monthly_data_for_year(base_currency, TARGET, y) for y in range(start_year, end_year + 1))
    if all_cached:
        print(f"  {base_currency} {start_year}-{end_year}: already fully cached.")
        return True

    url = (
        f"https://api.frankfurter.dev/v2/rates"
        f"?base={base_currency}"
        f"&quotes={TARGET}"
        f"&from={start_date}"
        f"&to={end_date}"
    )

    max_retries = 4
    for attempt in range(max_retries):
        try:
            print(f"  Fetching {base_currency} ({start_date} to {end_date}), attempt {attempt+1}...")
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                data = r.json()
                if not isinstance(data, list) or not data:
                    print(f"  No data for {base_currency} {start_date}..{end_date}")
                    return False

                daily_records = []
                by_year_month = defaultdict(list)

                for row in data:
                    d = row.get("date")
                    rate = row.get("rate")
                    if d and rate is not None:
                        y = int(d[:4])
                        if start_year <= y <= end_year:
                            m = int(d[5:7])
                            val = float(rate)
                            daily_records.append((d, base_currency, TARGET, val))
                            by_year_month[(y, m)].append(val)

                if daily_records:
                    save_historical_rates_batch(daily_records)

                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                monthly_batch = []
                for (y, m), rates in by_year_month.items():
                    avg_val = round(sum(rates) / len(rates), 4)
                    cnt = len(rates)
                    monthly_batch.append((
                        base_currency,
                        TARGET,
                        y,
                        m,
                        avg_val,
                        cnt,
                        "Frankfurter API",
                        now_str
                    ))

                if monthly_batch:
                    save_monthly_rates_batch(monthly_batch)
                    print(f"  Saved {len(monthly_batch)} monthly averages ({len(daily_records)} daily rates) for {base_currency} {start_year}-{end_year}")
                    return True
                return False

            elif r.status_code == 429:
                wait_sec = 25
                print(f"  Rate limited (429). Waiting {wait_sec}s before retry...")
                time.sleep(wait_sec)
            else:
                print(f"  HTTP Error {r.status_code}: {r.text[:100]}")
                time.sleep(5)

        except Exception as e:
            print(f"  Request exception: {e}")
            time.sleep(5)

    return False


def main():
    create_database()
    print("=== Starting Fast Chunk Seeder for 2000-2026 Historical Data ===")
    for cur in CURRENCIES:
        print(f"\nProcessing currency: {cur} -> {TARGET}")
        for start_date, end_date, sy, ey in CHUNKS:
            process_chunk(cur, start_date, end_date, sy, ey)
            time.sleep(2)  # courteous delay between chunks

    print("\n=== Seeding Finished! ===")


if __name__ == "__main__":
    main()

