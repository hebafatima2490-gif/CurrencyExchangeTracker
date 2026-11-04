import urllib.request
import urllib.parse
import json

base_url = "http://127.0.0.1:5000"

# 1. Test Home Dashboard
with urllib.request.urlopen(base_url + "/") as resp:
    html = resp.read().decode("utf-8")
    assert resp.status == 200
    assert "International Currency Exchange Rate Tracker" in html
    assert "Smart Recommendation" in html
    assert "Volatility Index" in html
    print("PASS 1: Dashboard (/) loaded successfully.")

# 2. Test History USD
with urllib.request.urlopen(base_url + "/history?currency=USD") as resp:
    html = resp.read().decode("utf-8")
    assert resp.status == 200
    assert "USD → INR Exchange Rate" in html
    assert 'id="start_date"' in html
    assert 'id="end_date"' in html
    assert "Historical USD to INR exchange rates" in html
    print("PASS 2: History USD (/history?currency=USD) loaded successfully.")

# 3. Test History EUR
with urllib.request.urlopen(base_url + "/history?currency=EUR") as resp:
    html = resp.read().decode("utf-8")
    assert resp.status == 200
    assert "EUR → INR Exchange Rate" in html
    assert "Historical EUR to INR exchange rates" in html
    print("PASS 3: History EUR (/history?currency=EUR) loaded successfully with dynamic title.")

# 4. Test Date Filtering (2026-09-10 to 2026-09-20)
url = base_url + "/history?currency=USD&start_date=2026-09-10&end_date=2026-09-20"
with urllib.request.urlopen(url) as resp:
    html = resp.read().decode("utf-8")
    assert resp.status == 200
    assert "<td>2026-09-10</td>" in html
    assert "<td>2026-09-20</td>" in html
    assert "<td>2026-09-01</td>" not in html
    assert "<td>2026-09-25</td>" not in html
    assert "Reset" in html
    print("PASS 4: Date filter applied correctly. Filtered records returned.")

# 5. Test Date Validation (Invalid Range)
url_invalid = base_url + "/history?currency=USD&start_date=2026-09-20&end_date=2026-09-10"
with urllib.request.urlopen(url_invalid) as resp:
    html = resp.read().decode("utf-8")
    assert resp.status == 200
    assert "Start date cannot be after end date" in html
    print("PASS 5: Invalid date range properly caught and error displayed.")

# 6. Test Currency Conversion POST
data = urllib.parse.urlencode({"from_currency": "USD", "to_currency": "INR", "amount": "50"}).encode("utf-8")
req = urllib.request.Request(base_url + "/convert", data=data)
with urllib.request.urlopen(req) as resp:
    html = resp.read().decode("utf-8")
    assert resp.status == 200
    assert "Currency Conversion Result" in html
    print("PASS 6: Currency conversion (/convert) working properly.")

# 7. Test Historical Monthly API for Year 2000
with urllib.request.urlopen(base_url + "/api/historical-monthly?currency=USD&year=2000") as resp:
    assert resp.status == 200
    payload = json.loads(resp.read().decode("utf-8"))
    assert payload["success"] is True
    assert payload["year"] == 2000
    assert payload["currency"] == "USD"
    assert len(payload["labels"]) == 12
    assert len(payload["rates"]) == 12
    assert payload["summary"]["available_months"] == 12
    assert payload["summary"]["highest_average"] > 0
    assert "USD to INR — Monthly Average Exchange Rates — 2000" in payload["title"]
    print("PASS 7: Historical monthly API (/api/historical-monthly?year=2000) returned valid verified data.")

# 8. Test Historical Year Navigation & Future Month Representation (Year 2026)
with urllib.request.urlopen(base_url + "/api/historical-monthly?currency=EUR&year=2026") as resp:
    assert resp.status == 200
    payload = json.loads(resp.read().decode("utf-8"))
    assert payload["success"] is True
    assert payload["year"] == 2026
    assert payload["currency"] == "EUR"
    # Future month Dec 2026 must be None (not fake)
    assert payload["rates"][11] is None
    assert payload["trends"][11] == "missing"
    print("PASS 8: Future months (Dec 2026) accurately represented as missing without fake interpolation.")

# 9. Test Dynamic Daily Range API
with urllib.request.urlopen(base_url + "/api/dynamic-daily?currency=USD&range=30d") as resp:
    assert resp.status == 200
    payload = json.loads(resp.read().decode("utf-8"))
    assert payload["success"] is True
    assert len(payload["dates"]) > 0
    assert len(payload["rates"]) > 0
    assert len(payload["colors"]) == len(payload["rates"])
    print("PASS 9: Dynamic daily range API (/api/dynamic-daily?range=30d) returned colored trend series.")

# 10. Test Year Navigation HTML Controls
with urllib.request.urlopen(base_url + "/history?currency=USD&year=2000") as resp:
    html = resp.read().decode("utf-8")
    assert resp.status == 200
    assert "monthlyChart" in html
    assert "prevYearBtn" in html
    assert "nextYearBtn" in html
    assert "yearSelect" in html
    assert "USD to INR — Monthly Average Exchange Rates — 2000" in html
    assert "Highest Monthly Average" in html
    assert "Lowest Monthly Average" in html
    assert "Data Coverage" in html
    print("PASS 10: Year navigation controls, summary statistics, and dual charts rendered in HTML.")

print("\nALL 10 END-TO-END HTTP TESTS PASSED SUCCESSFULLY!")
