# arXiv Daily Recommend

> Originally a standalone skill `arxiv-today`, now consolidated under `arxiv` as a domain-specific application.

Generates a personalized arXiv daily briefing covering:
- **astro-ph** (all subcategories)
- **physics.ins-det** (instrumentation & detectors)
- **cond-mat.supr-con** (superconductivity)

Papers are classified into 4 importance tiers and scored against 5 interest domains with weights, then filtered to produce a concise briefing.

## Script

**Location:** `scripts/arxiv_daily_briefing.py` (self-contained within this skill)

### Running Modes

| Mode | Command | Behavior |
|------|---------|----------|
| Manual (force) | `python3 scripts/arxiv_daily_briefing.py --force` | Always generates fresh briefing, skips dedup, ignores retry state. ⚠️ Do NOT combine with `--cron` — `--cron --force` still hits the done-flag check before `--force` logic runs. |
| Manual (normal) | `python3 scripts/arxiv_daily_briefing.py` | Generates briefing only if new unreported papers exist |
| Cron | `python3 scripts/arxiv_daily_briefing.py --cron` | Respects retry_state.json (hourly retry 10:00–15:00 Beijing), dedup, "done" flag |

### How to Execute

```bash
# Standalone (Python 3.8+, no deps beyond stdlib):
python3 scripts/arxiv_daily_briefing.py --force

# Or for background execution:
PYTHONUNBUFFERED=1 python3 scripts/arxiv_daily_briefing.py --force 2>&1
```

**No dependencies** — uses only Python stdlib (`urllib`, `xml`, `json`, `re`, `datetime`). Runs on Python 3.8+.

**Important flags:**
- **`-u` (unbuffered):** Required when running as background process.
- **`--force`:** Always use for manual triggers.
- **⚠️ Do NOT use `--force=manual` or `--force=somevalue`**: The script checks `"--force" in sys.argv` (exact string match). Only bare `--force` works.

Runtime: ~5-6 minutes (LLM analysis of ~80+ papers in batches of 12).

## Classification System

### Importance Tiers

| Tier | Label | Criteria |
|------|-------|----------|
| Tier-1 | 🔴 重大突破 | New physics, disruptive tech, Nature/Science-level results |
| Tier-2 | 🟠 重要综述 | High-quality reviews, long-term project milestones, methodology breakthroughs |
| Tier-3 | 🟡 项目更新 | Routine collaboration progress, incremental improvements |
| Tier-4 | ⚪ 一般工作报告 | Routine observations, technical notes, small-scale analysis |

### Interest Domains & Weights

| Weight | Domain | Keywords |
|--------|--------|----------|
| ×5 | 超导探测器及其读出技术 | TES, MKID, KID, SQUID, multiplexing, CMB detector, transition-edge |
| ×4 | 弥散热气体 | warm-hot IGM, circumgalactic medium, WHIM, hot halo, diffuse X-ray |
| ×3 | 天文仪器与技术 | instrumentation, telescope, spectrograph, optics, calibration |
| ×2 | X射线观测恒星与行星系统 | star-planet interaction, X-ray transit, coronal mass ejection, stellar wind, stellar flare, atmospheric escape, space weather, exoplanet X-ray |
| ×1 | 宜居世界搜索与地外生命 | habitable zone, biosignature, exoplanet atmosphere, technosignature |

### Report Selection Rules

```
Report = (all Tier-1)
       ∪ (Tier-2 matching any interest domain)
       ∪ (top 10% of Tier-3 + Tier-4 by weighted score, min 1 paper)
```

## LLM Backend

The script uses a configurable LLM endpoint chain for classification. By default it connects to a local proxy that handles model routing and fallback internally. If the proxy is unreachable, it falls back to a direct API call (DeepSeek).

**Configuration:** Set `DEEPSEEK_API_KEY` environment variable (or `.env` file in the skill directory) for the fallback endpoint. The proxy endpoints need no keys — they handle authentication internally.

- Batch size: 12 papers per LLM call
- Abstracts truncated to 500 characters
- Failed endpoints are automatically demoted (skipped) for the remainder of the run

The briefing footer shows which endpoints handled each batch:
```
⚡ LLM分类: LLM Proxy 5/8批(62%) · DeepSeek 3/8批(37%)
```

## Output Format

The script prints the formatted Markdown briefing to **stdout**. stderr contains progress/debug info.

## State Files

| File | Purpose |
|------|---------|
| `~/.hermes/cron/arxiv_briefing/reported_ids_YYYY-MM-DD.json` | Set of paper IDs reported on that date. Cross-day dedup checks all files from past 7 days. Auto-cleans files >7 days old. |
| `~/.hermes/cron/arxiv_briefing/retry_state.json` | Cron retry tracking (date, done flag, notified hours) |

## Customization

To adapt this skill for your own research interests:

1. **Edit `INTEREST_DOMAINS`** in `scripts/arxiv_daily_briefing.py` — change the domain names, keywords, and weight multipliers
2. **Edit `INTEREST_CATEGORIES`** — change which arXiv categories are monitored
3. **Edit `KEYWORD_CATEGORIES`** — change keyword-based filtering for categories that need it
4. **Adjust `filter_papers()` thresholds** — change the percentage of Tier-3/4 papers included

The classification tiers and selection logic are domain-agnostic — only the interest domains and categories need customization.

## RSS Feeds

The script fetches from multiple RSS hosts for reliability:
- `rss.arxiv.org` (primary)
- `export.arxiv.org` (fallback)

arXiv RSS `<pubDate>` is US-Eastern midnight (00:00 -0400). Papers go live at ~20:00 ET (~08:00 Beijing next day). The script uses a 0-1 day tolerance to account for this timezone offset.

Key RSS parsing features:
- **announce_type**: Read from dedicated `<arxiv:announce_type>` XML element (not description text)
- **YYMM cross-validation**: Paper ID submission month compared to feed pubDate month (±1 tolerance) to filter stale/cross-listed papers
- **Cross-day dedup**: Past 7 days' reported IDs are unioned into the dedup set
