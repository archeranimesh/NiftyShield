# Far-Expiry Capture Findings

## FC-4 Cron and healthcheck (Animesh)

Date: 2026-10-10

Cron line installed on the Mac host crontab (Mon-Fri, 16:10 IST, after the 15:30 close and after the 16:00 `signal_eod`):

```
10 16 * * 1-5 cd $NS && $NSPY -m scripts.pipeline.capture_far_expiry_chain >> logs/far_expiry_capture.log 2>&1
```

Healthcheck: `scripts/healthcheck.py` `_check_far_expiry_capture` (`12e7ccb`) verifies the previous trading day's `capture_far_expiry` heartbeat is `SUCCESS`. It checks the previous day because the
15:55 healthcheck runs before the 16:10 capture. No heartbeat yet warns; a stale or failed heartbeat is critical.

Open: the first scheduled run is Monday 2026-10-12 and its heartbeat had not been observed when FC-4 was closed (closed on Animesh's instruction). Confirm `logs/far_expiry_capture.log` and a `SUCCESS`
`capture_far_expiry` row in `cron_heartbeats` after that run; the capture needs a fresh Dhan token that day.
