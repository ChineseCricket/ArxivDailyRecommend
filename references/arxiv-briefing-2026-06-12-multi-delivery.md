# arXiv Briefing — 2026-06-12 Multi-Delivery Incident

## Symptoms

User received 4+ different arXiv briefings on June 12 with:
- Papers from June 10 appearing in June 12 briefing
- Inconsistent formatting and paper selection across deliveries
- Varying editorial style (standard Tier format vs narrative style)

## Root Causes

### 1. Stale RSS feed accepted as "today"
`is_feed_today()` used `feed_date >= today - 1`, accepting feeds up to 2 days old. The 10:07 run fetched June 10's RSS (paper IDs 2606.099xx-2606.111xx) instead of June 12's new papers.

### 2. No cross-day dedup
`reported_ids` was per-date only. Papers reported on June 10 could be re-reported on June 12 because `reported_ids_2026-06-12.json` starts empty each day.

### 3. Terminal blocked → execute_code fallback → multi-delivery
When terminal was blocked in cron context, the agent fell back to `execute_code` manual classification. Each fallback run produced different results (different paper selection, different formatting, different tier assignments). 4 different briefings were delivered in one day.

### 4. `_proxy_demoted` undefined variable
Line 250 declared `global _endpoint_order, _proxy_demoted` but `_proxy_demoted` was never defined. The actual variable is `_first_demoted`. This caused no runtime error (Python creates the global on first assignment) but was a latent bug.

## Timeline (June 12)

| Time | Source | Papers | Style | Issue |
|------|--------|--------|-------|-------|
| 10:07 | Script (old RSS) | 26 (June 10 papers) | Standard Tier | Stale feed |
| 11:05 | Script → [SILENT] | 0 | — | retry_state done=true |
| 12:05 | execute_code fallback | 14 (June 12 papers) | Different format | Manual classification |
| 13:08 | execute_code fallback | 12 | Another format | Same |
| 14:03 | execute_code fallback | ? | ? | Same |
| 15:02 | execute_code fallback | 11 | Another format | Same |

## Fixes Applied (v1.2.0)

1. `is_feed_today()`: `feed_date >= today - 1` → `feed_date == today` (stricter)
2. Cross-day dedup: load past 7 days' `reported_ids_*.json` and union
3. Cron prompt: forbid execute_code fallback → deliver status message instead
4. Bug fix: `_proxy_demoted` → `_first_demoted`
5. LLM endpoint tracking: classify_batch returns (results, endpoint_name)
6. Briefing footer: `⚡ LLM分类: Waterfall Proxy X/Y批(Z%) · DeepSeek ...`

## Prevention

- `cron_mode: approve` in config.yaml should allow terminal execution
- If terminal is still blocked at runtime, the new cron prompt delivers a brief status message instead of falling back to manual classification
- Cross-day dedup prevents paper re-delivery even if RSS doesn't rotate
- Stricter date check prevents stale feeds
