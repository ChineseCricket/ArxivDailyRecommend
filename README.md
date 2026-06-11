# Arxiv Daily Recommend

[![中文](https://img.shields.io/badge/中文-README_CN-blue)](README_CN.md)

Personalized arXiv daily briefing for astrophysics & superconducting detectors.  
Fetches new submissions from arXiv RSS feeds, classifies them with LLMs, and delivers a curated briefing.

## What It Covers

| Feed | Filter |
|------|--------|
| `astro-ph` | All new submissions |
| `physics.ins-det` | Detector-related papers (TES, MKID, SQUID, bolometer, etc.) |
| `cond-mat.supr-con` | Detector-related papers only |

Papers are classified into **4 importance tiers** and scored against **5 interest domains** with configurable weights.

## Quick Start

```bash
# No dependencies beyond Python 3.8 stdlib
python3 scripts/arxiv_daily_briefing.py --force
```

Output: a Markdown-formatted briefing to stdout.

## How It Works

1. Fetches RSS feeds from `export.arxiv.org/rss/` (3 feeds)
2. Filters by announce type ("new" only) and detector keywords
3. Sends batches of 12 papers to an LLM for classification
4. Selects papers: all Tier-1 + Tier-2 with interest match + top 10% of Tier 3/4
5. Formats and prints the briefing

## Interest Domains

| Weight | Domain |
|--------|--------|
| ×5 | 超导探测器及其读出技术 (Superconducting detectors & readout) |
| ×4 | 弥散热气体 (Warm-hot diffuse gas) |
| ×3 | 天文仪器与技术 (Astronomical instrumentation) |
| ×2 | X射线观测恒星与行星系统 (X-ray stellar-planet interactions) |
| ×1 | 宜居世界搜索与地外生命 (Habitable worlds & biosignatures) |

## LLM Backends

The script has an adaptive 3-tier fallback:

| Priority | Endpoint | Notes |
|----------|----------|-------|
| 1 | Waterfall Proxy (`localhost:18900`) | Optional — set your own |
| 2 | DeepSeek (`api.deepseek.com`) | Needs `DEEPSEEK_API_KEY` env var |
| 3 | z.ai GLM (`open.bigmodel.cn`) | Needs `GLM_API_KEY` env var |

If an endpoint fails, it auto-demotes to the next. If you don't have the proxy running, the script adapts after the first batch.

## Configuration

Edit `scripts/arxiv_daily_briefing.py`:

- `RSS_FEEDS` (~line 64) — arXiv categories to monitor
- `DETECTOR_KEYWORDS_PATTERNS` (~line 74) — keyword filters for detector feeds
- `INTEREST_DOMAINS` (~line 90) — your research interests (see below)

### Customizing Interest Domains

Each domain has a `name`, `tag` (emoji label in output), `weight` (multiplier), and a list of `keywords` (matched case-insensitively against title + abstract):

```python
INTEREST_DOMAINS = [
    {"name": "超导探测器及其读出技术", "tag": "🔬超导探测器", "weight": 5,
     "keywords": ["superconducting detector", "transition-edge sensor", ...]},
    {"name": "弥散热气体",                   "tag": "🌫️热气体",    "weight": 4,
     "keywords": ["warm-hot igm", "circumgalactic medium", ...]},
    # ... add/remove/modify domains here
]
```

To change interests:
1. Edit the `INTEREST_DOMAINS` list — add, remove, or reorder domains
2. Adjust `weight` values to change priority (higher = more papers from that domain selected)
3. Update `keywords` to match your field's terminology
4. The LLM classification prompt is auto-generated from this list — no other changes needed

Example — adding a new domain:
```python
{"name": "快速射电暴", "tag": "📡FRB", "weight": 4,
 "keywords": ["fast radio burst", "FRB", "radio transient", "CHIME", "repeating FRB"]},
```

- `LLM_ENDPOINTS` (~line 33) — add/modify your LLM backends

## Usage Modes

```bash
# Manual — always generates fresh briefing
python3 scripts/arxiv_daily_briefing.py --force

# Manual — only shows new unreported papers
python3 scripts/arxiv_daily_briefing.py

# Cron mode — hourly retry 10:00–15:00 Beijing, respects dedup
python3 scripts/arxiv_daily_briefing.py --cron
```

## Hermes Agent Integration

This project is structured as a [Hermes Agent](https://hermes-agent.nousresearch.com) skill:

```
SKILL.md                     → Skill definition (Hermes reads this)
scripts/arxiv_daily_briefing.py  → Core briefing script
scripts/search_arxiv.py       → arXiv search helper
references/daily-briefing.md  → Detailed docs
```

To use with Hermes cron + WeChat delivery:

```bash
hermes cron create \
  --name "arxiv-daily-briefing" \
  --schedule "0 10-15 * * 1-5" \
  --skill arxiv \
  --deliver weixin \
  --prompt "Run: ~/.hermes/hermes-agent/venv/bin/python3 -u \
    ~/.hermes/skills/research/arxiv/scripts/arxiv_daily_briefing.py --force"
```

## License

MIT
