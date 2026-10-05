"""DDP-4 old-data validation for the Dhan Data API POC (docs/plan/dhan-data-poc).

Scratch, read-only against Dhan, the Upstox Parquet chain, bhavcopy and portfolio.sqlite. No orders.
Raw Dhan responses go to data/historical/dhan_poc/ (gitignored); logs to data/historical/dhan_poc/logs/.
Pulls are resumable: a call whose file already exists is skipped.

Usage (run from the repo root; stdout carries aggregates only, details go to the log file):
    PYTHONPATH=. python scratch/data_probes/2026-10-05_dhan_ddp4_validation.py pull --dry-run
    PYTHONPATH=. python scratch/data_probes/2026-10-05_dhan_ddp4_validation.py pull
    PYTHONPATH=. python scratch/data_probes/2026-10-05_dhan_ddp4_validation.py analyze
    PYTHONPATH=. python scratch/data_probes/2026-10-05_dhan_ddp4_validation.py pull-paper --dry-run
    PYTHONPATH=. python scratch/data_probes/2026-10-05_dhan_ddp4_validation.py pull-paper
    PYTHONPATH=. python scratch/data_probes/2026-10-05_dhan_ddp4_validation.py analyze

Inferences (marked in the output): expiry of a rolling contract comes from the Tuesday rule, not from
Dhan; Dhan delta is a Black-Scholes value from Dhan's own IV (expired data has no delta).
"""

from __future__ import annotations

import argparse
import glob
import gzip
import json
import logging
import sqlite3
import sys
from datetime import date, datetime, timezone
from datetime import time as dtime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root, so no PYTHONPATH needed

from scratch._lib.dhan_data_api import (  # noqa: E402
    auth_headers,
    bs_delta,
    call,
    expiry_for,
    last_tuesday,
    rolling_body,
)

BASE = Path("data/historical/dhan_poc")
CHAIN_DIR = "data/historical/option_chain/intraday"
DB_PATH = "data/portfolio/portfolio.sqlite"
BOD_PATH = "data/instruments/NSE.json.gz"
PLAN_END = "2026-11-04"
GAP_S = 1.0
WINDOWS = [
    (date(2026, 6, 1), date(2026, 6, 30)),
    (date(2026, 7, 1), date(2026, 7, 30)),
    (date(2026, 7, 31), date(2026, 8, 29)),
    (date(2026, 8, 30), date(2026, 9, 28)),
    (date(2026, 9, 29), date(2026, 10, 5)),
]
OFFSETS = ["ATM", "ATM+5", "ATM-5", "ATM+10", "ATM-10"]
TOL = 0.05  # price tolerance in rupees for range containment
TDL1_POINTS = [  # (entry date, Tradetron strike) from docs/plan/tradetron-delta-and-long-window/findings.md
    (date(2026, 8, 12), 25600),
    (date(2026, 8, 19), 25100),
    (date(2026, 9, 2), 24700),
    (date(2026, 9, 9), 24250),
    (date(2026, 9, 16), 24400),
    (date(2026, 9, 25), 23950),
]

log = logging.getLogger("ddp4")


def say(msg: str = "") -> None:
    """Print an aggregate line and mirror it to the log file."""
    print(msg)
    log.debug(msg)


def setup_logging(phase: str) -> Path:
    """Log INFO to stdout and DEBUG to a timestamped file under BASE/logs."""
    (BASE / "logs").mkdir(parents=True, exist_ok=True)
    path = BASE / "logs" / f"ddp4_{phase}_{datetime.now():%Y%m%d_%H%M%S}.log"
    fh = logging.FileHandler(path)
    fh.setLevel(logging.DEBUG)
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)-5s %(message)s",
        handlers=[fh, sh],
    )
    return path


def rolling_path(
    kind: str, flag: str, opt: str, strike: str, interval: str, s: date, e: date
) -> Path:
    tok = strike.replace("+", "p").replace("-", "m")
    return BASE / kind / f"{flag}_{opt}_{tok}_{interval}m_{s}_{e}.json"


def fetch_one(
    h: dict[str, str], path: Path, flag: str, opt: str, strike: str, interval: str, s: date, e: date
) -> str:
    """Pull one rolling response unless cached. Returns cached | ok | empty | err | stop."""
    if path.exists():
        return "cached"
    body = rolling_body(strike, opt, flag, 1, interval, s, e)
    data, err = call("POST", "/charts/rollingoption", h, body, GAP_S)
    if err:
        log.warning("ERR %s %s %s %s %s..%s: %s", flag, opt, strike, interval, s, e, err)
        return "stop" if ("805" in err or "429" in err) else "err"
    side = "ce" if opt == "CALL" else "pe"
    block = (data.get("data") or {}).get(side) or {}
    rows = max((len(v) for v in block.values() if isinstance(v, list)), default=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"request": body, "response": data}))
    log.info(
        "%s %s %-7s %s..%s rows=%d bytes=%d", flag, opt, strike, s, e, rows, path.stat().st_size
    )
    return "ok" if rows else "empty"


def run_pull(args: argparse.Namespace) -> int:
    cases = [
        (flag, opt, strike, s, e)
        for s, e in WINDOWS
        for flag in ("MONTH", "WEEK")
        for opt in ("CALL", "PUT")
        for strike in OFFSETS
    ]
    todo = [
        c
        for c in cases
        if not rolling_path("rolling", c[0], c[1], c[2], args.interval, c[3], c[4]).exists()
    ]
    log.info(
        "pull plan: %d calls total, %d cached, %d to pull (interval %sm)",
        len(cases),
        len(cases) - len(todo),
        len(todo),
        args.interval,
    )
    if args.dry_run:
        return 0
    h = auth_headers()
    counts: dict[str, int] = {}
    for flag, opt, strike, s, e in todo:
        status = fetch_one(
            h,
            rolling_path("rolling", flag, opt, strike, args.interval, s, e),
            flag,
            opt,
            strike,
            args.interval,
            s,
            e,
        )
        counts[status] = counts.get(status, 0) + 1
        if status == "stop":
            log.error("rate limit hit; stopping. Re-run `pull` later to resume.")
            break
    write_manifest(counts)
    log.info("SUMMARY pull: %s", counts)
    return 0 if not counts.get("stop") and not counts.get("err") else 1


def write_manifest(counts: dict[str, int]) -> None:
    files = list(BASE.glob("**/*.json"))
    size_mb = sum(f.stat().st_size for f in files) / 1e6
    lines = [
        "# Dhan POC raw data",
        "",
        f"Last pull run: {datetime.now():%Y-%m-%d %H:%M}. Plan access ends {PLAN_END}.",
        "Raw `rollingoption` responses (request + response) written by "
        "`scratch/data_probes/2026-10-05_dhan_ddp4_validation.py`; story `docs/plan/dhan-data-poc`.",
        f"Files: {len(files)}, {size_mb:.1f} MB. Last run status counts: {counts}.",
        "Gitignored (`/data/`). Do not store tokens or client ids here.",
    ]
    (BASE / "MANIFEST.md").write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------- loading


def load_dhan(kind: str) -> pd.DataFrame:
    """All saved rolling responses of a kind as one frame (IST-naive minute stamps)."""
    frames = []
    for f in sorted((BASE / kind).glob("*.json")):
        doc = json.loads(f.read_text())
        req = doc["request"]
        side = "ce" if req["drvOptionType"] == "CALL" else "pe"
        block = (doc["response"].get("data") or {}).get(side) or {}
        if not block.get("timestamp"):
            continue
        df = pd.DataFrame({k: v for k, v in block.items() if isinstance(v, list)})
        df["flag"], df["opt"] = req["expiryFlag"], "CE" if side == "ce" else "PE"
        df["offset"] = req["strike"]
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    unit = "ms" if df["timestamp"].iloc[0] > 1e11 else "s"
    utc = pd.to_datetime(df["timestamp"], unit=unit)
    df["ts"], shift = _pick_ist(utc)
    log.info(
        "dhan %s: %d rows from %d files; timestamp shift vs UTC: %s",
        kind,
        len(df),
        len(frames),
        shift,
    )
    df["minute"] = df["ts"].dt.floor("min")
    df["date"] = df["ts"].dt.date
    return df


def _pick_ist(utc: pd.Series) -> tuple[pd.Series, str]:
    """Pick the shift (UTC+5:30 or none) that puts the modal first candle of each day at 09:15."""
    for label, shift in (("+5:30", pd.Timedelta(hours=5, minutes=30)), ("0", pd.Timedelta(0))):
        cand = utc + shift
        first = cand.groupby(cand.dt.normalize()).min().dt.time
        if first.mode().iloc[0] == dtime(9, 15):
            return cand, label
    log.warning("first candle of day is not 09:15 under either shift; using UTC+5:30 UNVERIFIED")
    return utc + pd.Timedelta(hours=5, minutes=30), "+5:30 (unverified)"


def load_upstox(dates: list[date]) -> pd.DataFrame:
    """Stored Upstox intraday chain snapshots for the given dates (floats; IST-naive minute)."""
    cols = [
        "snapshot_ts",
        "expiry_date",
        "strike",
        "option_type",
        "spot",
        "ltp",
        "oi",
        "iv",
        "delta",
    ]
    frames = []
    for d in dates:
        files = glob.glob(f"{CHAIN_DIR}/{d:%Y/%m/%d}/*.parquet")
        for f in files:
            t = pq.read_table(f, columns=cols).to_pandas()
            for c in ("strike", "spot", "ltp", "iv", "delta"):
                t[c] = t[c].astype(float)
            frames.append(t)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    ist = df["snapshot_ts"].dt.tz_convert("UTC").dt.tz_localize(None) + pd.Timedelta(
        hours=5, minutes=30
    )
    df["minute"] = ist.dt.floor("min")
    df["expiry"] = pd.to_datetime(df["expiry_date"]).dt.date
    return df


def dist(x: pd.Series) -> str:
    x = x.dropna()
    if x.empty:
        return "n=0"
    q = x.quantile([0.1, 0.5, 0.9])
    return f"n={len(x)} p10={q.iloc[0]:.2f} med={q.iloc[1]:.2f} p90={q.iloc[2]:.2f}"


# ---------------------------------------------------------------- analysis


def add_expiry(df: pd.DataFrame) -> pd.DataFrame:
    keys = df[["date", "flag"]].drop_duplicates()
    keys["expiry"] = [expiry_for(d, f, 1) for d, f in zip(keys["date"], keys["flag"], strict=True)]
    return df.merge(keys, on=["date", "flag"], how="left")


def compare_upstox(dh: pd.DataFrame) -> None:
    dates = sorted(dh["date"].unique())
    up = load_upstox(dates)
    say(f"\n[A] DHAN vs STORED UPSTOX CHAIN (dhan dates={len(dates)}, {dates[0]}..{dates[-1]})")
    if up.empty:
        say("  no Upstox snapshots found for these dates")
        return
    up_dates = set(up["minute"].dt.date)
    say(
        f"  upstox snapshot rows={len(up)}, dates with any snapshot={len(up_dates)}; dhan dates with none: "
        f"{[str(d) for d in dates if d not in up_dates][:10]}"
    )
    up = up.drop_duplicates(["minute", "strike", "option_type", "expiry"])
    keys = ["minute", "strike", "opt", "expiry"]
    up = up.rename(columns={"option_type": "opt"})
    m = dh.merge(up, on=keys, how="left", suffixes=("_dh", "_up"), indicator=True)
    has_min = m["minute"].isin(set(up["minute"]))
    say(
        f"  dhan rows={len(m)}; rows whose minute has an upstox snapshot={int(has_min.sum())}; "
        f"matched on strike+expiry(inferred)={int((m['_merge'] == 'both').sum())}"
    )
    j = m[m["_merge"] == "both"].copy()
    log.debug("matched by flag: %s", j.groupby("flag").size().to_dict())
    for label, sub in (("all matched", j), ("dhan candle volume>0", j[j["volume"] > 0])):
        report_pair(label, sub)


def report_pair(label: str, j: pd.DataFrame) -> None:
    live = j[(j["ltp"] > 0) & (j["close"] > 0)]
    inside = (
        ((live["ltp"] >= live["low"] - TOL) & (live["ltp"] <= live["high"] + TOL)).mean()
        if len(live)
        else float("nan")
    )
    dif = live["ltp"] - live["close"]
    rel = (dif.abs() / live["close"])[live["close"] >= 1]
    iv_scale = 100.0 if j["iv_up"].median() < 1.5 else 1.0
    div = j["iv_up"] * iv_scale - j["iv_dh"]
    oi_eq = (j["oi_up"] == j["oi_dh"]).mean() if len(j) else float("nan")
    t = np.array([(e - d).days / 365 for e, d in zip(j["expiry"], j["date"], strict=True)])
    md = [
        bs_delta(s, k, tt, iv, o == "CE")
        for s, k, tt, iv, o in zip(j["spot_dh"], j["strike"], t, j["iv_dh"], j["opt"], strict=True)
    ]
    j = j.assign(model_delta=md)
    dd = (j["model_delta"].abs() - j["delta"].abs())[j["delta"].abs() > 0]
    say(f"  -- {label}: matched rows {len(j)}")
    say(
        f"     LTP: upstox ltp within dhan [low,high]±{TOL}: {inside:.1%} (n={len(live)}); "
        f"ltp-close {dist(dif)}; rel |diff| (close>=1) {dist(rel)}"
    )
    say(f"     OI: exactly equal {oi_eq:.1%}; diff {dist((j['oi_up'] - j['oi_dh']).astype(float))}")
    say(f"     IV (upstox units assumed x{iv_scale:g} to percent): upstox-dhan {dist(div)}")
    say(f"     spot: upstox-dhan {dist(j['spot_up'] - j['spot_dh'])}")
    say(
        f"     delta [INFERENCE: model delta from Dhan IV vs upstox |delta|]: model-upstox {dist(dd)}"
    )
    say(
        f"     upstox ltp==0 rows: {int((j['ltp'] == 0).sum())}; by flag: {j.groupby('flag').size().to_dict()}"
    )


def compare_bhavcopy(dh: pd.DataFrame) -> None:
    from src.backtest.bhavcopy_loader import load_options_ohlcv

    lo, hi = dh["date"].min(), dh["date"].max()
    bh = load_options_ohlcv("NIFTY", lo, hi)
    say(
        f"\n[B] DHAN vs BHAVCOPY (loader range {lo}..{hi}): bhavcopy rows={len(bh)}, "
        f"trade dates={bh['trade_date'].nunique() if len(bh) else 0}"
    )
    if bh.empty:
        say("  no bhavcopy in range")
        return
    day = (
        dh.sort_values("ts")
        .groupby(["date", "flag", "opt", "strike"], as_index=False)
        .agg(close=("close", "last"), oi=("oi", "last"), volume=("volume", "sum"))
    )
    day = add_expiry(day)
    bh = bh.assign(
        strike=bh["strike"].astype(float), option_type=bh["option_type"].str.upper().str[:2]
    )
    bh = bh.rename(columns={"trade_date": "date", "expiry": "expiry", "option_type": "opt"})
    for c in ("close", "settle_price"):
        bh[c] = bh[c].astype(float)
    j = day.merge(bh, on=["date", "strike", "opt", "expiry"], suffixes=("_dh", "_bh"))
    say(
        f"  dhan contract-days={len(day)}, matched to bhavcopy={len(j)}, dates={sorted(set(map(str, j['date'])))[:5]}"
    )
    if j.empty:
        return
    say(f"     close: dhan last candle - bhav close {dist(j['close_dh'] - j['close_bh'])}")
    say(f"     close: dhan last candle - bhav settle {dist(j['close_dh'] - j['settle_price'])}")
    say(
        f"     OI: dhan - bhav {dist((j['oi_dh'] - j['oi_bh']).astype(float))}; equal {(j['oi_dh'] == j['oi_bh']).mean():.1%}"
    )
    say(f"     volume: dhan - bhav {dist((j['volume_dh'] - j['volume_bh']).astype(float))}")


def spot_by_date(dh: pd.DataFrame) -> dict[date, float]:
    first = dh.sort_values("ts").groupby("date")["spot"].first()
    return {d: float(v) for d, v in first.items()}


def load_paper(dates_spot: dict[date, float]) -> pd.DataFrame:
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    q = "select strategy_name, leg_role, instrument_key, trade_date, action, price from paper_trades where trade_date >= '2026-06-01'"
    rows = pd.read_sql_query(q, con)
    con.close()
    rows["price"] = rows["price"].astype(float)
    rows["date"] = pd.to_datetime(rows["trade_date"]).dt.date
    keys = set(rows["instrument_key"])
    bod = {}
    for r in json.load(gzip.open(BOD_PATH)):
        if r.get("instrument_key") in keys:
            bod[r["instrument_key"]] = r
    out = []
    for r in rows.itertuples():
        i = bod.get(r.instrument_key)
        if i is None:
            out.append((None, None, None, "key not in BOD file"))
        elif i.get("instrument_type") not in ("CE", "PE"):
            out.append((None, None, None, "not an option"))
        else:
            exp = datetime.fromtimestamp(i["expiry"] / 1000, tz=timezone.utc).date()
            out.append((float(i["strike_price"]), i["instrument_type"], exp, ""))
    rows[["strike", "opt", "expiry", "reason"]] = pd.DataFrame(
        out, index=rows.index, columns=["strike", "opt", "expiry", "reason"]
    )
    rows["spot"] = rows["date"].map(dates_spot)
    for idx, r in rows[rows["reason"] == ""].iterrows():
        rows.at[idx, "reason"] = classify(r)
    return rows


def classify(r: pd.Series) -> str:
    if pd.isna(r["spot"]):
        return "no dhan spot that day"
    atm = round(r["spot"] / 50) * 50
    off = round((r["strike"] - atm) / 50)
    flag = "MONTH" if r["expiry"] == last_tuesday(r["expiry"].year, r["expiry"].month) else "WEEK"
    if r["expiry"] != expiry_for(r["date"], flag, 1):
        if r["expiry"] > expiry_for(r["date"], flag, 3):
            return "expiry beyond code 3"
        return "code 2/3 (ATM only)"
    if abs(off) > 10:
        return "outside ATM±10"
    return "checkable"


def paper_requests(paper: pd.DataFrame, spread: int) -> list[tuple[date, str, str, str]]:
    """Unique (date, flag, option, strike token) pulls needed for the checkable paper trades."""
    need = set()
    for r in paper[paper["reason"] == "checkable"].itertuples():
        atm = round(r.spot / 50) * 50
        off = round((r.strike - atm) / 50)
        flag = "MONTH" if r.expiry == last_tuesday(r.expiry.year, r.expiry.month) else "WEEK"
        for o in range(off - spread, off + spread + 1):
            if abs(o) <= 10:
                need.add(
                    (
                        r.date,
                        flag,
                        "CALL" if r.opt == "CE" else "PUT",
                        "ATM" if o == 0 else f"ATM{o:+d}",
                    )
                )
    return sorted(need)


def report_paper(paper: pd.DataFrame, dp: pd.DataFrame) -> None:
    say(f"\n[C] DHAN vs PAPER TRADES (paper_trades rows since 2026-06-01: {len(paper)})")
    say("  checkability by reason: " + str(paper["reason"].value_counts().to_dict()))
    chk = paper[paper["reason"] == "checkable"]
    say(f"  checkable by strategy: {chk['strategy_name'].value_counts().head(10).to_dict()}")
    if dp.empty or chk.empty:
        say("  no paper pulls yet (run pull-paper) or nothing checkable")
        return
    dp = add_expiry(dp)
    res = []
    for r in chk.itertuples():
        rows = dp[
            (dp["date"] == r.date)
            & (dp["strike"] == r.strike)
            & (dp["opt"] == r.opt)
            & (dp["expiry"] == r.expiry)
        ]
        if rows.empty:
            res.append((r.strategy_name, r.action, "no dhan rows", np.nan))
            continue
        lo, hi = rows["low"].min(), rows["high"].max()
        ok = lo - TOL <= r.price <= hi + TOL
        res.append(
            (
                r.strategy_name,
                r.action,
                "inside" if ok else "outside",
                r.price - (hi if r.price > hi else lo if r.price < lo else r.price),
            )
        )
    out = pd.DataFrame(res, columns=["strategy", "action", "verdict", "miss"])
    say(f"  price within dhan day [low,high]±{TOL}: {out['verdict'].value_counts().to_dict()}")
    say(f"  miss size when outside (rupees) {dist(out.loc[out['verdict'] == 'outside', 'miss'])}")
    log.debug("paper check detail:\n%s", out.groupby(["strategy", "verdict"]).size().to_string())


def run_analyze(args: argparse.Namespace) -> int:
    dh = load_dhan("rolling")
    if dh.empty:
        log.error("no pulled data under %s/rolling; run `pull` first", BASE)
        return 1
    dh = add_expiry(dh)
    say(
        f"DHAN rows={len(dh)} dates={dh['date'].nunique()} {dh['date'].min()}..{dh['date'].max()} "
        f"by flag={dh.groupby('flag').size().to_dict()}"
    )
    compare_upstox(dh)
    compare_bhavcopy(dh)
    spots = spot_by_date(dh)
    paper = load_paper(spots)
    report_paper(
        paper, add_expiry(load_dhan("paper")) if (BASE / "paper").exists() else pd.DataFrame()
    )
    say("\n[D] TDL-1 TEST POINTS vs ATM±10 window (offset in 50-point strikes from day-open ATM)")
    for d, k in TDL1_POINTS:
        s = spots.get(d)
        off = None if s is None else round((k - round(s / 50) * 50) / 50)
        say(
            f"  {d} strike {k}: spot {s} offset {off} -> {'inside' if off is not None and abs(off) <= 10 else 'outside/unknown'}"
        )
    return 0


def run_pull_paper(args: argparse.Namespace) -> int:
    dh = load_dhan("rolling")
    if dh.empty:
        log.error("run `pull` first (spot per day comes from it)")
        return 1
    paper = load_paper(spot_by_date(dh))
    reqs = paper_requests(paper, args.spread)
    todo = [
        r for r in reqs if not rolling_path("paper", r[1], r[2], r[3], "1", r[0], r[0]).exists()
    ]
    log.info(
        "paper pull plan: %d calls needed, %d cached, %d to pull (spread ±%d)",
        len(reqs),
        len(reqs) - len(todo),
        len(todo),
        args.spread,
    )
    log.info("checkability by reason: %s", paper["reason"].value_counts().to_dict())
    if args.dry_run:
        return 0
    if len(todo) > args.max_calls:
        log.error(
            "%d calls exceeds --max-calls %d; raise it or lower --spread", len(todo), args.max_calls
        )
        return 1
    h = auth_headers()
    counts: dict[str, int] = {}
    for d, flag, opt, strike in todo:
        status = fetch_one(
            h, rolling_path("paper", flag, opt, strike, "1", d, d), flag, opt, strike, "1", d, d
        )
        counts[status] = counts.get(status, 0) + 1
        if status == "stop":
            log.error("rate limit hit; stopping. Re-run `pull-paper` later to resume.")
            break
    write_manifest(counts)
    log.info("SUMMARY pull-paper: %s", counts)
    return 0 if not counts.get("stop") and not counts.get("err") else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pull")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--interval", default="1", choices=["1", "5", "15", "60"])
    pp = sub.add_parser("pull-paper")
    pp.add_argument("--dry-run", action="store_true")
    pp.add_argument(
        "--spread", type=int, default=1, help="also pull ±N strike offsets around each paper strike"
    )
    pp.add_argument("--max-calls", type=int, default=150)
    sub.add_parser("analyze")
    args = ap.parse_args()
    logpath = setup_logging(args.cmd)
    log.info("start %s; log file %s", args.cmd, logpath)
    fn = {"pull": run_pull, "pull-paper": run_pull_paper, "analyze": run_analyze}[args.cmd]
    rc = fn(args)
    log.info("done rc=%d; full log %s", rc, logpath)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
