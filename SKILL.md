---
name: arxiv
description: Search and retrieve academic papers from arXiv. Includes Arxiv Daily Recommend — personalized daily briefing for astrophysics and superconducting detector papers with LLM-powered classification.
version: 1.3.1
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Research, Arxiv, Papers, Academic, Science, API, Daily Briefing, Astrophysics]
    related_skills: [ocr-and-documents]
---

# arXiv Research & Arxiv Daily Recommend

Two-in-one skill: (1) General arXiv paper search API, and (2) Arxiv Daily Recommend — personalized daily briefing for astrophysics + superconducting detectors.

## 🚀 Arxiv Daily Recommend

Generates a personalized arXiv daily briefing covering astro-ph, physics.ins-det, and cond-mat.supr-con. Papers are classified into 4 importance tiers and scored against 5 interest domains with configurable weights.

```bash
# One command — generates today's briefing to stdout
python3 scripts/arxiv_daily_briefing.py --force
```

No dependencies beyond Python 3.8 stdlib. Uses RSS feeds for data, LLM for classification.

Full documentation: `references/daily-briefing.md`

---

## 📚 Paper Search API

## Quick Reference

| Action | Command |
|--------|---------|
| Search papers | `curl "https://export.arxiv.org/api/query?search_query=all:QUERY&max_results=5"` |
| Get specific paper | `curl "https://export.arxiv.org/api/query?id_list=2402.03300"` |
| Read abstract (web) | `web_extract(urls=["https://arxiv.org/abs/2402.03300"])` |
| Read full paper (PDF) | `web_extract(urls=["https://arxiv.org/pdf/2402.03300"])` |

## Searching Papers

The API returns Atom XML. Parse with `grep`/`sed` or pipe through `python3` for clean output.

### Basic search

```bash
curl -s "https://export.arxiv.org/api/query?search_query=all:GRPO+reinforcement+learning&max_results=5"
```

### Clean output (parse XML to readable format)

```bash
curl -s "https://export.arxiv.org/api/query?search_query=all:GRPO+reinforcement+learning&max_results=5&sortBy=submittedDate&sortOrder=descending" | python3 -c "
import sys, xml.etree.ElementTree as ET
ns = {'a': 'http://www.w3.org/2005/Atom'}
root = ET.parse(sys.stdin).getroot()
for i, entry in enumerate(root.findall('a:entry', ns)):
    title = entry.find('a:title', ns).text.strip().replace('\n', ' ')
    arxiv_id = entry.find('a:id', ns).text.strip().split('/abs/')[-1]
    published = entry.find('a:published', ns).text[:10]
    authors = ', '.join(a.find('a:name', ns).text for a in entry.findall('a:author', ns))
    summary = entry.find('a:summary', ns).text.strip()[:200]
    cats = ', '.join(c.get('term') for c in entry.findall('a:category', ns))
    print(f'{i+1}. [{arxiv_id}] {title}')
    print(f'   Authors: {authors}')
    print(f'   Published: {published} | Categories: {cats}')
    print(f'   Abstract: {summary}...')
    print(f'   PDF: https://arxiv.org/pdf/{arxiv_id}')
    print()
"
```

## Search Query Syntax

| Prefix | Searches | Example |
|--------|----------|---------|
| `all:` | All fields | `all:transformer+attention` |
| `ti:` | Title | `ti:large+language+models` |
| `au:` | Author | `au:vaswani` |
| `abs:` | Abstract | `abs:reinforcement+learning` |
| `cat:` | Category | `cat:cs.AI` |
| `co:` | Comment | `co:accepted+NeurIPS` |

### Boolean operators

```
# AND (default when using +)
search_query=all:transformer+attention

# OR
search_query=all:GPT+OR+all:BERT

# AND NOT
search_query=all:language+model+ANDNOT+all:vision

# Exact phrase
search_query=ti:"chain+of+thought"

# Combined
search_query=au:hinton+AND+cat:cs.LG
```

## Sort and Pagination

| Parameter | Options |
|-----------|---------|
| `sortBy` | `relevance`, `lastUpdatedDate`, `submittedDate` |
| `sortOrder` | `ascending`, `descending` |
| `start` | Result offset (0-based) |
| `max_results` | Number of results (default 10, max 30000) |

```bash
# Latest 10 papers in cs.AI
curl -s "https://export.arxiv.org/api/query?search_query=cat:cs.AI&sortBy=submittedDate&sortOrder=descending&max_results=10"
```

## Fetching Specific Papers

```bash
# By arXiv ID
curl -s "https://export.arxiv.org/api/query?id_list=2402.03300"

# Multiple papers
curl -s "https://export.arxiv.org/api/query?id_list=2402.03300,2401.12345,2403.00001"
```

## BibTeX Generation

After fetching metadata for a paper, generate a BibTeX entry:

{% raw %}
```bash
curl -s "https://export.arxiv.org/api/query?id_list=1706.03762" | python3 -c "
import sys, xml.etree.ElementTree as ET
ns = {'a': 'http://www.w3.org/2005/Atom', 'arxiv': 'http://arxiv.org/schemas/atom'}
root = ET.parse(sys.stdin).getroot()
entry = root.find('a:entry', ns)
if entry is None: sys.exit('Paper not found')
title = entry.find('a:title', ns).text.strip().replace('\n', ' ')
authors = ' and '.join(a.find('a:name', ns).text for a in entry.findall('a:author', ns))
year = entry.find('a:published', ns).text[:4]
raw_id = entry.find('a:id', ns).text.strip().split('/abs/')[-1]
cat = entry.find('arxiv:primary_category', ns)
primary = cat.get('term') if cat is not None else 'cs.LG'
last_name = entry.find('a:author', ns).find('a:name', ns).text.split()[-1]
print(f'@article{{{last_name}{year}_{raw_id.replace(\".\", \"\")},')
print(f'  title     = {{{title}}},')
print(f'  author    = {{{authors}}},')
print(f'  year      = {{{year}}},')
print(f'  eprint    = {{{raw_id}}},')
print(f'  archivePrefix = {{arXiv}},')
print(f'  primaryClass  = {{{primary}}},')
print(f'  url       = {{https://arxiv.org/abs/{raw_id}}}')
print('}')
"
```
{% endraw %}

## Reading Paper Content

After finding a paper, read it:

```
# Abstract page (fast, metadata + abstract)
web_extract(urls=["https://arxiv.org/abs/2402.03300"])

# Full paper (PDF → markdown via Firecrawl)
web_extract(urls=["https://arxiv.org/pdf/2402.03300"])
```

For local PDF processing, see the `ocr-and-documents` skill.

## Common Categories

| Category | Field |
|----------|-------|
| `cs.AI` | Artificial Intelligence |
| `cs.CL` | Computation and Language (NLP) |
| `cs.CV` | Computer Vision |
| `cs.LG` | Machine Learning |
| `cs.CR` | Cryptography and Security |
| `stat.ML` | Machine Learning (Statistics) |
| `math.OC` | Optimization and Control |
| `physics.comp-ph` | Computational Physics |

Full list: https://arxiv.org/category_taxonomy

## Helper Script

The `scripts/search_arxiv.py` script handles XML parsing and provides clean output:

```bash
python scripts/search_arxiv.py "GRPO reinforcement learning"
python scripts/search_arxiv.py "transformer attention" --max 10 --sort date
python scripts/search_arxiv.py --author "Yann LeCun" --max 5
python scripts/search_arxiv.py --category cs.AI --sort date
python scripts/search_arxiv.py --id 2402.03300
python scripts/search_arxiv.py --id 2402.03300,2401.12345
```

No dependencies — uses only Python stdlib.

---

## Semantic Scholar (Citations, Related Papers, Author Profiles)

arXiv doesn't provide citation data or recommendations. Use the **Semantic Scholar API** for that — free, no key needed for basic use (1 req/sec), returns JSON.

### Get paper details + citations

```bash
# By arXiv ID
curl -s "https://api.semanticscholar.org/graph/v1/paper/arXiv:2402.03300?fields=title,authors,citationCount,referenceCount,influentialCitationCount,year,abstract" | python3 -m json.tool

# By Semantic Scholar paper ID or DOI
curl -s "https://api.semanticscholar.org/graph/v1/paper/DOI:10.1234/example?fields=title,citationCount"
```

### Get citations OF a paper (who cited it)

```bash
curl -s "https://api.semanticscholar.org/graph/v1/paper/arXiv:2402.03300/citations?fields=title,authors,year,citationCount&limit=10" | python3 -m json.tool
```

### Get references FROM a paper (what it cites)

```bash
curl -s "https://api.semanticscholar.org/graph/v1/paper/arXiv:2402.03300/references?fields=title,authors,year,citationCount&limit=10" | python3 -m json.tool
```

### Search papers (alternative to arXiv search, returns JSON)

```bash
curl -s "https://api.semanticscholar.org/graph/v1/paper/search?query=GRPO+reinforcement+learning&limit=5&fields=title,authors,year,citationCount,externalIds" | python3 -m json.tool
```

### Get paper recommendations

```bash
curl -s -X POST "https://api.semanticscholar.org/recommendations/v1/papers/" \
  -H "Content-Type: application/json" \
  -d '{"positivePaperIds": ["arXiv:2402.03300"], "negativePaperIds": []}' | python3 -m json.tool
```

### Author profile

```bash
curl -s "https://api.semanticscholar.org/graph/v1/author/search?query=Yann+LeCun&fields=name,hIndex,citationCount,paperCount" | python3 -m json.tool
```

### Useful Semantic Scholar fields

`title`, `authors`, `year`, `abstract`, `citationCount`, `referenceCount`, `influentialCitationCount`, `isOpenAccess`, `openAccessPdf`, `fieldsOfStudy`, `publicationVenue`, `externalIds` (contains arXiv ID, DOI, etc.)

---

## Complete Research Workflow

1. **Discover**: `python scripts/search_arxiv.py "your topic" --sort date --max 10`
2. **Assess impact**: `curl -s "https://api.semanticscholar.org/graph/v1/paper/arXiv:ID?fields=citationCount,influentialCitationCount"`
3. **Read abstract**: `web_extract(urls=["https://arxiv.org/abs/ID"])`
4. **Read full paper**: `web_extract(urls=["https://arxiv.org/pdf/ID"])`
5. **Find related work**: `curl -s "https://api.semanticscholar.org/graph/v1/paper/arXiv:ID/references?fields=title,citationCount&limit=20"`
6. **Get recommendations**: POST to Semantic Scholar recommendations endpoint
7. **Track authors**: `curl -s "https://api.semanticscholar.org/graph/v1/author/search?query=NAME"`

## RSS Feeds (Daily New Submissions)

The API's `sortBy=submittedDate` is unreliable for detecting today's new papers (rate limits, sorting bugs, stale results). **Use RSS feeds instead** for daily monitoring.

For the automated daily briefing cron job (astro-ph + detector keyword filtering + LLM classification), see `references/daily-briefing.md`.

arXiv exposes two RSS front-ends that occasionally fall out of sync. The briefing script now tries both (v1.3.0+):

```bash
# Primary (currently reliable)
curl -s "https://rss.arxiv.org/rss/astro-ph"
curl -s "https://rss.arxiv.org/rss/physics.ins-det"
curl -s "https://rss.arxiv.org/rss/cond-mat.supr-con"

# Legacy fallback (has returned empty channels during outages)
curl -s "https://export.arxiv.org/rss/astro-ph"
```

If you get 0 items from one host, try the other — they share the same pubDate but content sync can lag.

For LLM classification, the script uses a three-tier proxy fallback chain: `nim-large` (fast, first-valid-wins) → `nim-fusion` (reliable fan-out+judge) → DeepSeek (paid last resort). Choosing the right primary model is critical — see `references/arxiv-briefing-model-choice.md` for the full analysis. Key findings: nim-small produces malformed JSON ~17% of the time (unusable), nim-fusion as primary takes 35+ min for 150 papers (too slow for cron 600s timeout), nim-large is the best primary (fast, mostly reliable JSON). The script's `_demoted` mechanism auto-skips endpoints that produce bad JSON on a per-batch basis.

### RSS Structure

- Each `<item>` has `<title>`, `<link>`, `<description>` (abstract HTML), `<category>` (subject classification, e.g. `astro-ph.HE`), `<arxiv:announce_type>` (new/cross/replaced)
- **announce_type**: use dedicated `<arxiv:announce_type>new</arxiv:announce_type>` XML element (NOT the description text) — more robust against format changes
- **YYMM cross-validation**: new-format arXiv IDs (`YYMM.NNNNN`) encode submission month. Compare ID YYMM vs feed pubDate YYMM (±1 month tolerance) to catch cross-listed papers mislabeled as "new". Stale papers (ID month off by >1 from feed) are filtered before announce_type check.
- `<link>` contains the arXiv ID: extract with `link.split("/abs/")[-1]`
- `<category>` tags contain the granular arXiv subject classification (e.g. `astro-ph.IM`, `astro-ph.SR`, `cs.AI`) — available but not currently used for filtering
- RSS updates daily (~08:00 Beijing time for astro-ph), contains all new + cross-listed + replaced papers

### Parse RSS to get new papers (updated with XML announce_type + YYMM check)

```python
import urllib.request, xml.etree.ElementTree as ET, re

feed = urllib.request.urlopen("https://arxiv.org/rss/astro-ph").read()
root = ET.fromstring(feed)

# Extract feed pubDate YYMM for cross-validation
pub = root.find('.//pubDate')
feed_yyyymm = None
if pub is not None and pub.text:
    from email.utils import parsedate_to_datetime
    feed_dt = parsedate_to_datetime(pub.text.strip())
    feed_yyyymm = feed_dt.strftime("%y%m")

for item in root.findall('.//item'):
    arxiv_id = item.find('link').text.strip().split('/abs/')[-1]
    base_id = arxiv_id.split('v')[0]

    # YYMM cross-validation: skip papers with ID month far from feed month
    if feed_yyyymm:
        ym = re.match(r'^(\d{4})\.', base_id)
        if ym:
            id_yy, id_mm = int(ym.group(1)[:2]), int(ym.group(1)[2:])
            f_yy, f_mm = int(feed_yyyymm[:2]), int(feed_yyyymm[2:])
            if abs((id_yy*12+id_mm) - (f_yy*12+f_mm)) > 1:
                continue  # ID submission month >1 month away from feed

    # Announce type from dedicated XML element (not description text)
    at_elem = item.find('{http://arxiv.org/schemas/atom}announce_type')
    if at_elem is not None and at_elem.text and at_elem.text.strip() != 'new':
        continue  # skip cross-listed and replaced

    title = item.find('title').text.strip()
    abstract = item.find('description').text.strip()[:500]
    print(f"[{arxiv_id}] {title}")
```

### When to use RSS vs API

| Use RSS when | Use API when |
|-------------|-------------|
| Daily new submission monitoring | Searching by keyword/author |
| Getting "today's papers" in a category | Pagination over large result sets |
| Building daily briefing/notification systems | Fetching specific papers by ID |
| Need reliable "new today" classification | Need citation/reference traversal (Semantic Scholar) |

## Rate Limits

| API | Rate | Auth |
|-----|------|------|
| arXiv | ~1 req / 3 seconds | None needed |
| Semantic Scholar | 1 req / second | None (100/sec with API key) |

## Notes

- arXiv returns Atom XML — use the helper script or parsing snippet for clean output
- Semantic Scholar returns JSON — pipe through `python3 -m json.tool` for readability
- arXiv IDs: old format (`hep-th/0601001`) vs new (`2402.03300`)
- PDF: `https://arxiv.org/pdf/{id}` — Abstract: `https://arxiv.org/abs/{id}`
- HTML (when available): `https://arxiv.org/html/{id}`
- For local PDF processing, see the `ocr-and-documents` skill

## ID Versioning

- `arxiv.org/abs/1706.03762` always resolves to the **latest** version
- `arxiv.org/abs/1706.03762v1` points to a **specific** immutable version
- When generating citations, preserve the version suffix you actually read to prevent citation drift (a later version may substantially change content)
- The API `<id>` field returns the versioned URL (e.g., `http://arxiv.org/abs/1706.03762v7`)

## Historical Briefings (补发)

When the daily cron fails (e.g., "⚠️ 技术原因未能自动生成") and the user asks for
补发, RSS feeds cannot provide past dates. See `references/historical-briefing.md`
for the full retrieval-and-classification workflow using OAI-PMH + arXiv API.

Quick summary:
- **astro-ph**: Use OAI-PMH `ListRecords` with `set=physics:astro-ph` (300-450 papers/day)
- **ins-det / supr-con**: Use arXiv API date queries (≤30 papers/day)
- **Display**: For large volumes without time for full LLM classification, random-sample
  ~30 papers and present titles + abstracts grouped by category

## Already-Delivered Feed (Cross-Day Dedup Silent Exit)

When the cron runs and the script reports "No new papers to report" on stderr with empty stdout, and the feed *is* current (not stale), the most likely cause is **cross-day dedup**: the RSS feed for today's UTC date was already available and fully processed during the previous Beijing-time calendar day. The script's 7-day dedup correctly prevents re-delivery, but the output pattern (empty stdout + "No new papers to report" on stderr) doesn't match any of the 5 standard cron delivery rules. **Treat this as [SILENT]** — the briefing was already successfully delivered; there is nothing new to report.

Diagnostic check: verify overlap between `reported_ids_YYYY-MM-DD.json` (previous day) and current RSS paper IDs. If 100% overlap, this is the cross-day dedup case.

## Cron Failure Diagnosis

When the arXiv cron job repeatedly fails with "技术原因未能自动生成", the root
cause is usually a terminal-approval block — the `terminal()` tool returns
`status: "pending_approval"` and the cron fallback rule fires. See the
`cron-delivery-debug` skill for the full diagnostic checklist. Common causes:

- **Tirith binary GLIBC mismatch** — `pattern_key: "tirith:unknown"`, binary crashes
  on systems with GLIBC < 2.33 (e.g. Alibaba Cloud Linux 3). Fix: `security.tirith_enabled: false`
- **`approvals.cron_mode: deny`** — config blocking all terminal commands. Fix: `cron_mode: approve`
- **RSS host outage** — One arXiv RSS front-end returns an empty channel (zero items) while the other is fine. Symptom: hourly `⚠️ RSS已更新但未找到新论文` messages after 12:00 Beijing, no briefing delivered. Fix: script v1.3.0+ now uses multi-host (`rss.arxiv.org` primary, `export.arxiv.org` fallback). Verify manually: `curl -s 'https://rss.arxiv.org/rss/astro-ph' | grep -c '<item>'` vs export host. See `references/arxiv-briefing-2026-06-23-rss-host-outage.md`.
- **Proxy fusion timeout** — nim-fusion needs 60-120s for fan-out + judge pipeline but client timeout was 60s, causing every batch to fall through to paid DeepSeek. Probe reports healthy (sends tiny "Say ok" probe) but production batches time out. Fix: script v1.3.1+ uses 300s timeout for proxy endpoints, adds nim-large as free intermediate fallback before DeepSeek. See `references/arxiv-briefing-2026-06-23-proxy-fusion-timeout.md`.
- **NIM fusion proxy timeout** — `classify_batch` times out at 60 s even though the nvidia-model-probe reports nim-fusion as "healthy" (1.91 s). Cause: probe sends 3 tokens, arxiv batches send ~5000 — fusion mode's 4× backend fan-out + judge is fine for trivial payloads but stalls past 60 s for heavy ones. Fix: script v1.3.0+ demotes the proxy after the first timeout (60 s penalty), then falls back to DeepSeek directly for remaining batches. Verify: `curl --max-time 30 localhost:18900/v1/chat/completions -d '{"model":"nim-fusion","messages":[{"role":"user","content":"Say ok"}],"max_tokens":10}'` vs `nim-large`. See `references/arxiv-briefing-nim-fusion-timeout.md`.
- **`is_feed_today()` strict comparison timezone trap** — 10:00-11:00 Beijing cron runs report "arXiv今日数据尚未更新" even though papers ARE available. arXiv RSS `<pubDate>` is US-Eastern; strict `feed_dt.date() == now_beijing.date()` fails before 12:00 Beijing because pubDate hasn't flipped yet. Fix: use 0-1 day tolerance (`0 <= age_days <= 1`) instead of strict equality. See `references/arxiv-briefing-2026-06-25-timezone-timeout.md`.
- **Cron script timeout (120s) kills pipeline** — after pubDate flips at 12:00, the full LLM classification pipeline starts but gets killed by the 120s default script timeout. Symptom: `Script timed out after 120s` in cron output, no briefing generated at 12:00-14:00, then "已过15:00" at cutoff. Fix: `hermes config set cron.script_timeout_seconds 600`. The pipeline needs 300-600s for 10+ LLM batches. See `references/arxiv-briefing-2026-06-25-timezone-timeout.md`.
- **Cumulative LLM batch latency exceeding script timeout** — `Script timed out after 600s` even at 10:00-11:00 (well before 15:00 cutoff) with no partial output. NOT a single-batch timeout — cumulative latency from 11 LLM batches exceeds 600s when proxy backends (kimi, ds-pro) are intermittently slow. Symptom: proxy logs show requests taking 20-55s (normal) with 1-2 batches taking 100-140s. nim-large JSON failures force fallback to slower nim-fusion, amplifying the problem. Fix: increase to `hermes config set cron.script_timeout_seconds 900`. See `references/arxiv-briefing-2026-07-02-cumulative-timeout.md`.

## Withdrawn Papers

Papers can be withdrawn after submission. When this happens:
- The `<summary>` field contains a withdrawal notice (look for "withdrawn" or "retracted")
- Metadata fields may be incomplete
- Always check the summary before treating a result as a valid paper
