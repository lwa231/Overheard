"""PAPER trading on real prices. Never real money: no broker, no account, no order is sent anywhere; the only network call is the price fetch (net.py).
A paper portfolio starts with the finance allocation and is kept in one JSON file (written to a temp file, then renamed). Its one rule is a PLACEHOLDER, not a
strategy: buy with all cash when the 3-sample average of the price crosses above its 8-sample average, sell everything when it crosses below. No fees, no slippage.
The P&L feeds the finance returns card (returns.compute); returns.totals keeps it out of the agency net."""
import json
import logging
import math
import os
import time

from .gates import save_json

PLACEHOLDER = "PLACEHOLDER, not a strategy: moving-average crossover on real prices, PAPER money, no broker, no orders sent anywhere"
FAST, SLOW, EVERY_S, KEEP_TRADES = 3, 8, 300, 20        # sample windows; seconds between price fetches (asset prices are samples, not ticks)
log = logging.getLogger(__name__)


def _avg(xs):
    return sum(xs) / len(xs)


def _num(v, lo=0.0):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= lo


class Paper:
    def __init__(self, path, symbols, fetch, clock=time.time, start=8.0):
        """fetch: symbol -> price (net.fetch_price, or a fake in tests); clock: seconds, injected."""
        self.path, self.symbols, self.fetch, self.clock = path, list(symbols), fetch, clock
        self.s = {"start": start, "cash": start, "qty": {}, "cost": {}, "last": {}, "hist": {}, "closed": 0, "wins": 0, "trades": [], "peak": start, "dd": 0.0, "last_try": None, "error": ""}
        try:
            with open(path, encoding="utf-8") as f:
                s = json.load(f)
            if not self._sound(s):
                raise ValueError("unexpected content")
            self.s = s
        except FileNotFoundError:
            pass
        except (OSError, ValueError, RecursionError):                    # damaged: set it aside (never overwritten) and start again from the allocation
            log.warning("paper portfolio %s unreadable: set aside, starting again", path)
            os.replace(path, path + ".bad")

    @staticmethod
    def _sound(s):
        try:
            return (isinstance(s, dict) and set(s) == {"start", "cash", "qty", "cost", "last", "hist", "closed", "wins", "trades", "peak", "dd", "last_try", "error"}
                    and _num(s["start"], 0.01) and _num(s["cash"]) and _num(s["peak"]) and _num(s["dd"])
                    and all(_num(v) for d in ("qty", "cost", "last") for v in s[d].values())
                    and all(isinstance(v, list) and len(v) <= SLOW + 1 and all(_num(p, 1e-12) for p in v) for v in s["hist"].values())
                    and all(isinstance(s[k], int) and not isinstance(s[k], bool) and s[k] >= 0 for k in ("closed", "wins")) and s["wins"] <= s["closed"]
                    and isinstance(s["trades"], list) and isinstance(s["error"], str))
        except (TypeError, AttributeError):
            return False

    def equity(self):
        s = self.s
        return s["cash"] + sum(q * s["last"][k] for k, q in s["qty"].items())

    def price(self, sym, p, now):
        """One new price sample for sym. A missing or unusable price is ignored: no sample, no trade."""
        if sym not in self.symbols or not _num(p, 1e-12) or p >= 1e9:
            return
        s = self.s
        h = s["hist"].setdefault(sym, [])[-SLOW:] + [float(p)]
        s["hist"][sym], s["last"][sym] = h, float(p)
        if len(h) > SLOW:                                       # fast and slow averages before this sample (a) and with it (b)
            fa, sa, fb, sb = _avg(h[-FAST - 1:-1]), _avg(h[:-1]), _avg(h[-FAST:]), _avg(h[-SLOW:])
            if fa <= sa and fb > sb and sym not in s["qty"] and s["cash"] >= 0.01:
                self._trade(sym, "buy", p, s["cash"] / p, now)
            elif fa >= sa and fb < sb and sym in s["qty"]:
                self._trade(sym, "sell", p, s["qty"][sym], now)
        eq = self.equity()
        s["peak"] = max(s["peak"], eq)
        s["dd"] = max(s["dd"], s["peak"] - eq)

    def _trade(self, sym, side, p, qty, now):
        s = self.s
        if side == "buy":
            cost = min(qty * p, s["cash"])                          # never more than the cash: cash cannot go negative
            s["cash"] = round(s["cash"] - cost, 10)
            s["qty"][sym], s["cost"][sym] = qty, cost
        else:
            got = qty * p
            s["cash"] += got
            s["closed"] += 1                                        # running counters, not a list that grows for ever
            s["wins"] += got - s["cost"].pop(sym) > 0
            del s["qty"][sym]
        s["trades"] = (s["trades"] + [{"at": now, "sym": sym, "side": side, "price": p, "qty": qty}])[-KEEP_TRADES:]

    def due(self, now=None):
        """-> the symbols to fetch now ([] if EVERY_S has not passed since the last try; a failed try also counts: no hammering a failing source). Marks the try."""
        now = self.clock() if now is None else now
        if self.s["last_try"] is not None and now - self.s["last_try"] < EVERY_S:
            return []
        self.s["last_try"] = now
        return list(self.symbols)

    def fetch_all(self, syms):
        """-> [(symbol, price or the exception the fetch raised)]. The slow part: the server runs it on its worker thread, never inside the tick."""
        out = []
        for sym in syms:
            try:
                out.append((sym, self.fetch(sym)))
            except Exception as e:  # noqa: BLE001 - a failing source must never stop the dashboard
                out.append((sym, e))
        return out

    def apply(self, got, now):
        """Take the fetched prices (fetch_all's result) in: new samples, trades, the error note, and save."""
        err = ""
        for sym, p in got:
            try:
                if isinstance(p, Exception):
                    raise p
                self.price(sym, p, now)
            except Exception as e:  # noqa: BLE001
                err = "%s: %s" % (sym, type(e).__name__)
        self.s["error"] = err
        save_json(self.path, self.s)

    def step(self, now=None):
        """Fetch and apply in one go (blocks on the fetch; the server uses due/fetch_all/apply instead)."""
        now = self.clock() if now is None else now
        syms = self.due(now)
        if syms:
            self.apply(self.fetch_all(syms), now)

    def snapshot(self):
        s = self.s
        eq, pnl = self.equity(), self.equity() - s["start"]
        return {"paper": True, "label": PLACEHOLDER, "assets": self.symbols, "start": s["start"], "cash": round(s["cash"], 4), "equity": round(eq, 4), "pnl": round(pnl, 4),
                "pnl_pct": round(pnl / s["start"] * 100, 2), "dd_pct": round(s["dd"] / s["start"] * 100, 2), "closed": s["closed"],
                "win_rate_pct": round(100 * s["wins"] / s["closed"]) if s["closed"] else 0, "error": s["error"], "samples": {k: len(v) for k, v in s["hist"].items()},
                "positions": [{"sym": k, "qty": q, "price": s["last"][k], "value": round(q * s["last"][k], 4)} for k, q in s["qty"].items()], "trades": s["trades"][-5:]}
