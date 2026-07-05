# arXiv Cron Cumulative Timeout — 2026-07-02

## Symptom

Two consecutive cron runs (10:10, 11:10 Beijing) both fail with:
```
Script timed out after 600s: /home/admin/.hermes/scripts/arxiv_cron_wrapper.sh
```

No partial output — the script is killed mid-LLM-classification.

## Root Cause

NOT a single-batch timeout. Cumulative LLM batch latency exceeds 600s when NIM proxy
backends are intermittently slow. With 11 batches × 12 papers each (128 papers total),
even average 50s/batch → 550s total, leaving almost zero headroom. One slow batch (100s+)
pushes it over.

### Evidence from proxy logs

```bash
# Analyze proxy latency distribution during the affected window
python3 -c "
import json
from datetime import datetime, timezone
cutoff = datetime(2026,7,2,11,41,0, tzinfo=timezone.utc)
large_times = []
fusion_times = []
with open('/home/admin/.hermes/llm-proxy-v5/logs/requests.jsonl') as f:
    for line in f:
        d = json.loads(line.strip())
        if d.get('ts','') < '2026-07-02T11:41':
            continue
        vm = d.get('virtual_model','')
        lat = d.get('latency_ms', 0)
        if 'large' in vm:
            large_times.append(lat)
        elif 'fusion' in vm:
            fusion_times.append(lat)
if large_times:
    import statistics
    print(f'nim-large: {len(large_times)} calls, median={statistics.median(large_times):.0f}ms, max={max(large_times):.0f}ms, p90={sorted(large_times)[int(len(large_times)*0.9)]:.0f}ms')
if fusion_times:
    import statistics
    print(f'nim-fusion: {len(fusion_times)} calls, median={statistics.median(fusion_times):.0f}ms, max={max(fusion_times):.0f}ms')
print(f'Total LLM calls: {len(large_times)+len(fusion_times)} (target: 11 batches)')
"
```

Sample output from affected run:

| Batch | Model | Latency | Winner |
|-------|-------|---------|--------|
| 1 | nim-large | 38.5s | kimi |
| 2 | nim-large | 24.2s | kimi |
| 3 | nim-large | 19.7s | kimi |
| 4 | nim-large | 55.2s | kimi |
| 5 | nim-fusion | 37.9s | kimi |
| 6 | nim-fusion | 135.7s | ds-pro |

- nim-large batches: 20-55s (reasonable)
- nim-fusion batches: 38-136s (slow, especially ds-pro winner)
- 6 batches consumed ~311s; 5 more would add ~250-400s → total 560-710s

The nim-fusion fallback happens when nim-large produces malformed JSON.
nim-fusion's fan-out+judge pipeline inherently takes longer, and when the
judge backend (ds-pro) is slow, a single nim-fusion batch can consume 2+ minutes.

### Why previous days succeeded

NIM backend latency is intermittent. July 1 (10:09) completed normally.
July 2 morning backends (kimi, ds-pro) were slower than usual.

## Diagnostic Checklist

1. **Confirm it's cumulative, not single-batch**: check proxy logs for latency-per-batch
2. **Check nim-large JSON failure rate**: if >2 batches fail, nim-fusion fallback adds
   60-140s per failed batch
3. **Check proxy backend health**: which backend (kimi, ds-pro, minimax) is the winner?
   Slow winners (ds-pro at 135s) are the culprit
4. **Count total batches**: 128 papers / 12 = 11 batches. At 50s/batch = 550s minimum

## Fix

Increase `cron.script_timeout_seconds` to 900s:
```bash
hermes config set cron.script_timeout_seconds 900
```

This provides 15 minutes for the pipeline — enough for 11 batches at 60-80s average.

### Alternative (not implemented)

Reduce per-batch LLM timeout from 300s to 120s for proxy endpoints. This would cause
faster fallback to DeepSeek when nim-large is slow, but increases API costs.

## Quick Check Command

```bash
# Is the proxy slow right now?
python3 -c "
import json, statistics
with open('/home/admin/.hermes/llm-proxy-v5/logs/requests.jsonl') as f:
    lines = [json.loads(l) for l in f.readlines()[-20:]]
lats = [l['latency_ms'] for l in lines if 'latency_ms' in l]
print(f'Last {len(lats)} requests: median={statistics.median(lats):.0f}ms, max={max(lats):.0f}ms')
"
```
