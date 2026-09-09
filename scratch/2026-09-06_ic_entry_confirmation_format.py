"""Scratch — ROLL-17 IC entry confirmation format: current v1/v2 vs. a unified renderer.

WORKSHOP COMPARISON SCRIPT, not an implementation. Produced 2026-09-06 for the
`message-format-workshop.md` session so Animesh can close ROLL-17's OPEN design decisions
(`strategy-rollout/stories.md` §ROLL-17). No `src/` or `scripts/` file is touched; the
script only renders strings and, with `--send`, posts them to the configured Telegram chat.

backbone/ + formatting-rules/ have BOTH shipped (SHA 57c1c3c / 75cc123), so this imports the
real helpers — `escape_markdown` from `src.notifications.markdown`; `format_greek`,
`format_money`, `format_expiry`, `LegRow`, `build_leg_table` from `src.notifications.formatting`.

DECISIONS TAKEN from Animesh's feedback (2026-09-06):
  #1  LegRow / build_leg_table reused as-is — the IC entry confirmation BECOMES a fenced
      table. No parallel leg dataclass.
  - leg identity is `<strike> <PE|CE>` only (Nifty-only book — no "NIFTY", no "Short Put"
    role text, no per-leg expiry).
  - `[S]` = sold leg, `[B]` = bought leg (build_leg_table's own badge, driven off role
    prefix "Short"/"Long").
  - one consistent row shape for every leg: Act / Instrument / Δ / LTP / Entry.
    Δ and LTP always shown; Entry shown for the short legs (fill captured), "-" for the
    long/hedge legs. No `(hedge)` tag, no `width=Npts`, no `mid=`/`δ=` inline labels.
  - Δ via format_greek (2dp signed), LTP/Entry 1dp (build_leg_table's locked-in exception).

  #A  Mode line — CLOSED 2026-09-06: keep it, renderer omits the line when mode is None
      (so v1 shows `Mode: standalone|concurrent`, v2 shows nothing).
  #B  Entry column — CLOSED 2026-09-06: entry_mode="all" (2b) — every leg shows its fill
      price, including the bought hedges.
  #C  Header kv row — CLOSED 2026-09-06: kv_mode="full" (3a) — IVR DTE Nifty Exp, one line.
  #D  Net-credit line — CLOSED 2026-09-06: credit_mode="compact" (4d) —
      `💰 *Net credit:* ₹103.40/lot  ×65 = ₹6,721.00`.

  #E  Headline — CLOSED 2026-09-06: head_mode="v_and_type" (5c) — `✅ *IC v1 Entry* — weekly`
      / `✅ *IC v2 Entry* — monthly`. v1 and v2 coexist only on the monthly expiry, so the
      v1/v2 marker is the one bit that disambiguates two entry messages landing together;
      the full strategy id (5b) is noisier than needed.

ALL WORKSHOP QUESTIONS CLOSED. `PROPOSED` below is the confirmed format (pending a live
--send check on-device before it is written into strategy-rollout/stories.md).

Run from repo root (venv active):
    python -m scratch.2026-09-06_ic_entry_confirmation_format          # print only
    python scratch/2026-09-06_ic_entry_confirmation_format.py --send   # also send to Telegram
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402
from src.instruments.lookup import format_option_label  # noqa: E402
from src.notifications.formatting import (  # noqa: E402
    LegRow,
    build_leg_table,
    format_expiry,
    format_money,
)
from src.notifications.markdown import escape_markdown, mdcode  # noqa: E402

LOT_SIZE = 65  # src/paper/constants.py — 1 Nifty lot = 65 units, effective Jan 2026

# --------------------------------------------------------------------------------------
# Sample data. leg = (side, strike, opt_type, delta, ltp/mid, entry)
#   side: "S" sold / "B" bought.  All 4 legs are executed at bootstrap so entry is always
#   known; the Q2 variants differ only in which legs *display* it.
# WEEKLY's short-leg rows reproduce the exact table Animesh pasted 2026-09-06.
# --------------------------------------------------------------------------------------

WEEKLY = {
    "expiry_type": "weekly",
    "strategy_name": "paper_ic_nifty_v1_weekly",
    "mode": "standalone",
    "ivr": 0.16,
    "dte": 4,
    "nifty_spot": 23980.0,
    "expiry_str": "2026-09-09",
    "legs": [
        ("S", 23500, "PE", -0.19, 70.8, 103.4),
        ("B", 23000, "PE", -0.07, 23.8, 21.2),
        ("S", 24500, "CE", 0.22, 73.5, 91.3),
        ("B", 25000, "CE", 0.06, 17.1, 15.4),
    ],
    "net_credit": Decimal("103.40"),
}

MONTHLY = {
    "expiry_type": "monthly",
    "strategy_name": "paper_ic_nifty_v2_monthly",
    "mode": None,  # v2 emits no Mode line today
    "ivr": 0.19,
    "dte": 21,
    "nifty_spot": 24610.0,
    "expiry_str": "2026-09-30",
    "legs": [
        ("S", 23000, "PE", -0.030, 118.4, 121.0),
        ("B", 22000, "PE", -0.012, 54.1, 52.6),
        ("S", 26000, "CE", 0.271, 96.2, 98.3),
        ("B", 27000, "CE", 0.104, 38.8, 37.1),
    ],
    "net_credit": Decimal("122.75"),
}


# --------------------------------------------------------------------------------------
# CURRENT renderings — reproduced verbatim from the live f-strings (the drift ROLL-17 fixes)
# --------------------------------------------------------------------------------------


def build_v1_current(d: dict) -> str:
    """paper_ic_entry.py ~L789 as it renders today (escape_markdown over the whole body)."""
    sp, lp, sc, lc = d["legs"]
    exp = d["expiry_str"]
    nc = d["net_credit"]
    return escape_markdown(
        f"✅ IC Entry — {d['expiry_type']} ({d['strategy_name']})\n"
        f"Mode: {d['mode']}\n"
        f"IVR: {d['ivr']:.2f}  DTE: {d['dte']}  Nifty: {d['nifty_spot']:,.0f}\n\n"
        f"Short Put  {format_option_label('NIFTY', sp[1], 'PE', exp)}  "
        f"δ={abs(sp[3]):.3f}  mid=₹{sp[4]:.2f}\n"
        f"Long Put   {format_option_label('NIFTY', lp[1], 'PE', exp)}   "
        f"(hedge)  mid=₹{lp[4]:.2f}\n"
        f"Short Call {format_option_label('NIFTY', sc[1], 'CE', exp)} "
        f"δ={abs(sc[3]):.3f}  mid=₹{sc[4]:.2f}\n"
        f"Long Call  {format_option_label('NIFTY', lc[1], 'CE', exp)}  "
        f"(hedge)  mid=₹{lc[4]:.2f}\n\n"
        f"Net credit: ₹{nc:.2f}/lot  (₹{nc * LOT_SIZE:,.0f} for {LOT_SIZE} units)"
    )


def build_v2_current(d: dict) -> str:
    """paper_ic_entry_v2.py ~L709 as it renders today — bare {strike}PE, no Mode, wings."""
    sp, lp, sc, lc = d["legs"]
    nc = d["net_credit"]
    ww_put = abs(sp[1] - lp[1])
    ww_call = abs(lc[1] - sc[1])
    return escape_markdown(
        f"✅ IC V2 Entry — {d['expiry_type']} ({d['strategy_name']})\n"
        f"IVR: {d['ivr']:.2f}  DTE: {d['dte']}  Nifty: {d['nifty_spot']:,.0f}\n\n"
        f"Short Put  {int(sp[1])}PE  δ={abs(sp[3]):.3f}  mid=₹{sp[4]:.2f}\n"
        f"Long Put   {int(lp[1])}PE   δ={abs(lp[3]):.3f}  width={ww_put:.0f}pts\n"
        f"Short Call {int(sc[1])}CE δ={abs(sc[3]):.3f}  mid=₹{sc[4]:.2f}\n"
        f"Long Call  {int(lc[1])}CE  δ={abs(lc[3]):.3f}  width={ww_call:.0f}pts\n\n"
        f"Net credit: ₹{nc:.2f}/lot  (₹{nc * LOT_SIZE:,.0f} for {LOT_SIZE} units)"
    )


# --------------------------------------------------------------------------------------
# PROPOSED unified renderer — fenced build_leg_table(), one consistent row shape
# --------------------------------------------------------------------------------------


@dataclass
class ICEntryMessage:
    strategy_name: str
    expiry_type: str
    expiry: date
    mode: str | None = None
    ivr: float | None = None
    dte: int | None = None
    spot: float | None = None
    net_credit: Decimal | None = None
    legs: list[LegRow] = field(default_factory=list)


def _esc_bold(s: str) -> str:
    """Escape reserved punctuation but keep the paired * bold markers."""
    return escape_markdown(s).replace("\\*", "*")


def _kv_row(m: ICEntryMessage, kv_mode: str) -> str:
    ivr = f"*IVR:* {m.ivr:.2f}"
    dte = f"*DTE:* {m.dte}"
    spot = f"*Nifty:* {m.spot:,.0f}"
    exp = f"*Exp:* {format_expiry(m.expiry)}"
    if kv_mode == "two_line":
        return _esc_bold(f"{ivr}  {dte}") + "\n" + _esc_bold(f"{spot}  {exp}")
    fields = {
        "full": [ivr, dte, spot, exp],
        "no_exp": [ivr, dte, spot],
        "no_spot": [ivr, dte, exp],
    }[kv_mode]
    return _esc_bold("  ".join(fields))


def _credit_lines(m: ICEntryMessage, credit_mode: str) -> list[str]:
    if m.net_credit is None:
        return []
    per_lot = format_money(m.net_credit)  # ₹103.40  (FMT-1 §3, 2dp)
    total = format_money(m.net_credit * LOT_SIZE)  # ₹6,721.00
    if credit_mode == "inline":
        return [escape_markdown(f"Net credit: {per_lot}/lot  ({total} for {LOT_SIZE} units)")]
    if credit_mode == "bold":
        return [
            _esc_bold(f"💰 *Net credit:* {per_lot}/lot"),
            escape_markdown(f"Total: {total} ({LOT_SIZE} units)"),
        ]
    if credit_mode == "lot_only":
        return [_esc_bold(f"💰 *Net credit:* {per_lot}/lot")]
    if credit_mode == "compact":
        return [_esc_bold(f"💰 *Net credit:* {per_lot}/lot  ×{LOT_SIZE} = {total}")]
    raise ValueError(credit_mode)


def _headline(m: ICEntryMessage, head_mode: str) -> str:
    et = escape_markdown(m.expiry_type)
    ver = "v2" if "v2" in m.strategy_name else "v1"
    if head_mode == "with_id":
        return f"✅ *IC Entry* — {et}  ·  {mdcode(m.strategy_name)}"
    if head_mode == "v_and_type":
        return f"✅ *IC {ver} Entry* — {et}"
    return f"✅ *IC Entry* — {et}"


def format_ic_entry_message(
    m: ICEntryMessage,
    *,
    kv_mode: str = "full",
    credit_mode: str = "compact",
    head_mode: str = "v_and_type",
) -> str:
    """Headline (bold) + optional Mode + kv row + fenced leg table + net-credit line.

    Q2 CLOSED: every leg shows its fill price (build_leg_table as-is).
    Q3 CLOSED: kv_mode="full" — IVR DTE Nifty Exp, one line.
    Q4 CLOSED: credit_mode="compact" — 💰 *Net credit:* ₹X/lot  ×65 = ₹Y.
    head_mode: "type_only" (5a) | "with_id" (5b) | "v_and_type" (5c) — Q5.

    Values via FMT-2 (format_greek inside build_leg_table, format_money for credit) —
    never a re-implemented f"δ={abs(v):.3f}" / f"₹{v:.2f}".
    """
    head = [_headline(m, head_mode)]
    if m.mode is not None:
        head.append(f"*Mode:* {escape_markdown(m.mode)}")
    head.append(_kv_row(m, kv_mode))

    table = ["```", build_leg_table(m.legs), "```"]
    return "\n".join([*head, "", *table, "", *_credit_lines(m, credit_mode)]).rstrip()


def _to_msg(d: dict) -> ICEntryMessage:
    legs = [
        LegRow(
            role="Short" if side == "S" else "Long",
            instrument=f"{int(strike)} {opt}",
            delta=delta,
            ltp=ltp,
            entry=entry,
        )
        for (side, strike, opt, delta, ltp, entry) in d["legs"]
    ]
    return ICEntryMessage(
        strategy_name=d["strategy_name"],
        expiry_type=d["expiry_type"],
        expiry=date.fromisoformat(d["expiry_str"]),
        mode=d["mode"],
        ivr=d["ivr"],
        dte=d["dte"],
        spot=d["nifty_spot"],
        net_credit=d["net_credit"],
        legs=legs,
    )


# --------------------------------------------------------------------------------------
# Render + send
# --------------------------------------------------------------------------------------


def all_renderings() -> list[tuple[str, str]]:
    return [
        ("v1 CURRENT (weekly)", build_v1_current(WEEKLY)),
        ("v1 PROPOSED (weekly)", format_ic_entry_message(_to_msg(WEEKLY))),
        ("v2 CURRENT (monthly)", build_v2_current(MONTHLY)),
        ("v2 PROPOSED (monthly)", format_ic_entry_message(_to_msg(MONTHLY))),
    ]


async def _send(text: str) -> bool:
    payload = {"chat_id": settings.telegram_chat_id, "text": text, "parse_mode": "MarkdownV2"}
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.post(url, json=payload) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    print(f"!! Telegram API error ({resp.status}): {data.get('description')}")
                return bool(data.get("ok"))
    except Exception as exc:  # scratch probe — isolate all API failures
        print(f"!! send failed: {exc}")
        return False


async def main() -> None:
    do_send = "--send" in sys.argv
    for label, text in all_renderings():
        print(f"\n{'=' * 72}\n{label}\n{'-' * 72}")
        print(text)
        if do_send:
            if not settings.telegram_bot_token or not settings.telegram_chat_id:
                print("!! TELEGRAM creds not set — cannot send")
                continue
            # Escape the debug prefix — "ROLL-17" / "( )" / "[ ]" are all MarkdownV2-reserved
            # and would 400 the send before the body is even parsed.
            prefix = escape_markdown(f"[SCRATCH ROLL-17 {label}]")
            ok = await _send(f"{prefix}\n\n{text}")
            print(f"  send -> {ok}")


if __name__ == "__main__":
    asyncio.run(main())
