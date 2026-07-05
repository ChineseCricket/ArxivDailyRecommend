# arXiv Daily Briefing — Classification Model Choice

## Problem

The arXiv daily briefing script classifies 150+ papers through an LLM proxy.
Choosing the right model is non-trivial — what works for a probe ("Say ok") fails
for structured JSON classification tasks.

## Model Behavior (v5 proxy, 2026-06-24)

| Model | Latency | JSON Reliability | Suitability |
|-------|---------|-----------------|-------------|
| nim-small | ~0.6s | ❌ ~17% malformed JSON | Too unreliable for classification |
| nim-large | ~0.8s | ❌ occasional bad JSON | Fast but inconsistent on structured output |
| nim-fusion | ~11.7s | ✅ reliable (fan-out+judge) | Correct but 35+ min for 150 papers |
| DeepSeek | ~15s | ✅ reliable | Fast and reliable but paid |

## Recommended Config

For 150+ paper daily classification, the ONLY viable proxy-free approach is the
script's own fallback chain. The script's `_demoted` mechanism auto-skips
endpoints that produce malformed JSON, so the chain naturally converges on the
fastest reliable model:

```python
LLM_ENDPOINTS = [
    {"name": "nim-large",  "model": "nim-large"},   # fast, usually ok
    {"name": "nim-fusion", "model": "nim-fusion"},   # reliable fallback
    {"name": "DeepSeek",   "model": "deepseek-v4-pro"},  # paid last-resort
]
```

**Order matters**: nim-large first (fast, most batches succeed) → nim-fusion
(if large produced bad JSON on a batch) → DeepSeek (if proxy is down).

## What NOT to do

- Don't use nim-small for classification (malformed JSON wastes time on retries)
- Don't make nim-fusion the primary (11.7s × 13 batches = 2.5min minimum, often 35min+)
- Don't run with --cron in the background thinking it'll finish fast
- Use --force for manual re-runs to bypass the schedule window check

## --force vs --cron

- `--cron`: Respects schedule window (if past 15:00, skips with "try tomorrow")
- `--force`: Ignores schedule. Use for 补发 (resend) and manual re-runs.

## Timeout

The cron terminal command has a 600s timeout. With nim-fusion as primary,
this is often insufficient for 150 papers. The fallback chain must converge
quickly to avoid hitting the wall.
