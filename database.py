import sqlite3
from datetime import datetime


DATABASE_NAME = "currency_tracker.db"


def create_database():
    connection = sqlite3.connect(DATABASE_NAME)

    cursor = connection.cursor()

    # Existing tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exchange_rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            base_currency TEXT NOT NULL,
            target_currency TEXT NOT NULL,
            rate REAL NOT NULL
        )
    """)

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_exchange_rates_date_currencies
        ON exchange_rates (date, base_currency, target_currency)
    """)

    # Monthly historical averages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monthly_exchange_rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            base_currency TEXT NOT NULL,
            target_currency TEXT NOT NULL,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            average_rate REAL NOT NULL,
            observations_count INTEGER NOT NULL,
            data_source TEXT NOT NULL DEFAULT 'Frankfurter API',
            created_at TEXT
        )
    """)

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_monthly_rates_currency_year_month
        ON monthly_exchange_rates (base_currency, target_currency, year, month)
    """)

    # Users table for authentication
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    connection.commit()
    connection.close()


def save_rate(base_currency, target_currency, rate, date=None):
    if rate is None:
        return False

    connection = sqlite3.connect(DATABASE_NAME)

    cursor = connection.cursor()

    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    # Check whether a rate for this date and currency pair is already stored
    cursor.execute("""
        SELECT id
        FROM exchange_rates
        WHERE date = ?
        AND base_currency = ?
        AND target_currency = ?
    """, (
        date,
        base_currency,
        target_currency
    ))

    existing_record = cursor.fetchone()

    if existing_record:

        # Update existing rate
        cursor.execute("""
            UPDATE exchange_rates
            SET rate = ?
            WHERE id = ?
        """, (
            rate,
            existing_record[0]
        ))

    else:

        # Create a new record
        cursor.execute("""
            INSERT INTO exchange_rates
            (date, base_currency, target_currency, rate)
            VALUES (?, ?, ?, ?)
        """, (
            date,
            base_currency,
            target_currency,
            rate
        ))

    connection.commit()
    connection.close()
    return True


def get_history(base_currency, target_currency, start_date=None, end_date=None):
    connection = sqlite3.connect(DATABASE_NAME)

    cursor = connection.cursor()

    query = """
        SELECT date, rate
        FROM exchange_rates
        WHERE base_currency = ?
        AND target_currency = ?
    """
    params = [base_currency, target_currency]

    if start_date:
        query += " AND date >= ?"
        params.append(start_date)

    if end_date:
        query += " AND date <= ?"
        params.append(end_date)

    query += " ORDER BY date ASC"

    cursor.execute(query, tuple(params))

    history = cursor.fetchall()

    connection.close()

    return history


def get_date_bounds(base_currency, target_currency):
    connection = sqlite3.connect(DATABASE_NAME)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT MIN(date), MAX(date)
        FROM exchange_rates
        WHERE base_currency = ?
        AND target_currency = ?
    """, (base_currency, target_currency))

    result = cursor.fetchone()
    connection.close()

    if result and result[0] and result[1]:
        return result[0], result[1]
    return None, None


def save_historical_rate(date, base_currency, target_currency, rate):
    if rate is None or not date:
        return False

    connection = sqlite3.connect(DATABASE_NAME)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id
        FROM exchange_rates
        WHERE date = ?
        AND base_currency = ?
        AND target_currency = ?
    """, (date, base_currency, target_currency))

    existing_record = cursor.fetchone()

    if existing_record:
        cursor.execute("""
            UPDATE exchange_rates
            SET rate = ?
            WHERE id = ?
        """, (rate, existing_record[0]))
    else:
        cursor.execute("""
            INSERT INTO exchange_rates
            (date, base_currency, target_currency, rate)
            VALUES (?, ?, ?, ?)
        """, (date, base_currency, target_currency, rate))

    connection.commit()
    connection.close()
    return True


def get_previous_rate(base_currency, target_currency):
    connection = sqlite3.connect(DATABASE_NAME)
    cursor = connection.cursor()

    current_date = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT rate
        FROM exchange_rates
        WHERE base_currency = ?
        AND target_currency = ?
        AND date < ?
        ORDER BY date DESC
        LIMIT 1
    """, (base_currency, target_currency, current_date))

    result = cursor.fetchone()

    connection.close()

    if result:
        return result[0]

    return None


def get_latest_rate(base_currency, target_currency):
    """Retrieve the most recent exchange rate regardless of date (useful for offline fallbacks)."""
    connection = sqlite3.connect(DATABASE_NAME)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT rate
        FROM exchange_rates
        WHERE base_currency = ?
        AND target_currency = ?
        ORDER BY date DESC
        LIMIT 1
    """, (base_currency, target_currency))

    result = cursor.fetchone()
    connection.close()

    if result:
        return result[0]
    return None


def get_average_rate(base_currency, target_currency):
    """
    Calculates the 30-observation rolling average exchange rate from SQLite.

    Methodology:
        Unweighted arithmetic mean of the most recent 30 recorded trading observations
        (exchange_rates table ordered by date DESC LIMIT 30). Because foreign exchange
        markets are closed on weekends and financial holidays, 30 trading observations
        typically span approximately 40 to 45 calendar days.
    """
    connection = sqlite3.connect(DATABASE_NAME)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT AVG(rate)
        FROM (
            SELECT rate
            FROM exchange_rates
            WHERE base_currency = ?
            AND target_currency = ?
            ORDER BY date DESC
            LIMIT 30
        )
    """, (base_currency, target_currency))

    result = cursor.fetchone()

    connection.close()

    return result[0] if result[0] is not None else None


def get_volatility(base_currency, target_currency):
    """
    Calculates currency volatility using Mean Absolute Percentage Deviation (MAPD)
    over the most recent 30 recorded market observations.

    Formula:
        Average Rate (r̄) = (1 / N) * sum(rate_i)
        Deviation_i      = |rate_i - r̄| / r̄ * 100%
        Volatility (MAPD)= (1 / N) * sum(Deviation_i)

    Interpretation:
        < 1.0% : Low Volatility (stable currency conditions)
        1.0% - 2.0% : Medium Volatility (moderate price fluctuation)
        > 2.0% : High Volatility (elevated exchange rate movement)
    """
    connection = sqlite3.connect(DATABASE_NAME)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT rate
        FROM exchange_rates
        WHERE base_currency = ?
        AND target_currency = ?
        ORDER BY date DESC
        LIMIT 30
    """, (base_currency, target_currency))

    records = cursor.fetchall()

    connection.close()

    if len(records) < 2:
        return None

    rates = [record[0] for record in records]

    average_rate = sum(rates) / len(rates)

    differences = [
        abs(rate - average_rate) / average_rate * 100
        for rate in rates
    ]

    volatility = sum(differences) / len(differences)

    return volatility


# ==========================================
# Monthly Historical Averages Functions (2000-2026)
# ==========================================

def save_monthly_rate(base_currency, target_currency, year, month, average_rate, observations_count, data_source="Frankfurter API"):
    """Save or update a calculated monthly average rate in SQLite."""
    if average_rate is None or not year or not month:
        return False

    connection = sqlite3.connect(DATABASE_NAME)
    cursor = connection.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO monthly_exchange_rates
        (base_currency, target_currency, year, month, average_rate, observations_count, data_source, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(base_currency, target_currency, year, month)
        DO UPDATE SET
            average_rate = excluded.average_rate,
            observations_count = excluded.observations_count,
            data_source = excluded.data_source,
            created_at = excluded.created_at
    """, (base_currency, target_currency, int(year), int(month), round(float(average_rate), 4), int(observations_count), data_source, now_str))

    connection.commit()
    connection.close()
    return True


def save_monthly_rates_batch(records):
    """
    Batch insert or update monthly exchange rates.
    records: list of tuples: (base_currency, target_currency, year, month, average_rate, observations_count, data_source, created_at)
    """
    if not records:
        return 0

    connection = sqlite3.connect(DATABASE_NAME)
    cursor = connection.cursor()

    cursor.executemany("""
        INSERT INTO monthly_exchange_rates
        (base_currency, target_currency, year, month, average_rate, observations_count, data_source, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(base_currency, target_currency, year, month)
        DO UPDATE SET
            average_rate = excluded.average_rate,
            observations_count = excluded.observations_count,
            data_source = excluded.data_source,
            created_at = excluded.created_at
    """, records)

    connection.commit()
    connection.close()
    return len(records)


def save_historical_rates_batch(records):
    """
    Batch insert or update daily exchange rates in exchange_rates.
    records: list of tuples: (date, base_currency, target_currency, rate)
    """
    if not records:
        return 0

    connection = sqlite3.connect(DATABASE_NAME)
    cursor = connection.cursor()

    cursor.executemany("""
        INSERT INTO exchange_rates (date, base_currency, target_currency, rate)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(date, base_currency, target_currency)
        DO UPDATE SET rate = excluded.rate
    """, records)

    connection.commit()
    connection.close()
    return len(records)


def get_monthly_history(base_currency, target_currency, year):
    """
    Retrieve monthly average rates for a given currency pair and year from SQLite.
    Returns: list of tuples (month, average_rate, observations_count, data_source)
    """
    connection = sqlite3.connect(DATABASE_NAME)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT month, average_rate, observations_count, data_source
        FROM monthly_exchange_rates
        WHERE base_currency = ?
        AND target_currency = ?
        AND year = ?
        ORDER BY month ASC
    """, (base_currency, target_currency, int(year)))

    rows = cursor.fetchall()
    connection.close()
    return rows


def has_monthly_data_for_year(base_currency, target_currency, year):
    """Check if monthly data already exists in SQLite for the given year and currency."""
    connection = sqlite3.connect(DATABASE_NAME)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM monthly_exchange_rates
        WHERE base_currency = ?
        AND target_currency = ?
        AND year = ?
    """, (base_currency, target_currency, int(year)))

    count = cursor.fetchone()[0]
    connection.close()
    return count > 0


def get_available_years_for_monthly(base_currency, target_currency):
    """Return a sorted list of years that have monthly data in SQLite."""
    connection = sqlite3.connect(DATABASE_NAME)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT DISTINCT year
        FROM monthly_exchange_rates
        WHERE base_currency = ?
        AND target_currency = ?
        ORDER BY year ASC
    """, (base_currency, target_currency))

    rows = cursor.fetchall()
    connection.close()
    return [r[0] for r in rows]


def compute_and_save_monthly_from_daily(base_currency, target_currency, year):
    """
    Calculates monthly averages directly from daily records already in exchange_rates table
    and stores them in monthly_exchange_rates table.
    """
    connection = sqlite3.connect(DATABASE_NAME)
    cursor = connection.cursor()

    start_date = f"{year:04d}-01-01"
    end_date = f"{year:04d}-12-31"

    cursor.execute("""
        SELECT
            CAST(strftime('%m', date) AS INTEGER) AS month_num,
            AVG(rate) AS avg_rate,
            COUNT(rate) AS obs_count
        FROM exchange_rates
        WHERE base_currency = ?
          AND target_currency = ?
          AND date >= ?
          AND date <= ?
        GROUP BY month_num
        ORDER BY month_num ASC
    """, (base_currency, target_currency, start_date, end_date))

    rows = cursor.fetchall()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    batch = []
    for month_num, avg_rate, obs_count in rows:
        batch.append((
            base_currency,
            target_currency,
            int(year),
            int(month_num),
            round(avg_rate, 4),
            int(obs_count),
            "Daily Observations Aggregate",
            now_str
        ))

    if batch:
        cursor.executemany("""
            INSERT INTO monthly_exchange_rates
            (base_currency, target_currency, year, month, average_rate, observations_count, data_source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(base_currency, target_currency, year, month)
            DO UPDATE SET
                average_rate = excluded.average_rate,
                observations_count = excluded.observations_count,
                data_source = excluded.data_source,
                created_at = excluded.created_at
        """, batch)
        connection.commit()

    connection.close()
    return len(batch)


def get_latest_rate_with_date(base_currency, target_currency):
    """Most recent stored rate and its date, as (rate, date) or None.
    Used when the live API is unreachable so the page can say how old the rate is."""
    connection = sqlite3.connect(DATABASE_NAME)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT rate, date
        FROM exchange_rates
        WHERE base_currency = ?
        AND target_currency = ?
        ORDER BY date DESC
        LIMIT 1
    """, (base_currency, target_currency))

    result = cursor.fetchone()
    connection.close()
    return (result[0], result[1]) if result else None
