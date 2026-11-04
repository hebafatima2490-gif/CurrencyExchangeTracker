from collections import defaultdict
from datetime import datetime
import requests


def get_exchange_rate(base_currency, target_currency):

    url = f"https://api.frankfurter.dev/v2/rate/{base_currency}/{target_currency}"

    try:

        response = requests.get(
            url,
            timeout=10
        )

        if response.status_code == 200:

            data = response.json()

            return data["rate"]

        return None

    except requests.exceptions.RequestException:

        return None


def get_historical_rates(base_currency, target_currency, start_date, end_date):
    url = (
        f"https://api.frankfurter.dev/v2/rates"
        f"?base={base_currency}"
        f"&quotes={target_currency}"
        f"&from={start_date}"
        f"&to={end_date}"
    )

    try:
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                return data
            return []

        return []

    except requests.exceptions.RequestException:
        return []


def fetch_and_cache_year_history(base_currency, target_currency, year):
    """
    Fetches real historical exchange rates for a full year from Frankfurter API,
    calculates monthly averages from actual daily observations, and caches
    both daily observations and monthly averages into SQLite.
    
    Formula:
        Monthly Average = Sum of available daily observations / Number of available daily observations
    """
    from database import save_historical_rates_batch, save_monthly_rates_batch

    start_date = f"{year:04d}-01-01"
    end_date = f"{year:04d}-12-31"

    url = (
        f"https://api.frankfurter.dev/v2/rates"
        f"?base={base_currency}"
        f"&quotes={target_currency}"
        f"&from={start_date}"
        f"&to={end_date}"
    )

    try:
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            return []

        data = response.json()
        if not isinstance(data, list) or len(data) == 0:
            return []

        year_prefix = f"{year:04d}-"
        daily_records = []
        monthly_groups = defaultdict(list)

        for item in data:
            date_str = item.get("date")
            rate = item.get("rate")
            if not date_str or rate is None:
                continue

            # Ensure the date actually belongs to the requested year
            if date_str.startswith(year_prefix):
                daily_records.append((date_str, base_currency, target_currency, float(rate)))
                month_num = int(date_str[5:7])
                monthly_groups[month_num].append(float(rate))

        # Save daily records in batch
        if daily_records:
            save_historical_rates_batch(daily_records)

        # Calculate monthly averages from actual daily observations
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        monthly_batch = []
        monthly_results = []

        for month_num in range(1, 13):
            rates = monthly_groups.get(month_num, [])
            if rates:
                avg_rate = round(sum(rates) / len(rates), 4)
                count = len(rates)
                monthly_batch.append((
                    base_currency,
                    target_currency,
                    int(year),
                    int(month_num),
                    avg_rate,
                    count,
                    "Frankfurter API",
                    now_str
                ))
                monthly_results.append({
                    "month": month_num,
                    "average_rate": avg_rate,
                    "observations_count": count,
                    "data_source": "Frankfurter API"
                })

        # Save monthly averages to database
        if monthly_batch:
            save_monthly_rates_batch(monthly_batch)

        return monthly_results

    except requests.exceptions.RequestException as e:
        print(f"Network error fetching historical data for {base_currency} {year}: {e}")
        return []
