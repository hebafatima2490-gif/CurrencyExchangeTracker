# International Currency Exchange Rate Tracker

A comprehensive financial planning portal and Bureau de Change ledger engineered for verified exchange rate tracking, 30-observation volatility monitoring, and currency conversion against the Indian Rupee (INR).

---

## Technology Stack

- **Backend**: Python (Flask)
- **Database**: SQLite3 (`currency_tracker.db`) with atomic updates, indexing, and deduplication
- **Data Source**: [Frankfurter API v2](https://api.frankfurter.dev) (European Central Bank interbank reference rates)
- **Frontend**: Accessible HTML5 semantic markup, Sovereign Intaglio & Banknote CSS theme
- **Visualizations**: Chart.js for longitudinal graphs, HTML5 Canvas + GSAP ScrollTrigger for cinematic frame sequences
- **Security**: Werkzeug secure password hashing (`generate_password_hash`, `check_password_hash`), configurable environment secret keys

---

## Core Features

1. **Bureau de Change Rates Dashboard (`/`)**
   - Displays verified mid-market rates for **USD**, **EUR**, **GBP**, **JPY**, and **AED** against **INR**.
   - Features a split-flap departure board hero animation.
   - Computes rolling 30-observation averages, Mean Absolute Percentage Deviation (MAPD) volatility, and automated buy/wait/hold signals.
   - Pinned Global Wealth Scene 1 cinematic scroll-driven canvas sequence.

2. **Currency Converter Desk (`/converter` & `/convert`)**
   - Instant conversions between global reserve currencies and the Indian Rupee.
   - Server-side validation rejecting empty, non-numeric, zero, negative, NaN, and infinite inputs.
   - Real-time and offline cached benchmark rate fallback with rupee weakening/strengthening status indicators.

3. **Historical Analytics & Longitudinal Graphs (`/history`)**
   - **Daily History Graph**: Interactive timeline tracking daily rates with custom date filters and trend-colored segment points.
   - **Monthly Historical Graph (2000 to Current Year)**: Explores over 26 years of monthly averages with milestone navigation (2000, 2005, 2010, 2015, 2020, 2025, 2026).
   - Dynamic calendar year bounds that automatically scale with the system clock.

4. **Forex Decision Assistant (`/decision-assistant`)**
   - Audits retail quotes from banks or money changers.
   - Calculates effective rates, markup percentages, hidden spreads, flat fees, commission percentages, and applicable taxes against reference benchmarks.
   - Provides an action verification checklist before transacting.

5. **Travel Money Planner (`/travel-planner`)**
   - Models foreign currency and Rupee requirements for overseas trips.
   - Generates sensitivity scenarios (±1%, ±2%, ±5% exchange rate shifts) to plan safety buffers.

6. **User Authentication (`/register`, `/login`, `/logout`)**
   - Secure registration and login backed by SQLite user accounts.
   - Public analytical tools remain accessible to all users; authenticated sessions display user identification.

---

## Calculation & Methodology Reference

### 1. 30-Observation Rolling Average
$$\bar{r} = \frac{1}{N} \sum_{i=1}^{N} r_i \quad (N \le 30)$$
Computed over the most recent 30 recorded market observations in SQLite. Because foreign exchange markets are closed on weekends and exchange holidays, 30 market observations span approximately 40 to 45 calendar days.

### 2. Volatility Index (Mean Absolute Percentage Deviation - MAPD)
$$\text{MAPD} = \frac{1}{N} \sum_{i=1}^{N} \frac{|r_i - \bar{r}|}{\bar{r}} \times 100\%$$
- **Low Volatility** (< 1.0%): Stable market regime.
- **Medium Volatility** (1.0% – 2.0%): Moderate day-to-day rate fluctuations.
- **High Volatility** (> 2.0%): Heightened exchange rate variance.

### 3. Smart Recommendations
- **Buy Now**: Current rate is $\ge 102\%$ of the 30-observation average ($\ge +2\%$).
- **Wait**: Current rate is $\le 98\%$ of the 30-observation average ($\le -2\%$).
- **Hold**: Current rate is within $\pm 2\%$ of the 30-observation average.

### 4. Monthly Averages (Unweighted Arithmetic Mean)
$$\text{Monthly Average} = \frac{\sum \text{Daily Observations in Month}}{\text{Number of Observations}}$$
Calculated as an **unweighted arithmetic mean** where each daily observation is weighted equally ($1/N$). Transaction volume data is not present in mid-market reference feeds. Annual summaries calculate the unweighted mean of all available monthly averages.

---

## Setup & Installation

### Prerequisites
- Python 3.10+ (tested through Python 3.14)
- Git

### 1. Clone & Set Up Virtual Environment
```bash
git clone <repository-url>
cd CurrencyExchangeTracker

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# Windows (CMD):
.\.venv\Scripts\activate.bat
# Linux / macOS:
source .venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```
*(Dependencies: `flask`, `requests`, `werkzeug`)*

### 3. Environment & Security Configuration

The application securely loads its session secret key from the environment.

- **Production Mode**: When running in production (`FLASK_ENV=production` or `ENV=production`), `FLASK_SECRET_KEY` is **mandatory**. The application will fail to start if it is missing, preventing insecure deployments.
- **Local Development**: If `FLASK_SECRET_KEY` is omitted and the server is not in production mode, a local development fallback key is used automatically so you can get started immediately.

#### Generating a Strong Secret Key
Generate a cryptographically secure 64-character random key using Python:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

#### Setting the Environment Variable
- **Windows (PowerShell)**:
  ```powershell
  $env:FLASK_SECRET_KEY = "your-generated-secret-key"
  $env:FLASK_ENV = "production" # When deploying to production
  ```
- **Windows (Command Prompt)**:
  ```cmd
  set FLASK_SECRET_KEY=your-generated-secret-key
  set FLASK_ENV=production
  ```
- **Linux / macOS (Bash / Zsh)**:
  ```bash
  export FLASK_SECRET_KEY="your-generated-secret-key"
  export FLASK_ENV="production"
  ```

### 4. Run the Application
```bash
python app.py
```
Open your browser and navigate to `http://127.0.0.1:5000/`.

---

## Running the Test Suite

The project includes unit and integration tests covering math, routes, database integrity, error handling, and historical monthly graphs:

```bash
# Run all unit test suites
python -m unittest test_new_features test_historical_enhancements test_suite -v
```

---

## Project Structure

```
CurrencyExchangeTracker/
├── app.py                         # Flask web application and routes
├── api.py                         # Frankfurter API client & observation date tracking
├── database.py                    # SQLite schema, queries, deduplication & statistics
├── forex_tools.py                 # Pure calculation engine for Decision Assistant & Planner
├── requirements.txt               # Python package dependencies
├── currency_tracker.db            # SQLite database
│
├── static/
│   ├── css/
│   │   ├── main.css               # Sovereign Intaglio & Banknote stylesheet
│   │   └── scene1.css             # Pinned Scene 1 Canvas & ScrollTrigger styles
│   ├── js/
│   │   ├── main.js                # Split-flap board animation & navigation
│   │   └── scene1.js              # 95-frame responsive Canvas engine with GSAP scrub
│   └── frames/scene1/             # Extracted cinematic sequence frames (1 to 95)
│
├── templates/
│   ├── base.html                  # Accessible master layout & navigation
│   ├── index.html                 # Dashboard & Scene 1 experience
│   ├── converter.html             # Currency Converter interface
│   ├── conversion_result.html     # Conversion receipt & rate spread summary
│   ├── history.html               # Daily & monthly historical charts
│   ├── decision_assistant.html    # Forex quote fee auditor
│   ├── travel_planner.html        # Trip currency budget planner
│   ├── about.html                 # Methodology & disclosures
│   ├── login.html                 # Account login
│   ├── register.html              # Account registration
│   ├── tool_base.html             # Shared financial tool layout
│   └── _official_resources.html   # Regulatory & RBI verified resources
│
└── tests/
    ├── test_new_features.py       # Decision Assistant & Travel Planner tests
    ├── test_historical_enhancements.py # 2000-2026 historical graph tests
    └── test_suite.py              # Core database, dashboard & converter tests
```