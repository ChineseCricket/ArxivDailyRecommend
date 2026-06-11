# 2026-06-03 Network Outage — Diagnostic Record

## Summary

All LLM endpoints experienced severe timeouts from the server, preventing the arXiv daily briefing from being generated with proper classification.

## Endpoint Status

| Endpoint | Status | Details |
|----------|--------|---------|
| DeepSeek (`api.deepseek.com`) | 🔑 Key invalid | `sk-f3ce4ddf819644b7a77e3d6eec59ba` returns `"Authentication Fails"`. Script gets "timed out" (not auth error — server drops silently). |
| z.ai (`open.bigmodel.cn`) | ⏱️ Times out on batches | Small curl works (<200 chars). Batch prompts (8-10K tokens, 12 papers) time out at both 30s and 60s. Only 1/9 batches succeeded in one attempt. |
| Waterfall Proxy (`localhost:18900`) | 🔌 Likely not running | Consistently "timed out" in 30s. Proxy log shows last activity at 23:26. |

## Paper Count

- 103 total papers (102 astro-ph, 1 physics.ins-det, 0 cond-mat.supr-con)
- 9 batches of 12 (last batch: 7 papers)
- RSS feed date: 2026-06-02 12:00 Beijing

## Attempts

### Attempt 1: Default multi-endpoint (original script, --cron)
- Result: Timed out at 600s
- Progress: Reached batch 7/9
- All endpoints failed for batches 1,2,4,5,6; batch 3 succeeded via proxy (odd)
- No briefing generated (killed before print)

### Attempt 2: z.ai only, 60s timeout (patched script, --force --cron)
- Result: Timed out at 557s  
- Progress: All 9 batches attempted
- 8/9 batches failed with "The read operation timed out"; only batch 9 (7 papers) succeeded
- Briefing generated (10 papers) but with mostly Tier-4 defaults from failed batches

### Attempt 3: Skip LLM, Tier-4 only (patched script, --force)
- Result: Completed in ~18s
- All 103 papers assigned Tier-4 defaults
- Briefing: 10 papers, no domain matching, truncated summaries ("标题：...")
- Quality too low to deliver

## Patches Applied (and Reverted)

### Patch A: Tier-4-only fallback
Replace the LLM batch loop in `main()` with:
```python
# LLM analysis in batches — SKIPPED due to network issues, all Tier-4
batch_size = 12
all_analyses = []
total_batches = (len(new_papers) + batch_size - 1) // batch_size

print(f"  ⚠️ Network issue detected — skipping LLM classification, all papers Tier-4", file=sys.stderr)
for j, p in enumerate(new_papers):
    all_analyses.append((p, {
        'tier': 'Tier-4',
        'relevance': {d['name']: 0 for d in INTEREST_DOMAINS},
        'summary_cn': f"标题：{p['title'][:80]}",
    }))
```
**When to use:** All endpoints unreachable, need *any* output within 600s.

### Patch B: z.ai-only with 60s timeout
Replace the `classify_batch()` body with:
```python
# Try z.ai only (confirmed working today) with 60s timeout
endpoint = LLM_ENDPOINTS[1]  # z.ai GLM-5-turbo
payload = {
    "model": endpoint["model"],
    "messages": messages,
    "stream": False,
    "temperature": 0.2,
}
headers = {"Content-Type": "application/json"}
if endpoint.get("key"):
    headers["Authorization"] = f"Bearer {endpoint['key']}"

req = urllib.request.Request(
    endpoint["url"],
    data=json.dumps(payload).encode("utf-8"),
    headers=headers,
    method="POST"
)

try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    content = result['choices'][0]['message']['content'].strip()
    for prefix in ("```json", "```"):
        if content.startswith(prefix):
            content = content.split("\n", 1)[1] if "\n" in content else content[len(prefix):]
    if content.endswith("```"):
        content = content.rsplit("```", 1)[0]
    parsed = json.loads(content.strip())
    print(f"    → {endpoint['name']} OK", file=sys.stderr)
    return parsed
except Exception as e:
    print(f"    → {endpoint['name']} failed: {e}", file=sys.stderr)
    return None
```
**When to use:** z.ai is confirmed working for small requests, proxy and DeepSeek both down.

## DeepSeek Key Verification
```bash
curl -s --max-time 10 "https://api.deepseek.com/v1/models" \
  -H "Authorization: Bearer sk-f3ce4ddf819644b7a77e3d6eec59ba" | head -c 200
# Returns: {"error":{"message":"Authentication Fails, Your api key: ****59ba is invalid"...}}
```

## Root Causes Identified
1. **DeepSeek API key expired** — hardcoded fallback in script is stale
2. **z.ai batch sensitivity** — works for small prompts, times out on large batch prompts during peak hours
3. **Classify_batch iteration bug** — z.ai gets skipped on batch 1 when proxy is demoted (see SKILL.md Known Issues)
4. **600s subagent timeout** — script's worst-case runtime (810s) exceeds this
