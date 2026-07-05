# arXiv Briefing — NIM Fusion Proxy Timeout (2026-06-23)

## Symptom

Every `classify_batch()` call times out at 60 s when using the LLM Waterfall Proxy
(`nim-fusion` via `localhost:18900`). The nvidia-model-probe, which runs at 07:00,
reports nim-fusion as healthy (1.91 s), so this looks like a contradiction.

## Root cause: fusion mode payload-size mismatch

`nim-fusion` uses the proxy's **fusion mode**, which fans one request out to 4
backend models in parallel, then runs a judge to select the best answer.

| Payload | Input tokens | nim-fusion elapsed | Result |
|---------|-------------|-------------------|--------|
| Probe ("Say ok") | ~3 | 1.91 s (at 07:00) | ✅ OK |
| A single batch (12 papers, full abstracts) | ~5000 | >60 s | ❌ timeout |

The probe correctly measures that nim-fusion *responds* for trivial loads, but
"healthy for 3 tokens" does not imply "fast enough for 5000 tokens." The fusion
pipeline sends 4 copies of the 5000-token prompt to different backends, waits
for all of them (or `fusion_min_valid=2`), then runs a judge. If even ONE backend
model is slow or unresponsive, the entire pipeline stalls past 60 s.

Time-of-day also matters: the probe runs at 07:00 when the proxy is fresh.
By 12:00–15:00 (when arxiv cron fires), backend health may have degraded.

## Direct model vs fusion

```
nim-large (direct):    request → single backend → 2.5 s (even at 23:00)
nim-fusion (fusion):   request → 4 backends + judge → 60+ s timeout
```

Direct virtual models (`nim-large`, `nim-small`) route to a single backend
and are consistently fast. Only fusion mode has the multi-model coordination
overhead that makes it fragile.

## Fix applied: endpoint demotion (script v1.3.0)

The arxiv script already has a DeepSeek fallback. The v1.3.0 demotion fix
ensures the proxy is only tried ONCE per run:

```python
# Module-level flag
_proxy_demoted = False

# At the top of classify_batch(), before the endpoint loop:
if _proxy_demoted and _endpoint_order[0] == 0:
    _endpoint_order[:] = [1, 0]  # DeepSeek first from now on

# In the exception handler:
except Exception as e:
    if ep_idx == 0:
        _proxy_demoted = True
```

This saves ~12 minutes of wasted timeout waiting when the proxy is broken.

Key design constraint: the demotion must happen BEFORE the for loop, not inside
it. Modifying `_endpoint_order` mid-iteration causes Python's for-loop iterator
to re-visit the same index (e.g., `[0,1]` → set `[:] = [1,0]` → position 1 is
now `0` → tries proxy again).

## Verification

```bash
# Check if nim-fusion is currently responsive (small payload)
curl -s --max-time 30 http://localhost:18900/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"nim-fusion","messages":[{"role":"user","content":"Say ok"}],"max_tokens":10,"stream":false,"temperature":0}'

# Check if a direct model works (usually fast)
curl -s --max-time 10 http://localhost:18900/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"nim-large","messages":[{"role":"user","content":"Say ok"}],"max_tokens":10,"stream":false,"temperature":0}'
```

## Future improvements

If the user wants to use the proxy for arxiv classification, switch from
`nim-fusion` (fusion mode → 4x overhead) to `nim-large` (direct → 1 backend).
The DeepSeek fallback is already a good direct single-model path.
