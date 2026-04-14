"""
Polymarket ingestion — dual-source strategy.

fetch_markets() uses the Gamma REST API:
  https://gamma-api.polymarket.com/markets
  - Supports filtering by active/closed and sorting by volume
  - Returns volume, liquidity, outcomePrices as part of the response
  - No auth required

fetch_market() uses the CLOB API for single market lookup:
  https://clob.polymarket.com
  - Authoritative for order book and price data
  - Falls back to Gamma if CLOB lookup fails
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

GAMMA_HOST = "https://gamma-api.polymarket.com"
CLOB_HOST = os.getenv("POLYMARKET_CLOB_HOST", "https://clob.polymarket.com")

_HTTP_TIMEOUT = 20  # seconds


@dataclass
class Market:
    condition_id: str
    question: str
    implied_prob: Optional[float]   # YES token price ≈ probability
    volume: Optional[float]
    end_date: Optional[str]
    active: bool = True
    raw: dict = field(default_factory=dict, repr=False)

    def delta(self, estimate: float) -> float:
        """Signal delta: LLM estimate minus market-implied probability."""
        if self.implied_prob is None:
            return 0.0
        return estimate - self.implied_prob


# ---------------------------------------------------------------------------
# Price extraction
# ---------------------------------------------------------------------------

def _parse_yes_price(outcome_prices: str, outcomes: str) -> Optional[float]:
    """
    Parse the YES-side price from Gamma API outcomePrices + outcomes fields.

    Both fields are JSON-encoded strings like:
      outcomes:      '["Yes", "No"]'  or  '["Liverpool FC", "Draw", "PSG"]'
      outcomePrices: '["0.345", "0.655"]'

    For explicit Yes/No markets: return the Yes price.
    For binary non-Yes/No markets: return the first outcome price (primary side).
    Multi-outcome markets (3+): return the first outcome price.
    """
    import json as _json
    try:
        prices = _json.loads(outcome_prices)
        labels = _json.loads(outcomes)
    except (TypeError, ValueError):
        return None

    if not prices:
        return None

    # Try to find explicit "Yes" label
    for label, price in zip(labels, prices):
        if str(label).strip().lower() == "yes":
            try:
                p = float(price)
                return p if 0.0 <= p <= 1.0 else None
            except (TypeError, ValueError):
                return None

    # Fallback: first price as the primary outcome probability
    try:
        p = float(prices[0])
        return p if 0.0 <= p <= 1.0 else None
    except (TypeError, ValueError):
        return None


def _normalize_gamma(raw: dict) -> Market:
    """Convert a Gamma API market dict into a normalized Market object."""
    condition_id = raw.get("conditionId") or raw.get("condition_id") or ""
    question = raw.get("question") or "(no question)"

    implied_prob = _parse_yes_price(
        raw.get("outcomePrices", "[]"),
        raw.get("outcomes", "[]"),
    )
    # Also try lastTradePrice as a tiebreaker
    if implied_prob is None:
        ltp = raw.get("lastTradePrice")
        try:
            implied_prob = float(ltp) if ltp is not None else None
        except (TypeError, ValueError):
            implied_prob = None

    volume = None
    for key in ("volumeNum", "volume24hr", "volume"):
        v = raw.get(key)
        if v is not None:
            try:
                volume = float(v)
                break
            except (TypeError, ValueError):
                continue

    end_date = raw.get("endDateIso") or raw.get("endDate") or raw.get("end_date_iso")
    active = bool(raw.get("active", False)) and not bool(raw.get("closed", True))

    return Market(
        condition_id=condition_id,
        question=question,
        implied_prob=implied_prob,
        volume=volume,
        end_date=end_date,
        active=active,
        raw=raw,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_markets(limit: int = 20, only_active: bool = True) -> list[Market]:
    """
    Fetch the top N active markets from Polymarket (Gamma API), sorted by
    24-hour volume descending.

    Args:
        limit:       Max number of markets to return.
        only_active: If True, request only active/non-closed markets.

    Returns:
        List of normalized Market objects, sorted by volume descending.
    """
    params: dict = {
        "limit": min(limit * 2, 100),  # over-fetch slightly for filtering
        "order": "volume24hr",
        "ascending": "false",
    }
    if only_active:
        params["active"] = "true"
        params["closed"] = "false"

    try:
        resp = httpx.get(
            f"{GAMMA_HOST}/markets",
            params=params,
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        raw_list = resp.json()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"Gamma API error {exc.response.status_code}: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Polymarket fetch failed: {exc}") from exc

    markets: list[Market] = []
    for raw in raw_list:
        m = _normalize_gamma(raw)
        if only_active and not m.active:
            continue
        if m.condition_id and m.implied_prob is not None:
            markets.append(m)
        if len(markets) >= limit:
            break

    return markets


def fetch_market(condition_id: str) -> Market:
    """
    Fetch a single market by condition_id.

    Tries Gamma API first (has volume data); falls back to CLOB if not found.

    Args:
        condition_id: Polymarket conditionId (hex string).

    Returns:
        Normalized Market object.

    Raises:
        ValueError: If the market is not found in either source.
    """
    # Try Gamma first — filter client-side since conditionId is not a server filter
    try:
        resp = httpx.get(
            f"{GAMMA_HOST}/markets",
            params={"conditionId": condition_id},
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            for item in data:
                if (item.get("conditionId") or "").lower() == condition_id.lower():
                    return _normalize_gamma(item)
        if isinstance(data, dict):
            if (data.get("conditionId") or "").lower() == condition_id.lower():
                return _normalize_gamma(data)
    except Exception:
        pass

    # Fallback: CLOB API
    try:
        resp = httpx.get(
            f"{CLOB_HOST}/markets/{condition_id}",
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        raw = resp.json()
        if raw:
            return _normalize_clob(raw)
    except Exception as exc:
        raise ValueError(
            f"Market not found in Gamma or CLOB API: {condition_id}"
        ) from exc

    raise ValueError(f"Market not found: {condition_id}")


def _normalize_clob(raw: dict) -> Market:
    """Normalize a CLOB API market response (fallback path)."""
    condition_id = raw.get("condition_id") or ""
    question = raw.get("question") or "(no question)"

    # Extract price from tokens
    tokens = raw.get("tokens") or []
    implied_prob = None
    for token in tokens:
        outcome = str(token.get("outcome") or "").strip().lower()
        if outcome == "yes":
            try:
                p = float(token["price"])
                implied_prob = p if 0.0 <= p <= 1.0 else None
            except (KeyError, TypeError, ValueError):
                pass
            break
    if implied_prob is None and tokens:
        try:
            implied_prob = float(tokens[0].get("price") or 0) or None
        except (TypeError, ValueError):
            pass

    end_date = raw.get("end_date_iso") or raw.get("end_date")
    active = not raw.get("closed", True) and bool(raw.get("accepting_orders", False))

    return Market(
        condition_id=condition_id,
        question=question,
        implied_prob=implied_prob,
        volume=None,
        end_date=end_date,
        active=active,
        raw=raw,
    )
