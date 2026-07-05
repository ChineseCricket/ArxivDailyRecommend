#!/usr/bin/env python3
"""arXiv Daily Briefing — Astrophysics & Superconducting Detectors
Uses RSS feeds for reliable data fetching, LLM for classification.
Primary: LLM Proxy combo/steady-fallback (handles model routing internally).
Fallback: DeepSeek direct (if proxy process is completely down).
"""

import urllib.request
import xml.etree.ElementTree as ET
import json
import time
import sys
import os
import re
from datetime import datetime, timedelta, timezone

# Load .env for API keys
from pathlib import Path
_dotenv = Path.home() / ".hermes" / ".env"
if _dotenv.exists():
    for _line in _dotenv.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

# === Configuration ===
BEIJING_TZ = timezone(timedelta(hours=8))

# LLM endpoints: proxy virtual models in reliability order.
# nim-large (fast hedge) → nim-fusion (fan-out+judge, for if large produces bad JSON).
# DeepSeek only as last-resort if proxy is completely unreachable.
LLM_ENDPOINTS = [
    {
        "name": "LLM Proxy (nim-large)",
        "url": "http://localhost:18900/v1/chat/completions",
        "key": None,
        "model": "nim-large",
    },
    {
        "name": "LLM Proxy (nim-fusion)",
        "url": "http://localhost:18900/v1/chat/completions",
        "key": None,
        "model": "nim-fusion",
    },
    {
        "name": "DeepSeek (proxy-down fallback)",
        "url": "https://api.deepseek.com/v1/chat/completions",
        "key": os.environ.get("DEEPSEEK_API_KEY") or "sk-YOU...HERE",
        "model": "deepseek-v4-pro",
    },
]

# Sequential fallback: nim-large (fast & structured) → nim-fusion (reliable JSON)
# → DeepSeek (paid, only if proxy is completely dead).
# The demotion mechanism auto-skips endpoints that produce malformed JSON.
_endpoint_order = list(range(len(LLM_ENDPOINTS)))
_demoted = set()  # endpoint indices that failed and should be skipped
MAX_RETRIES = 3
RETRY_INTERVAL = 3600  # 1 hour
CACHE_DIR = os.path.expanduser("~/.hermes/cron/arxiv_briefing")

# RSS feeds to fetch
RSS_FEEDS = [
    "astro-ph",          # All astrophysics
    "physics.ins-det",   # Instruments & detectors
    "cond-mat.supr-con", # Superconductivity
]

# Only keep "new" type papers from these feeds.
# For physics.ins-det and cond-mat.supr-con, also filter by keywords
# Uses regex word-boundary matching (\\b) for abbreviations to avoid
# false positives (e.g. "tes" matching "states", "nes" matching "tunneling").
DETECTOR_KEYWORDS_PATTERNS = [
    # Full phrases (substring match is fine — distinctive enough)
    r"superconducting detector", r"transition-edge", r"microcalorimeter",
    r"bolometer", r"cryogenic detector", r"mm-wave detector",
    r"submillimeter detector", r"cmb detector", r"photon noise",
    r"noise equivalent", r"kinetic inductance", r"multiplex",
    r"readout", r"mu-metal",
    # Abbreviations — word-boundary to avoid false matches
    r"\bTES\b", r"\bMKID\b", r"\bKID\b", r"\bSQUID\b",
    r"\bNES\b", r"\bNEP\b",
    # Compound terms with abbreviations
    r"\bTES\b.*(?:microcalorimeter|bolometer|detector|array|sensor)",
    r"\bKID\b.*(?:array|detector|sensor)",
]

# Interest domains with weights
INTEREST_DOMAINS = [
    {"name": "超导探测器及其读出技术", "tag": "🔬超导探测器", "weight": 5,
     "keywords": ["superconducting detector", "transition-edge sensor",
                   "kinetic inductance", "microwave squid", "multiplexing",
                   "frequency division multiplex", "fdm", "tdm", "readout",
                   "mu-metal", "detector array", "bolometer", "microcalorimeter",
                   "mm-wave detector", "sub-mm detector", "cmb detector",
                   "photon noise", "noise equivalent power"]},
    {"name": "弥散热气体", "tag": "🌫️热气体", "weight": 4,
     "keywords": ["warm-hot igm", "whim", "circumgalactic medium", "cgm",
                   "hot halo", "diffuse x-ray", "ovii", "oviii",
                   "absorption line", "baryon", "missing baryon", "hot gas",
                   "intergalactic medium", "intracluster medium",
                   "hot circumgalactic", "diffuse baryon"]},
    {"name": "天文仪器与技术", "tag": "🔭天文仪器", "weight": 3,
     "keywords": ["instrumentation", "telescope design", "spectrograph",
                   "optics", "calibration", "adaptive optics", "interferometry",
                   "coronagraph", "integral field unit", "ifu",
                   "telescope optics", "mirror", "focal plane"]},
    {"name": "X射线观测恒星与行星系统相互作用", "tag": "⭐X射线恒星行星", "weight": 2,
     "keywords": ["star-planet interaction", "x-ray transit",
                   "coronal mass ejection", "stellar wind",
                   "exoplanet x-ray", "flare star", "magnetosphere planet",
                   "planetary atmosphere erosion", "x-ray emission host star",
                   "x-ray stellar", "stellar flare", "stellar activity",
                   "atmospheric escape", "space weather",
                   "high-energy radiation planet"]},
    {"name": "宜居世界搜索与地外生命", "tag": "🌍宜居世界", "weight": 1,
     "keywords": ["habitable zone", "biosignature", "technosignature",
                   "exoplanet atmosphere characterization", "transit spectroscopy",
                   "life detection", "habitable world", "biomarker",
                   "atmospheric escape", "habitable exoplanet"]},
]


def fetch_rss_feed(category):
    """Fetch and parse an arXiv RSS feed, trying multiple front-end hosts.

    arXiv exposes two RSS front-ends that occasionally fall out of sync:
      - rss.arxiv.org    (primary, currently reliable)
      - export.arxiv.org (legacy; has returned an empty channel — correctly
        dated but with zero <item>s — during outages, e.g. late June 2026)
    We try each host and return the first response that actually contains
    items. If every host returns an empty channel we return the last one so
    the caller can still read channel metadata (pubDate) for date checks."""
    hosts = [
        f"https://rss.arxiv.org/rss/{category}",
        f"https://export.arxiv.org/rss/{category}",
    ]
    last_xml = ""
    for url in hosts:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "arxiv-daily-briefing/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                xml_data = resp.read().decode("utf-8")
            if xml_data.count("<item") > 0:
                return xml_data
            last_xml = xml_data
        except Exception:
            continue
    return last_xml


def parse_rss_items(xml_data, feed_category, keyword_filter=False):
    """Parse RSS items into paper dicts. Optionally filter by detector keywords."""
    root = ET.fromstring(xml_data)
    papers = []

    # Extract channel pubDate YYMM for ID cross-validation
    feed_yyyymm = None
    chan_pub = root.find('.//pubDate')
    if chan_pub is not None and chan_pub.text:
        try:
            from email.utils import parsedate_to_datetime
            _fdt = parsedate_to_datetime(chan_pub.text.strip())
            feed_yyyymm = _fdt.strftime("%y%m")
        except Exception:
            pass

    for item in root.findall('.//item'):
        title = item.find('title').text.strip().replace('\n', ' ')
        link = item.find('link').text.strip()
        desc = item.find('description').text or ''

        # Extract arXiv ID from link
        arxiv_id = link.split('/abs/')[-1] if '/abs/' in link else ''
        if not arxiv_id:
            continue
        base_id = arxiv_id.split('v')[0]

        # YYMM cross-validation: ID submission month should match feed month (+/-1)
        if feed_yyyymm:
            _id_ym = re.match(r'^(\d{4})\.', base_id)
            if _id_ym and not _yyyymm_close(_id_ym.group(1), feed_yyyymm, tolerance=1):
                print(f"    [YYMM] Skip {base_id}: ID month {_id_ym.group(1)} vs feed {feed_yyyymm}", file=sys.stderr)
                continue

        # Determine announce type from dedicated XML element
        # (more robust than parsing description text)
        announce_type = 'other'
        at_elem = item.find('{http://arxiv.org/schemas/atom}announce_type')
        if at_elem is not None and at_elem.text:
            announce_type = at_elem.text.strip()

        # Only keep new submissions (not cross-listed or replaced)
        if announce_type != 'new':
            continue

        # Extract abstract from description
        abstract = ''
        abs_match = re.search(r'Abstract:\s*(.*)', desc, re.DOTALL)
        if abs_match:
            abstract = abs_match.group(1).strip()
            # Clean LaTeX artifacts
            abstract = re.sub(r'\$[^$]*\$', '', abstract)
            abstract = abstract.replace('\n', ' ').strip()[:500]

        # Keyword filter for non-astro-ph feeds (regex word-boundary matching)
        if keyword_filter:
            text = title + ' ' + abstract
            if not any(re.search(pat, text, re.IGNORECASE) for pat in DETECTOR_KEYWORDS_PATTERNS):
                continue

        papers.append({
            'id': base_id,
            'title': title,
            'abstract': abstract,
            'feed_category': feed_category,
            'url': f"https://arxiv.org/abs/{base_id}",
        })

    return papers


def fetch_all_papers():
    """Fetch papers from all RSS feeds."""
    all_papers = []
    for feed in RSS_FEEDS:
        try:
            print(f"  Fetching {feed}...", file=sys.stderr)
            xml_data = fetch_rss_feed(feed)
            is_keyword = feed not in ("astro-ph",)
            papers = parse_rss_items(xml_data, feed, keyword_filter=is_keyword)
            print(f"    {len(papers)} new papers from {feed}", file=sys.stderr)
            all_papers.extend(papers)
            time.sleep(2)  # Be nice to arXiv
        except Exception as e:
            print(f"    Warning: {feed} fetch failed: {e}", file=sys.stderr)

    return deduplicate(all_papers)


def deduplicate(papers):
    """Remove duplicates by base arXiv ID."""
    seen = set()
    unique = []
    for p in papers:
        if p['id'] not in seen:
            seen.add(p['id'])
            unique.append(p)
    return unique


def _yyyymm_close(yyyymm_a, yyyymm_b, tolerance=1):
    """Check if two YYMM strings (e.g. '2606') are within +/- tolerance months."""
    try:
        ya, ma = int(yyyymm_a[:2]), int(yyyymm_a[2:4])
        yb, mb = int(yyyymm_b[:2]), int(yyyymm_b[2:4])
        return abs((ya * 12 + ma) - (yb * 12 + mb)) <= tolerance
    except (ValueError, IndexError):
        return True  # Can't parse — don't block


def get_feed_date():
    """Get the publication date (pubDate) from the RSS feed. Returns a datetime in Beijing TZ."""
    try:
        xml_data = fetch_rss_feed("astro-ph")
        root = ET.fromstring(xml_data)
        # Use first item's pubDate — they're all the same within a daily feed
        pub = root.find('.//pubDate')
        if pub is not None and pub.text:
            # Parse: "Tue, 12 May 2026 00:00:00 -0400"
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(pub.text.strip())
            return dt.astimezone(BEIJING_TZ)
    except:
        pass
    return None


def is_feed_today():
    """Check if the RSS feed contains today's papers (Beijing date).

    Primary check: pubDate age (0-1 days, accounting for US-Eastern to Beijing offset).
    YYMM sanity: if pubDate passes but feed YYMM differs from current month by >1,
    log a diagnostic warning (does not reject — pubDate is authoritative).
    """
    feed_dt = get_feed_date()
    if feed_dt is None:
        return False, None
    now_beijing = datetime.now(BEIJING_TZ)
    # arXiv RSS pubDate is US-Eastern midnight (00:00 -0400), which equals
    # Beijing noon of the *previous* day.  Papers actually go live at ~20:00 ET
    # (= ~08:00 Beijing next day), so the RSS date is always 1 day behind
    # Beijing when papers are fresh.
    # Allow feed_date == today OR yesterday to account for the timezone offset:
    # - Before 12:00 Beijing, pubDate still shows yesterday's ET date
    # - After 12:00 Beijing, pubDate flips to today's ET date
    # Reject feeds older than 1 day to prevent stale weekend re-delivery.
    age_days = (now_beijing.date() - feed_dt.date()).days
    is_today = 0 <= age_days <= 1

    # YYMM sanity check (diagnostic only — pubDate remains authoritative)
    if is_today:
        feed_yyyymm = feed_dt.strftime("%y%m")
        now_yyyymm = now_beijing.strftime("%y%m")
        if not _yyyymm_close(feed_yyyymm, now_yyyymm, tolerance=1):
            print(f"  [YYMM] Feed pubDate YYMM ({feed_yyyymm}) differs from current ({now_yyyymm}) by >1 month — possible stale feed", file=sys.stderr)

    return is_today, feed_dt.strftime("%Y-%m-%d %H:%M 北京时间")


def classify_batch(papers_batch, batch_idx, total_batches):
    """Send a batch of papers to LLM for classification.
    Fallback chain: nim-fusion → nim-large → DeepSeek (paid).
    Failed endpoints are demoted (skipped) for the rest of the run."""

    paper_texts = []
    for i, p in enumerate(papers_batch):
        paper_texts.append(
            f"[P{i+1}] ID: {p['id']}\n"
            f"Feed: {p.get('feed_category', '?')}\n"
            f"Title: {p['title']}\n"
            f"Abstract: {p['abstract']}"
        )

    domain_desc = "\n".join(
        f"  - {d['name']} (权重×{d['weight']})"
        for d in INTEREST_DOMAINS
    )

    prompt = f"""你是天体物理学与超导探测器技术领域的资深专家。请分析以下 {len(papers_batch)} 篇 arXiv 新投稿论文。

对每篇论文完成：

1. **重要性分级**（严格四选一）：
   - Tier-1: 重大突破 — 新物理发现、颠覆性技术、里程碑式观测成果（极其罕见，真正改变领域认知的工作）
   - Tier-2: 重要综述/重要进展 — 高质量综述论文、长期项目重要里程碑、重要方法学突破
   - Tier-3: 项目更新 — 合作组常规进展、已知方法增量改进、初步结果
   - Tier-4: 一般工作报告 — 常规观测报告、技术报告、小规模分析

   注意：Tier-1 门槛极高，只有真正的突破性成果才能标记。绝大部分论文应为 Tier-3 或 Tier-4。

2. **兴趣领域相关度**（每个领域 0-3 分：0=无关 1=略微相关 2=相关 3=高度相关）：
{domain_desc}

   ⚠️ 重要排除规则：「超导探测器及其读出技术」领域仅关注**探测器器件与读出系统**本身，不包括纯凝聚态超导理论研究。以下主题即使来自cond-mat.supr-con也应评为0分：
   - 超导配对机制、BCS理论、非常规超导机理（如拓扑超导、马约拉纳费米子用于量子计算）
   - 高温超导体材料性质（铜氧化物、铁基、镍基等合成与表征）
   - 涡旋物理、磁通钉扎、临界电流、磁化率测量
   - 约瑟夫森结用于量子比特/量子计算（但量子比特的低温读出与多路复用技术**属于该领域**，应正常打分）
   - 超导薄膜/异质结生长（除非明确用于探测器制造）
   - Ising超导、拓扑超导、自旋三重态配对等纯基础物理

   以下属于该领域，应正常打分：TES/MKID/KID/SQUID探测器、微卡计、辐射热计、低温探测器阵列、多路复用读出、超导纳米线单光子探测器(SNSPD)、mm波/亚mm波探测器、CMB探测器、X射线/γ射线超导探测器、量子比特低温读出与多路复用。

   ⚠️ 同理，「X射线观测恒星与行星系统相互作用」仅关注**恒星活动对行星系统的高能辐射影响**。以下即使涉及X射线也应评为0分：
   - 超亮X射线源(ULX)、X射线双星、AGN/活动星系核的X射线辐射
   - 中子星/黑洞吸积（除非明确涉及行星磁层/大气）
   - 星系团/星系尺度弥散X射线（属于「弥散热气体」，不属本领域）
   以下属于该领域，应正常打分：恒星耀斑/CME对行星大气的X射线剥离、行星X射线凌日、恒星星风与行星磁层相互作用、主星X射线辐射对行星大气演化的影响。

3. **一句话中文简介**（40-60字，概括最重要的创新点和结果，简洁精准）

严格返回纯JSON数组（不要markdown代码块标记、不要额外解释）：
[
  {{
    "paper_index": 1,
    "tier": "Tier-1",
    "relevance": {{
      "超导探测器及其读出技术": 0,
      "弥散热气体": 0,
      "天文仪器与技术": 0,
      "X射线观测恒星与行星系统相互作用": 0,
      "宜居世界搜索与地外生命": 0
    }},
    "summary_cn": "一句话中文简介"
  }}
]

论文列表：
{chr(10).join(paper_texts)}"""

    messages = [
        {"role": "system", "content": "你是天体物理学和探测器技术领域的专家评审。只返回纯JSON数组，不要任何额外文字、解释或markdown标记。"},
        {"role": "user", "content": prompt}
    ]

    # Fallback chain: nim-fusion → nim-large → DeepSeek.
    # Endpoints in _demoted are skipped for the rest of the run to avoid
    # re-paying timeout penalties.  Proxy endpoints (idx 0,1) get 300s
    # (cron runs in background); DeepSeek (idx 2) gets 90s (direct, paid).
    for ep_idx in _endpoint_order:
        if ep_idx in _demoted:
            continue
        endpoint = LLM_ENDPOINTS[ep_idx]
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
            call_timeout = 300 if ep_idx < 2 else 90  # proxy=300s, deepseek=90s
            with urllib.request.urlopen(req, timeout=call_timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            content = result['choices'][0]['message']['content'].strip()
            for prefix in ("```json", "```"):
                if content.startswith(prefix):
                    content = content.split("\n", 1)[1] if "\n" in content else content[len(prefix):]
            if content.endswith("```"):
                content = content.rsplit("```", 1)[0]
            parsed = json.loads(content.strip())
            print(f"    → {endpoint['name']} OK", file=sys.stderr)
            return parsed, endpoint['name']
        except Exception as e:
            print(f"    → {endpoint['name']} failed: {e}", file=sys.stderr)
            _demoted.add(ep_idx)  # skip this endpoint for the rest of the run
            continue

    return None, None


def compute_weighted_score(analysis):
    """Compute weighted interest score."""
    total = 0
    rel = analysis.get('relevance', {})
    for domain in INTEREST_DOMAINS:
        total += rel.get(domain['name'], 0) * domain['weight']
    return total


def filter_papers(papers_with_analysis):
    """Apply filtering rules to select papers for the briefing."""
    tiers = {"Tier-1": [], "Tier-2": [], "Tier-3": [], "Tier-4": []}
    for paper, analysis in papers_with_analysis:
        tier = analysis.get('tier', 'Tier-4')
        if tier not in tiers:
            tier = 'Tier-4'
        analysis['weighted_score'] = compute_weighted_score(analysis)
        tiers[tier].append((paper, analysis))

    selected = []

    # Rule 1: All Tier-1
    selected.extend(tiers["Tier-1"])

    # Rule 2: Tier-2 with any interest (score > 0)
    for paper, analysis in tiers["Tier-2"]:
        if analysis['weighted_score'] > 0:
            selected.append((paper, analysis))

    # Rule 3: Tier-3 and Tier-4 top 10% by weighted score
    lower = tiers["Tier-3"] + tiers["Tier-4"]
    if lower:
        lower.sort(key=lambda x: x[1]['weighted_score'], reverse=True)
        count = max(1, len(lower) // 10)
        selected.extend(lower[:count])

    return selected


def format_briefing(selected, total_fetched, endpoint_stats=None):
    """Format the final markdown briefing."""
    now_bj = datetime.now(BEIJING_TZ)
    date_str = now_bj.strftime("%Y-%m-%d")

    lines = [
        f"📄 **arXiv 天体物理日报** | {date_str}",
        "",
        f"📊 今日扫描 {total_fetched} 篇新投稿，入选 {len(selected)} 篇",
        "",
    ]

    tier_labels = [
        ("Tier-1", "🔴 重大突破"),
        ("Tier-2", "🟠 重要综述/重要进展"),
        ("Tier-3", "🟡 项目更新（精选）"),
        ("Tier-4", "⚪ 一般工作报告（精选）"),
    ]

    for tier_key, tier_label in tier_labels:
        tier_papers = [(p, a) for p, a in selected if a.get('tier') == tier_key]
        if not tier_papers:
            continue
        tier_papers.sort(key=lambda x: x[1]['weighted_score'], reverse=True)
        lines.append(f"━━━ {tier_label} ━━━")
        lines.append("")
        for i, (paper, analysis) in enumerate(tier_papers, 1):
            summary = analysis.get('summary_cn', '（无简介）')
            # Find best matching domain tag
            rel = analysis.get('relevance', {})
            best_domains = sorted(
                [(d, rel.get(d['name'], 0)) for d in INTEREST_DOMAINS],
                key=lambda x: x[1], reverse=True
            )
            top_tags = [d['tag'] for d, score in best_domains if score >= 2]
            tag_str = ' '.join(top_tags) + ' | ' if top_tags else ''
            lines.append(f"**{i}.** {tag_str}{paper['title']}")
            lines.append(f"💡 {summary}")
            lines.append(f"🔗 {paper['url']}")
            lines.append("")

    # Domain stats
    lines.append("━━ 📊 领域覆盖 ━━")
    for domain in INTEREST_DOMAINS:
        count = sum(1 for p, a in selected
                    if a.get('relevance', {}).get(domain['name'], 0) >= 2)
        if count > 0:
            lines.append(f"  {domain['name']}: {count} 篇")

    # LLM endpoint usage footer
    if endpoint_stats:
        total_batches = sum(endpoint_stats.values())
        parts = []
        # Ordered: Waterfall Proxy, DeepSeek, z.ai
        for ep in LLM_ENDPOINTS:
            name = ep["name"]
            count = endpoint_stats.get(name, 0)
            if count > 0:
                pct = count * 100 // total_batches
                parts.append(f"{name} {count}/{total_batches}批({pct}%)")
        if parts:
            lines.append("")
            lines.append(f"⚡ LLM分类: {' · '.join(parts)}")

    return "\n".join(lines)


def _reported_ids_file():
    """Return today's dated reported-IDs file path (per-day isolation)."""
    today = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")
    return os.path.join(CACHE_DIR, f"reported_ids_{today}.json")


def load_reported_ids():
    """Load previously reported paper IDs (today only)."""
    cache_file = _reported_ids_file()
    if os.path.exists(cache_file):
        try:
            with open(cache_file) as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def save_reported_ids(ids):
    """Save reported paper IDs to today's dated file."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_file = _reported_ids_file()
    with open(cache_file, 'w') as f:
        json.dump(sorted(list(ids)), f)
    # Prune stale reported-IDs files older than 7 days
    _prune_stale_ids()


def _prune_stale_ids():
    """Remove reported-IDs files older than 7 days to prevent accumulation."""
    try:
        cutoff = datetime.now(BEIJING_TZ) - timedelta(days=7)
        for fname in os.listdir(CACHE_DIR):
            if not fname.startswith("reported_ids_") or not fname.endswith(".json"):
                continue
            # Parse date from filename: reported_ids_YYYY-MM-DD.json
            date_str = fname[len("reported_ids_"):-len(".json")]
            try:
                file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(
                    tzinfo=BEIJING_TZ
                )
                if file_date.date() < cutoff.date():
                    os.remove(os.path.join(CACHE_DIR, fname))
            except (ValueError, OSError):
                pass
    except OSError:
        pass


def main():
    force = any(a.startswith("--force") for a in sys.argv)
    cron_mode = "--cron" in sys.argv

    now_beijing = datetime.now(BEIJING_TZ)

    # === Cron mode: check retry state ===
    if cron_mode:
        state_file = os.path.join(CACHE_DIR, "retry_state.json")
        today_str = now_beijing.strftime("%Y-%m-%d")
        cutoff_beijing = now_beijing.replace(hour=15, minute=0, second=0, microsecond=0)

        state = {}
        if os.path.exists(state_file):
            try:
                with open(state_file) as f:
                    state = json.load(f)
            except:
                pass
        if state.get("date") != today_str:
            state = {"date": today_str, "done": False, "notified_hours": []}

        # Already reported today — silent exit
        if state.get("done"):
            print(f"[cron] 今日简报已推送，跳过", file=sys.stderr)
            return

        # Past 15:00 — give up
        if now_beijing >= cutoff_beijing:
            print("⚠️ arXiv日报 | 今天已过15:00，arXiv始终未更新。明天再试。")
            state["done"] = True
            with open(state_file, "w") as f:
                json.dump(state, f)
            return

    # === Check if feed is today ===
    is_today, feed_date_str = is_feed_today()

    if not is_today:
        msg = f"⏳ arXiv日报 | arXiv今日数据尚未更新（RSS日期：{feed_date_str or '未知'}），请稍后再试。"
        if cron_mode:
            current_hour = now_beijing.hour
            if current_hour not in state.get("notified_hours", []):
                next_hour = current_hour + 1
                if next_hour >= 15:
                    next_hint = "这是最后一次尝试"
                else:
                    next_hint = f"将于{next_hour}:00再次尝试"
                print(f"⏳ arXiv日报 | arXiv今日数据尚未更新（RSS日期：{feed_date_str or '未知'}），{next_hint}。")
                state.setdefault("notified_hours", []).append(current_hour)
                with open(state_file, "w") as f:
                    json.dump(state, f)
            else:
                print(f"[cron] 本小时已通知，跳过", file=sys.stderr)
        else:
            print(msg)
        return

    # === Feed is today — generate briefing ===
    print(f"  Feed is current ({feed_date_str}), fetching papers...", file=sys.stderr)
    all_papers = fetch_all_papers()

    if not all_papers:
        # Feed is dated "today" but every host returned zero items. arXiv
        # essentially never has a genuinely empty new-submission day, so this
        # is almost certainly a front-end RSS outage rather than "no papers".
        # Notify the user ONCE, then stay silent for the rest of the day so
        # we don't repeat the same warning every hour.
        if cron_mode:
            if not state.get("empty_notified"):
                print("⚠️ arXiv日报 | 今日RSS源返回空（疑似arXiv端临时故障），已尝试备用源仍未获取到数据，将在下个整点重试。")
                state["empty_notified"] = True
                with open(state_file, "w") as f:
                    json.dump(state, f)
            else:
                print("[cron] RSS空通知已发送，本小时跳过", file=sys.stderr)
        else:
            print("⚠️ arXiv日报 | RSS源返回空，疑似arXiv端故障，请稍后重试。")
        return

    # Dedup — cross-day: check today + past 7 days to prevent re-delivery
    today_reported_ids = load_reported_ids()
    # Load past 7 days' reported IDs for cross-day dedup (separate from today's save)
    cross_day_ids = set()
    for days_ago in range(1, 8):
        past_date = (now_beijing - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        past_file = os.path.join(CACHE_DIR, f"reported_ids_{past_date}.json")
        if os.path.exists(past_file):
            try:
                with open(past_file) as f:
                    cross_day_ids |= set(json.load(f))
            except Exception:
                pass
    all_reported_ids = today_reported_ids | cross_day_ids
    if force:
        new_papers = all_papers
    else:
        new_papers = [p for p in all_papers if p['id'] not in all_reported_ids]

    if not new_papers:
        print("📭 arXiv日报 | 今日扫描完成，无符合条件的新论文（已通过跨日去重过滤）。")
        if cron_mode:
            state["done"] = True
            with open(state_file, "w") as f:
                json.dump(state, f)
        return

    print(f"  {len(new_papers)} papers to analyze (total fetched: {len(all_papers)})", file=sys.stderr)

    # LLM analysis in batches
    batch_size = 12
    all_analyses = []
    endpoint_stats = {}  # Track which LLM endpoint handled each batch
    total_batches = (len(new_papers) + batch_size - 1) // batch_size

    for i in range(0, len(new_papers), batch_size):
        batch = new_papers[i:i + batch_size]
        batch_idx = i // batch_size + 1
        print(f"  Batch {batch_idx}/{total_batches} ({len(batch)} papers)...", file=sys.stderr)

        analyses, ep_name = classify_batch(batch, batch_idx, total_batches)
        if ep_name:
            endpoint_stats[ep_name] = endpoint_stats.get(ep_name, 0) + 1
        if analyses and isinstance(analyses, list):
            for a in analyses:
                idx = a.get('paper_index', 0) - 1
                if 0 <= idx < len(batch):
                    all_analyses.append((batch[idx], a))
        else:
            for j, p in enumerate(batch):
                all_analyses.append((p, {
                    'tier': 'Tier-4',
                    'relevance': {d['name']: 0 for d in INTEREST_DOMAINS},
                    'summary_cn': f"标题：{p['title'][:80]}",
                }))

    # Filter and format
    selected = filter_papers(all_analyses)
    briefing = format_briefing(selected, len(all_papers), endpoint_stats)

    # Print briefing first, then save state
    print(briefing)

    # Save IDs — only today's new papers, not the cross-day union
    save_reported_ids(today_reported_ids | {p['id'] for p in new_papers})

    # Mark done (cron mode)
    if cron_mode:
        state["done"] = True
        with open(state_file, "w") as f:
            json.dump(state, f)


if __name__ == "__main__":
    main()
