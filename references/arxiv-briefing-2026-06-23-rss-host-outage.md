# arXiv Briefing Incident — 2026-06-22/23 RSS Host Outage

## Timeline

| Date | Hour | Outcome | Message |
|------|------|---------|---------|
| Mon 6/22 | 10:00–11:00 | ⏳ Retrying | `RSS日期：2026-06-21` — feed not yet today |
| Mon 6/22 | 12:00–14:00 | ⚠️ Empty spam | Feed recognized as today (pubDate=06-22) but 0 items. `⚠️ RSS已更新但未找到新论文，可能数据异常` × 3 |
| Mon 6/22 | 15:00 | [SILENT] | Past cutoff, retry_state `done=true` |
| Tue 6/23 | 10:00–11:00 | ⏳ Retrying | `RSS日期：2026-06-22` — feed not yet today |
| Tue 6/23 | 12:00–14:00 | ⚠️ Empty spam | Same pattern as Monday. `⚠️ … 可能数据异常` × 3 |
| Tue 6/23 | 15:06 | ⚠️ Final | `⚠️ 今天已过15:00，arXiv始终未更新。明天再试。` |

## Root Cause

`export.arxiv.org/rss/<category>` returned a well-formed RSS channel skeleton (904 bytes) with correct `pubDate` and `lastBuildDate`, but **zero `<item>` elements**. The listing pages (`arxiv.org/list/<cat>/new`) and the API (`export.arxiv.org/api/query`) had normal paper counts — astro-ph had 154 new submissions on Tuesday, physics.ins-det had 9 new.

Meanwhile, `rss.arxiv.org/rss/<category>` worked correctly throughout the outage, returning 293 items for astro-ph. The script only used `export.arxiv.org`, so it saw zero papers.

## Diagnosis

Verified with:

```bash
# Broken — 0 items
curl -s 'https://export.arxiv.org/rss/astro-ph' | grep -c '<item'

# Working — 293 items  
curl -s 'https://rss.arxiv.org/rss/astro-ph' | grep -c '<item'
```

Both hosts returned the same `pubDate` (Tue, 23 Jun 2026 00:00:00 -0400), confirming the outage was a content sync issue on the `export` front-end, not a date-routing problem.

## User Impact

- **12 WeChat push notifications** over 2 days (6 per day — 10/11 status + 12/13/14 empty + 15 cutoff)
- No actual briefing delivered either day
- Messages sounded alarmist (`可能数据异常` = "possibly data anomaly") when the real issue was a front-end sync gap
- User correctly noted Monday 6/22 genuinely had no arXiv new submissions (post-Juneteenth holiday), but Tuesday 6/23 had 154 new papers that were missed

## Fix Applied (v1.3.0)

1. **Multi-host RSS fallback**: `fetch_rss_feed()` tries `rss.arxiv.org` first, falls back to `export.arxiv.org`
2. **Empty-feed notify-once**: Notifies user ONCE when both hosts return empty, then stays silent for the rest of the day
3. **LLM endpoint demotion**: Proxy failure on batch 1 demotes it from the queue, subsequent batches skip the 60 s timeout

## Follow-up Fix (v1.3.1, same day)

After the RSS fix, the補发 run revealed that nim-fusion was timing out on every
batch (proxy alive but fusion pipeline too slow for 60s client timeout). This was
a separate issue from the RSS outage. The proxy fusion timeout analysis is
documented separately at `references/arxiv-briefing-2026-06-23-proxy-fusion-timeout.md`.
Summary: timeout 60s→300s for proxy endpoints, nim-large added as free
intermediate fallback before paid DeepSeek.

## Commands

```bash
# Verify RSS is working across hosts
for host in rss.arxiv.org export.arxiv.org; do
  for cat in astro-ph physics.ins-det cond-mat.supr-con; do
    echo -n "$host/$cat: "
    curl -s "https://$host/rss/$cat" | grep -c '<item>'
  done
done

# Tuesday補發 (run after fix)
~/.hermes/hermes-agent/venv/bin/python3 -u ~/.hermes/skills/research/arxiv/scripts/arxiv_daily_briefing.py --force
```
