# arXiv Briefing — Proxy Fusion Timeout Analysis (2026-06-23)

## Symptom

The nvidia-model-probe (cron at 07:00) reported nim-fusion healthy (1.91s response).
But the arXiv briefing script (cron at 10:00-15:00) got `timed out` on every batch,
causing full fallback to paid DeepSeek for all 13 batches.

## Root Cause: Client Timeout vs Fusion Pipeline Latency

The script used `timeout=60s` for all LLM calls. This was designed for the old
hedge mode but is too short for nim-fusion's pipeline:

```
nim-fusion pipeline for one batch:
  t=0s      Fan out 4 models simultaneously (kimi, ds-pro, glm5, minimax-m3)
  t=10-30s  First model answers (e.g. kimi in ~10s)
  t=20-40s  Second model answers → fusion_min_valid=2 reached → trigger judge
  t=25-45s  Judge dispatched (one of the same 4 models, separate call)
  t=40-70s  Judge returns → winner selected → response sent to client
             ↑ 60s client timeout fires HERE, killing the connection
```

For 12-paper batches with long abstracts, each model call takes 15-40s.
The fan-out + judge pipeline easily reaches 60-90s. The 60s client timeout
was killing fusion before it could deliver.

## Key Finding: fusion_min_valid Already Works

Config already had `fusion_min_valid: 2` — fusion enters the judge phase
after just 2 distinct models return valid answers. It does NOT wait for
all 4 models. The bottleneck was purely the client-side timeout being
shorter than the pipeline latency.

## Key Finding: Probe vs Production Load Mismatch

The nvidia-model-probe sends `"Say ok"` (3 tokens, max_tokens=5). This is
~1-2s for any model. It measures whether the proxy process is alive and
can route — NOT whether fusion can complete a heavy classification task
within 60s.

The probe is healthy at 07:00, but by 12:00 one of the 4 backend models
may have degraded, adding latency to the fan-out phase. The probe gives
no visibility into this.

## Key Finding: Key Rotation (Round-Robin, Not Immediate Retry)

The proxy has `NVIDIA_API_KEY_1` and `NVIDIA_API_KEY_2`. `router_state.select_key()`
uses round-robin: calls alternate KEY_1 → KEY_2 → KEY_1...

If a call to KEY_1 fails (429, auth error), the proxy does NOT immediately
retry with KEY_2. The failed model's lane waits `fusion_retry_interval_seconds`
(60s) before re-firing, at which point round-robin picks the other key.
So there IS cross-key retry, but with up to 60s delay.

## Fix Applied (v1.3.1)

```python
# Before: single timeout for all endpoints
with urllib.request.urlopen(req, timeout=60) as resp:

# After: per-endpoint timeouts
call_timeout = 300 if ep_idx < 2 else 90  # proxy=300s, deepseek=90s
with urllib.request.urlopen(req, timeout=call_timeout) as resp:
```

Plus nim-large added as intermediate fallback between nim-fusion and DeepSeek.
nim-large uses staggered hedge mode (first valid answer wins, no judge) —
faster and more resilient to individual model failures than fusion.

## Proxy Architecture Quick Reference

```
                    ┌─ nim-fusion (quality): 4 models fan-out → judge selects best
proxy :18900 ───────┼─ nim-large  (hedge):    4 models staggered, first valid wins
                    └─ nim-small  (fast):     same as large but 180s hard cutoff

Backend tier "large": kimi-k2.6, deepseek-v4-pro, glm-5.1, minimax-m3
  - Shared across all virtual models
  - Round-robin key rotation across 2 NIM API keys
  - Health-score ranking (last 30 min) for dispatch ordering

Config: ~/.hermes/llm-proxy-v5/config.yaml
Code:   ~/.hermes/llm-proxy-v5/app/fusion.py (fusion mode)
        ~/.hermes/llm-proxy-v5/app/hedger.py (hedge mode + key selection)
        ~/.hermes/llm-proxy-v5/app/router.py (round-robin key rotation)
```

## Diagnostic Commands

```bash
# Test fusion directly (see if it's the script timeout or a real outage)
time curl -s --max-time 300 http://localhost:18900/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"nim-fusion","messages":[{"role":"user","content":"Say ok"}],"stream":false}' \
  | python3 -m json.tool

# Test nim-large (hedge mode — should be faster)
time curl -s --max-time 60 http://localhost:18900/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"nim-large","messages":[{"role":"user","content":"Say ok"}],"stream":false}' \
  | python3 -m json.tool

# Check which model responded (proxy returns the winning model in "model" field)
curl -s http://localhost:18900/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"nim-fusion","messages":[{"role":"user","content":"Say ok"}],"stream":false}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['model'])"

# Check probe history (does the probe agree with production behavior?)
tail -10 ~/.hermes/probe_history/model_probe_history.jsonl
```
