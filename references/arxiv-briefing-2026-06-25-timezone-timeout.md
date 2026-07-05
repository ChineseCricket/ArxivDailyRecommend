# arXiv Briefing Failure — 2026-06-25: Timezone + Timeout

## Symptom

Cron job (10:00–15:00 hourly) repeatedly claimed "arXiv今日数据尚未更新" and
"已过15:00，arXiv始终未更新", despite new papers being available on arXiv.

## Root Causes (two independent failures)

### 1. `is_feed_today()` strict comparison fails for morning runs

arXiv RSS `<pubDate>` uses US-Eastern timezone (midnight ET = 12:00 Beijing).
The script's `is_feed_today()` used STRICT equality:

```python
is_today = feed_dt.date() == now_beijing.date()
```

At 10:00 Beijing, pubDate still shows yesterday's ET date:
- RSS pubDate: `"Wed, 24 Jun 2026 00:00:00 -0400"`
- → Beijing: `2026-06-24 12:00` → date = `06-24`
- `now_beijing.date() = 06-25`
- `06-24 == 06-25` → **False** → "arXiv今日数据尚未更新"

This is correct behavior until 12:00, but the old 1-day tolerance
(`>= now - 1 day`) had been removed in a prior fix for stale weekend feeds.

**Fix**: Change to 0–1 day tolerance (rejects feeds older than 1 day):

```python
age_days = (now_beijing.date() - feed_dt.date()).days
is_today = 0 <= age_days <= 1
```

File: `scripts/arxiv_daily_briefing.py`, function `is_feed_today()`.

### 2. Script timeout (120s) kills full pipeline

At ~12:00 Beijing, pubDate flips to today's ET date and `is_feed_today()`
returns True. The full pipeline starts: fetch papers → LLM classification
(10+ batches × 30s each ≈ 300–600s). But the cron scheduler's script
timeout defaults to **120 seconds**, killing the process before it finishes.

This happened at 12:02, 13:02, and 14:02 on June 25 — three consecutive
timeouts with no user-visible output.

**Fix**: Increase script timeout to 600s:

```bash
hermes config set cron.script_timeout_seconds 600
```

This is read by `_get_script_timeout()` in `cron/scheduler.py`.

## June 25 Timeline

| Time    | Event |
|---------|-------|
| 10:00   | `is_feed_today()` returns False (pubDate = Jun 24 ET). ⏳ "尚未更新" delivered. |
| 11:00   | Same. ⏳ "尚未更新" delivered. |
| 12:02   | pubDate flips to Jun 25 ET. Pipeline starts. **Timeout after 120s — no output.** |
| 13:02   | Pipeline starts again. **Timeout after 120s — no output.** |
| 14:02   | Pipeline starts again. **Timeout after 120s — no output.** |
| 15:00   | Cutoff logic triggers. ⚠️ "已过15:00，始终未更新" delivered. |

## Verification

```bash
# Test is_feed_today() with new logic
python3 -c "
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta
import urllib.request, xml.etree.ElementTree as ET

BEIJING_TZ = timezone(timedelta(hours=8))
xml_data = urllib.request.urlopen('https://rss.arxiv.org/rss/astro-ph', timeout=30).read()
root = ET.fromstring(xml_data)
pub = root.find('.//pubDate')
dt = parsedate_to_datetime(pub.text.strip())
feed_dt = dt.astimezone(BEIJING_TZ)
now_bj = datetime.now(BEIJING_TZ)
age = (now_bj.date() - feed_dt.date()).days
print(f'feed={feed_dt.date()} now={now_bj.date()} age={age} accept={0 <= age <= 1}')
"

# Verify config
hermes config get cron.script_timeout_seconds
```
