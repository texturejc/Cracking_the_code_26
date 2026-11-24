"""
Prep script -- NOT part of the class. Run once to build the two JSON files the
Week 3 practical demo reads; students just load the JSON.

    python3 make_market_data.py

Writes:
    headlines.json     {"2023-01-03": ["headline one", "headline two", ...], ...}
    semis_prices.json  {"NVDA": {"2023-01-03": 14.30, ...}, "AMD": {...}, ...}

Headlines are lower-cased with punctuation replaced by spaces, so that
headline.split() gives clean words ("Nvidia's" -> "nvidia s").
Prices are daily closing prices (adjusted for splits and dividends).

Source: the semantic-trader project's historical_headlines.parquet and
historical_prices.parquet.
"""
import json
import re

import pandas as pd

SRC = "/Users/jamescarney/Desktop/Old_machine/semantic_transformer/semantic-trader/data"
START = "2023-01-01"
END = "2025-12-31"

# Semiconductor stocks, plus SMH, an ETF that holds a basket of them
TICKERS = ["NVDA", "AMD", "INTC", "MU", "AVGO", "QCOM", "AMAT", "SMH"]


def clean(title):
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


# Headlines: one list per calendar day
heads = pd.read_parquet(f"{SRC}/historical_headlines.parquet", columns=["date", "title"])
heads = heads[(heads.date >= START) & (heads.date <= END)].dropna()
headlines = {}
for date, title in zip(heads.date, heads.title):
    headlines.setdefault(date, []).append(clean(title))
headlines = dict(sorted(headlines.items()))

with open("headlines.json", "w", encoding="utf-8") as fh:
    json.dump(headlines, fh, ensure_ascii=False)

# Prices: one {date: close} dict per ticker, in date order
prices = pd.read_parquet(f"{SRC}/historical_prices.parquet", columns=["Date", "Close", "etf"])
prices["date"] = prices.Date.dt.strftime("%Y-%m-%d")
prices = prices[(prices.date >= START) & (prices.date <= END) & prices.etf.isin(TICKERS)]
prices = prices.sort_values("date")

semis = {}
for ticker in TICKERS:
    rows = prices[prices.etf == ticker]
    semis[ticker] = {d: round(c, 4) for d, c in zip(rows.date, rows.Close)}

with open("semis_prices.json", "w", encoding="utf-8") as fh:
    json.dump(semis, fh, indent=1)

print(f"{len(headlines)} days of headlines, {sum(len(v) for v in headlines.values())} headlines")
for ticker in TICKERS:
    print(ticker, len(semis[ticker]), "trading days")
