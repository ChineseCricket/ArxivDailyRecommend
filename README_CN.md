# arXiv 每日简报

[![English](https://img.shields.io/badge/English-README-blue)](README.md)

基于 arXiv RSS 的天体物理 & 超导探测器每日论文推送。自动抓取最新投稿，用大模型分类打分，生成个性化简报。

## 覆盖范围

| RSS 源 | 筛选方式 |
|--------|----------|
| `astro-ph` | 全部新投稿 |
| `physics.ins-det` | 仅保留探测器相关（TES、MKID、SQUID、bolometer 等） |
| `cond-mat.supr-con` | 仅保留探测器相关 |

论文按 **4 级重要性** 分级，按 **5 个兴趣领域** 加权打分后筛选输出。

## 快速开始

```bash
# Python 3.8+ 即可，零依赖（纯标准库）
python3 scripts/arxiv_daily_briefing.py --force
```

输出为 Markdown 格式的简报，直接打印到 stdout。

## 工作流程

1. 从 `export.arxiv.org/rss/` 抓取 3 个 RSS feed
2. 过滤公告类型（仅 "new"）和探测器关键词
3. 每 12 篇一批送入大模型分类
4. 筛选：全部 Tier-1 + 有匹配的 Tier-2 + Tier 3/4 中分数前 10%
5. 格式化输出简报

## 兴趣领域

| 权重 | 领域 | 说明 |
|------|------|------|
| ×5 | 🔬 超导探测器及其读出技术 | TES、MKID、KID、SQUID、多路复用、CMB 探测器 |
| ×4 | 🌫️ 弥散热气体 | WHIM、星系周介质、热晕、弥散 X 射线 |
| ×3 | 🔭 天文仪器与技术 | 望远镜设计、光谱仪、光学、定标 |
| ×2 | ⭐ X 射线恒星行星系统 | 星-行星相互作用、恒星耀斑、大气逃逸 |
| ×1 | 🌍 宜居世界与地外生命 | 宜居带、生物标志物、系外行星大气 |

## LLM 后端

脚本内置自适应三级降级：

| 优先级 | 端点 | 说明 |
|--------|------|------|
| 1 | Waterfall Proxy (`localhost:18900`) | 可选，可自行配置 |
| 2 | DeepSeek (`api.deepseek.com`) | 需设置环境变量 `DEEPSEEK_API_KEY` |
| 3 | z.ai GLM (`open.bigmodel.cn`) | 需设置环境变量 `GLM_API_KEY` |

当前端点失败自动降级到下一个。即使只配 DeepSeek 一个后端也能正常工作。

## 配置

编辑 `scripts/arxiv_daily_briefing.py`：

- `LLM_ENDPOINTS`（~33 行）— 添加/修改你的 LLM 后端
- `RSS_FEEDS`（~64 行）— 修改要监控的 arXiv 分类
- `DETECTOR_KEYWORDS_PATTERNS`（~74 行）— 调整关键词过滤
- `INTEREST_DOMAINS`（~90 行）— 自定义兴趣领域和权重

## 运行模式

```bash
# 手动强制模式 — 无视去重，始终生成新简报
python3 scripts/arxiv_daily_briefing.py --force

# 手动普通模式 — 仅展示未推送过的新论文
python3 scripts/arxiv_daily_briefing.py

# Cron 模式 — 北京时间 10:00-15:00 每小时重试，自动去重
python3 scripts/arxiv_daily_briefing.py --cron
```

## Hermes Agent 集成

本项目也是 [Hermes Agent](https://hermes-agent.nousresearch.com) 的 skill：

```
SKILL.md                         → Skill 定义
scripts/arxiv_daily_briefing.py  → 核心简报脚本
scripts/search_arxiv.py          → arXiv 搜索工具
references/daily-briefing.md     → 详细文档
```

配合 Hermes cron + 微信推送：

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
