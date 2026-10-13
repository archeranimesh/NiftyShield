
# Telegram Message Caption-Fit Audit — prompt

> Read-only audit: inventory every Telegram message NiftyShield sends and measure how many fit a single photo-with-caption message (the TM Trading "image + caption" layout). No implementation.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

Today the payoff chart is sent as a separate photo (`send_payoff_chart`, no caption) next to a text message sent via `TelegramNotifier.send()`. Animesh wants one message: chart on top, text
underneath, like the reference screenshot of a TM Trading update. Telegram's `sendPhoto` caption is capped at 1024 characters after entity parsing (text messages: 4096), and an over-limit caption
rejects the whole photo. Before changing any call site we need to know, per message type, how many actually fit, so the follow-up implementation story is sized and designed on evidence.

## Scope guard

Findings only. No edits under `src/`, `scripts/` or `tests/`. No real Telegram calls, no network, no real DB. Measurement uses existing formatters fed with fixtures or recorded outputs, via a
`scratch/` script per `SCRATCH.md` if one is needed. The only artifact committed is `docs/plan/telegram-caption-audit/findings.md` plus the story's own docs. Recommendations go in the findings; the
implementation story is authored separately after Animesh reviews them.

## Design review

No new module, class or seam in this story. The follow-up implementation story must run `docs/refactor/design-principles.md` triggers (likely a caption-builder seam and a text-fallback policy).

## Session-start load hints

`src/notifications/CLAUDE.md` (formatting and escaping contract), `FORMATTING.md` (MarkdownV2 escaping boundary), `src/notifications/telegram.py` (`send`, `send_photo`), `telegram_gateway.py`,
`payoff_chart.py` (`send_payoff_chart`). Call sites already known: `scripts/strategies/ic/paper_ic_snapshot.py`, `paper_ic_entry.py`, `paper_ic_entry_v2.py`, `src/strategy/ic_nifty_v1.py`,
`ic_nifty_v2.py`. Find the rest with `search_code` on `notifier.send`, `gateway.send`, `send_message`.

## Task overview

TCA-1 inventories every Telegram message type and its sender. TCA-2 measures rendered length of each against the 1024 and 4096 limits, on escaped MarkdownV2 text. TCA-3 classifies each type (fits as
caption / fits with trimming / needs split) and writes recommendations.

## Definition of done

`findings.md` exists with a table covering every message type: trigger, source file, has chart today (Y/N), measured length (min/typical/max), verdict, and a recommended layout. It states the count
that fit as-is, the count that fit with trimming, and the count that need a photo-plus-follow-up split. No source file changed.

## Perspectives not covered

Telegram client rendering differences (mobile vs desktop caption truncation in previews), message-edit and reply-thread behaviour, rate limits when a photo and a follow-up are sent back to back, and
whether a caption's MarkdownV2 escaping inflates length enough to cross the limit on real strike and symbol strings.
