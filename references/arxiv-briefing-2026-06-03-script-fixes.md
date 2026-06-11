# 2026-06-03 Arxiv Script Fixes

## Context

Arxiv cron (job `40e756c061e9`) failed all 4 hourly runs today (12:00–15:00 Beijing) because DeepSeek API key had zero balance (HTTP 402 Insufficient Balance). The cron agent itself couldn't make LLM calls, so the arxiv script was never executed.

Manual re-run also failed: all 7 batches timed out because:
1. Proxy (NIM) was down → 60s wasted per batch
2. z.ai GLM-5-turbo timed out on batch prompts → 60s wasted
3. DeepSeek was occasionally 502 → more wasted time
4. Iteration bug: `_endpoint_order.remove()+append()` in-place modification caused z.ai to be SKIPPED when proxy was demoted

## Fixes Applied

### 1. Iteration Bug (UnboundLocalError + index skipping)
**Before:**
```python
_proxy_demoted = False  # module-level

for ep_idx in _endpoint_order:
    ...
    if ep_idx == 0 and not _proxy_demoted:
        _endpoint_order.remove(ep_idx)   # in-place, shifts indices
        _endpoint_order.append(ep_idx)
        _proxy_demoted = True            # UnboundLocalError — no 'global'
```

**After:**
```python
_first_demoted = False  # module-level

global _first_demoted, _endpoint_order   # fix UnboundLocalError
for ep_idx in _endpoint_order:
    ...
    if ep_idx == 0 and not _first_demoted:
        _endpoint_order = _endpoint_order[1:] + [0]  # new list, no index shift
        _first_demoted = True
        print(f"    → {endpoint['name']} demoted to last priority")
```

### 2. Endpoint Order (user directive)
User wants proxy FIRST because NIM tokens are free. Order: Proxy → DeepSeek → z.ai.

- **NIM alive day**: Proxy wins all batches (free!)
- **NIM dead day**: Batch 1 wastes 60s (proxy timeout), then DeepSeek handles remaining 6 batches at 11-55s each. z.ai is last because it consistently times out on 8-10K token batch prompts.

### 3. Timeout: 30s → 60s
DeepSeek batch prompts can be slow (observed 55s during peak). 30s was cutting off valid responses.

### 4. Generic Demotion
No longer hardcodes "Proxy" — works with any first endpoint.

## Endpoint Health (2026-06-03)
| Endpoint | Status | Latency |
|----------|--------|---------|
| Waterfall Proxy (NIM) | ❌ HTTP 502 | Dead |
| DeepSeek v4-pro | ✅ | 11-55s/batch |
| z.ai GLM-5-turbo | ⚠️ | Timeout on batch prompts, OK on small reqs |
