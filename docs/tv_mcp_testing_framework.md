# TradingView MCP — Capability Testing Framework

**Purpose:** Systematic probe of the `tradesdontlie/tradingview-mcp` server to map exactly what data
can be extracted, in what format, and at what fidelity — specifically for NIFTY regime classification
and options strategy selection.

**Setup required:**
- TradingView Desktop launched with `--remote-debugging-port=9222`
- MCP server running and connected to ChatGPT/Codex
- NIFTY 1D chart open as the active tab before running each phase

---

## How to use this document

Each phase is a self-contained test block. Run it in Codex in order. After each block, fill in the
**Record** section with what actually came back. The goal is not to verify the tools work — it is
to map the *data schema and fidelity* so we can build a reliable regime classifier on top.

---

## Phase 0 — Connection Health

**Prompt to Codex:**
```
Run tv_health_check and tell me:
1. Is TradingView Desktop connected?
2. What version / build is reported?
3. How many chart tabs are currently open?
Then run chart_get_state and return the full raw response — do not summarize it.
```

**What we are probing:** baseline connectivity, what `chart_get_state` returns as its raw schema.

**Record:**
- [ ] Connected: yes / no
- [ ] Symbol shown: ___
- [ ] Timeframe shown: ___
- [ ] Indicator list (paste verbatim): ___
- [ ] Fields in chart_get_state response: ___
- [ ] Any unexpected fields or missing data: ___

---

## Phase 1 — Price & Quote Data

**Prompt to Codex:**
```
On the active NIFTY 1D chart, run the following in sequence and return the raw response for each:

1. quote_get — return every field in the response
2. data_get_ohlcv with summary:true — return the full summary object
3. data_get_ohlcv with summary:false, requesting 100 bars — return the first 3 bars and the last
   3 bars verbatim, plus tell me the total bar count returned and the date range covered
4. data_get_ohlcv with summary:false, requesting 500 bars — same: first 3, last 3, total count,
   date range

Do not filter or reshape the responses.
```

**What we are probing:**
- What fields does `quote_get` return? (open, high, low, close, volume, change%, bid/ask?)
- What does `summary:true` give? (OHLCV stats, returns, volatility?)
- What is the maximum bar depth available for NIFTY 1D?
- Is the bar data adjusted or unadjusted?

**Record:**
- [ ] quote_get fields: ___
- [ ] summary:true fields and values: ___
- [ ] Max bars returned at 500 request: ___
- [ ] Earliest date available: ___
- [ ] Bar data format (timestamp format, OHLCV field names): ___
- [ ] Any gaps or anomalies in dates: ___

---

## Phase 2 — Built-in Indicator Reading

**Setup:** Before running this phase, manually add these indicators to the NIFTY 1D chart in
TradingView (use default settings):
- RSI (14)
- ATR (14)
- Average Directional Index (ADX, 14, smoothing 14)
- EMA (21)
- EMA (144)
- Bollinger Bands (20, 2.0)
- Volume

**Prompt to Codex:**
```
Run data_get_study_values and return:
1. The full raw response — all indicator names, IDs, and their current bar values
2. For each indicator found, tell me: is the value a single number or an array of values?
   If array, what are the sub-values? (e.g. BB returns upper/middle/lower?)
3. Does the response include only the current bar, or historical values for each indicator?
   If historical, how many bars back?
4. Are indicator IDs stable across sessions or do they change when TradingView restarts?
```

**What we are probing:**
- Can we reliably read ADX, ATR, EMA values without writing Pine Script?
- Do we get current-bar values only or a mini-history?
- Is there a way to get indicator values at a specific historical bar?

**Record:**
- [ ] Indicator names as returned (exact strings): ___
- [ ] ADX value format (single number or {adx, +DI, -DI}?): ___
- [ ] ATR value format: ___
- [ ] BB value format (upper/mid/lower or single?): ___
- [ ] EMA 21 value: ___ | EMA 144 value: ___
- [ ] Historical depth per indicator: ___
- [ ] ID stability (note for next session test): ___

---

## Phase 3 — Pine Script as Data Pipe (Core Phase)

This is the most important phase. The hypothesis is that we can use Pine Script's `table.new()` as a
structured data output channel that the MCP reads via `data_get_pine_tables`.

**Setup:** Load the `regime_probe.pine` script (in this repo) onto the NIFTY 1D chart and let it
compile cleanly before running the prompts below.

**Prompt 3A — Table readability:**
```
The Regime Probe Pine Script is active on the NIFTY 1D chart.
Run data_get_pine_tables and return:
1. The full raw response — every table, every cell, verbatim
2. How are cells identified? By row/column index, by cell text, or by some other key?
3. Is the table name (as defined in Pine Script) visible in the response?
4. Do numeric values come back as strings or as numbers?
5. If there are multiple tables, how are they distinguished?
```

**Prompt 3B — Label readability:**
```
Run data_get_pine_labels and return:
1. The full raw response for all labels currently on the chart
2. For each label: what fields are present? (price, text, bar_index, color, time?)
3. Can we use labels as a key-value data output from Pine Script?
   (e.g. a label at price=0 with text="ADX:23.4|Regime:Sideways" — is the text field readable?)
```

**Prompt 3C — Reliability test:**
```
Switch the chart to NIFTY 1W (weekly timeframe), wait 3 seconds, then run data_get_pine_tables again.
Return the full table response. Then switch back to 1D and run data_get_pine_tables once more.
I want to know: does the table update correctly when timeframe changes, or does it lag or break?
```

**Prompt 3D — Parameterization:**
```
Use indicator_set_inputs to change the Fast EMA length input on the Regime Probe script from 21 to 34.
After the change:
1. Run data_get_pine_tables — does the regime output update to reflect the new EMA?
2. How long does it take for the table to refresh after an input change?
3. Return the updated table values verbatim.
```

**Record:**
- [ ] Table cell format (row/col index? named keys?): ___
- [ ] Numeric values — string or number type: ___
- [ ] Table identified by name or by index: ___
- [ ] Labels — fields present: ___
- [ ] Labels — full text field readable: yes / no
- [ ] Table updates on timeframe change: yes / no / lag
- [ ] Table updates on input change: yes / no / lag
- [ ] Any data lost or malformed across phases: ___

---

## Phase 4 — India VIX Integration

**Prompt to Codex:**
```
1. Open a new chart tab and set the symbol to NSE:INDIAVIX, timeframe 1D.
2. Run quote_get — return the current VIX value and all fields.
3. Run data_get_ohlcv with summary:true — return the VIX summary stats.
4. Now go back to the NIFTY 1D tab. I want to test cross-symbol data in Pine Script:
   The Regime Probe script uses request.security() to load INDIAVIX inside the NIFTY chart.
   Run data_get_pine_tables — does the VIX value in the table match what quote_get returned on
   the VIX tab? Record both values.
5. How stale is the cross-symbol data in Pine Script vs the direct quote?
```

**What we are probing:**
- Can VIX be read as a direct quote (tab-switch method)?
- Can VIX be embedded in a NIFTY-chart Pine Script via request.security() and read via MCP?
- What is the staleness of request.security() data — is it real-time or delayed?

**Record:**
- [ ] VIX current value from quote_get: ___
- [ ] VIX value in NIFTY Pine table: ___
- [ ] Match? yes / no / delta: ___
- [ ] request.security() staleness (bars of delay): ___

---

## Phase 5 — Batch & Multi-Symbol Sweep

**Prompt to Codex:**
```
Use batch_run to run the following across these symbols, all on 1D timeframe:
- NSE:NIFTY
- NSE:BANKNIFTY
- NSE:INDIAVIX
- NSE:NIFTYBEES

For each symbol, collect:
1. quote_get (current price and change%)
2. data_get_ohlcv with summary:true

Return all results structured as a table with one row per symbol.
Also tell me: how long did the batch operation take total?
```

**What we are probing:**
- Does batch_run work for Indian NSE symbols?
- What is the latency per symbol?
- Can we build a daily multi-instrument snapshot with a single batch call?

**Record:**
- [ ] All 4 symbols resolved: yes / no / partial
- [ ] NIFTYBEES data available: yes / no (ETF vs index)
- [ ] Batch latency total: ___ms
- [ ] Per-symbol latency estimate: ___ms
- [ ] Any symbols that failed and why: ___

---

## Phase 6 — Streaming Viability

**Prompt to Codex:**
```
I want to test whether streaming is useful for regime detection on a daily chart.

1. Run: stream values for 10 seconds on NIFTY 1D. Return what arrives in the stream —
   how frequently do updates come? What fields update?
2. Run: stream tables for 10 seconds. Does the Pine Script table output stream as new rows arrive,
   or only when the bar closes?
3. On a 1D chart, does streaming serve any purpose — or does data only change at market open
   and bar close?
```

**What we are probing:**
- Streaming is relevant for intraday — is it useless on daily charts?
- Does the table stream fire on indicator recalculation or only on bar confirm?

**Record:**
- [ ] Stream values update frequency on 1D: ___
- [ ] Stream tables update frequency on 1D: ___
- [ ] Any real-time indicator recalculations on 1D (outside market hours): yes / no
- [ ] Conclusion — is streaming useful for daily regime work: yes / no / intraday only

---

## Phase 7 — Screenshot as Fallback Channel

**Prompt to Codex:**
```
Take a screenshot of the strategy_tester region.
Then take a screenshot of the full chart.

For each screenshot:
1. Can you read the text in the strategy tester results panel from the screenshot?
2. What P&L, trade count, win rate, and max drawdown values are visible?
3. Is screenshot a viable fallback for extracting backtest results when data_get_pine_tables
   cannot capture strategy tester output?
```

**What we are probing:**
- Strategy tester results are NOT accessible via `data_get_pine_tables` (it only reads indicator
  output, not the built-in strategy tester panel). Screenshot + vision is the fallback.
- Is the screenshot quality sufficient for reliable OCR/vision extraction?

**Record:**
- [ ] Screenshot region "strategy_tester" works: yes / no
- [ ] Values readable from screenshot: yes / no
- [ ] This is a viable data extraction path: yes / no / partial

---

## Summary Matrix (fill after all phases)

| Data Type | Tool | Works | Format | Depth/Fidelity | Notes |
|---|---|---|---|---|---|
| Current OHLCV | quote_get | | | current bar only | |
| Historical OHLCV | data_get_ohlcv | | | N bars | |
| Built-in indicator (current) | data_get_study_values | | | current bar | |
| Built-in indicator (history) | data_get_study_values | | | ? bars | |
| Custom Pine output | data_get_pine_tables | | | current bar | |
| Price levels | data_get_pine_lines | | | all on chart | |
| Text annotations | data_get_pine_labels | | | all on chart | |
| India VIX (direct) | quote_get (tab switch) | | | current bar | |
| India VIX (embedded) | request.security + table | | | current bar | |
| Multi-symbol snapshot | batch_run | | | current bar | |
| Strategy tester results | capture_screenshot | | | visible panel | |
| Streaming on daily | stream values/tables | | | tick/bar | |

---

## Key Questions This Framework Answers

After running all phases, you will know:

1. **Can the MCP read regime signals from a Pine Script table reliably?** (Phase 3 — the critical one)
2. **What is the maximum historical bar depth for NIFTY?** (Phase 1)
3. **Is VIX readable without a tab switch?** (Phase 4)
4. **Can a single batch call produce a multi-instrument regime snapshot?** (Phase 5)
5. **Is streaming relevant for daily regime work or only intraday?** (Phase 6)
6. **Is screenshot extraction a viable fallback for strategy tester data?** (Phase 7)

These answers directly determine the architecture of the regime classifier pipeline in NiftyShield.
