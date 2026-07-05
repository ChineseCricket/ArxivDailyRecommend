# Cron Agent Prompt Discipline

## Problem

The arXiv cron agent sometimes ignores the "run script, deliver output" protocol
and instead performs extensive manual verification — reading retry_state.json,
reported_ids files, re-running scripts, and concluding incorrectly that results
are already reported. This wastes 20+ API calls and leads to missed deliveries.

## Root Cause

The default agent behavior is to "be helpful" by verifying and cross-checking.
When the prompt says "if stdout is empty AND stderr contains X → [SILENT]",
the agent may still decide to investigate WHY the output looks that way.

## Fix: Explicit FORBIDDEN Rules

The cron prompt must include explicit prohibitions, not just instructions:

```
RULES — follow EXACTLY, no exceptions:
1. The script handles ALL logic internally: date check, cross-day dedup, LLM 
   classification, retry_state tracking. Do NOT read state files, RSS feeds, 
   or reported_ids yourself. Do NOT re-run the script multiple times.
2. If stdout contains a briefing → deliver it AS-IS.
3. If stdout is empty AND stderr contains specific phrases → [SILENT].
4. If stdout has a status message → deliver that message.
5. FORBIDDEN: Do NOT read retry_state.json, reported_ids files, or RSS feeds.
   Do NOT verify the script's output. Do NOT investigate why the output looks 
   a certain way. The script IS the authority.
```

## Key Principle

The cron agent is a **delivery relay**, not a **quality inspector**.
The script already handles: timing, dedup, classification, formatting.
The agent's ONLY job is to run the script and pipe its output to WeChat.
