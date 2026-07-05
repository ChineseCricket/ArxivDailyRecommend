# Historical arXiv Briefing Generation

When the daily cron fails and the user asks to 补发 (re-send) briefings for past dates, RSS feeds
cannot be used because arXiv only serves the current day's feed. Use these approaches instead.

## OAI-PMH for astro-ph (reliable, large volume)

The arXiv OAI-PMH endpoint reliably returns all papers for a specific date in a given category:

```
https://export.arxiv.org/oai2?verb=ListRecords
  &metadataPrefix=arXiv
  &set=physics:astro-ph
  &from=YYYY-MM-DD
  &until=YYYY-MM-DD
```

Returns OAI Dublin Core + arXiv metadata XML. Supports resumption tokens for
large result sets. Rate limit: ~1 req / 3 seconds.

**Python parser:**
```python
import urllib.request, xml.etree.ElementTree as ET

ns = {
    'oai': 'http://www.openarchives.org/OAI/2.0/',
    'arxiv': 'http://arxiv.org/OAI/arXiv/'
}

url = f"https://export.arxiv.org/oai2?verb=ListRecords&metadataPrefix=arXiv&set=physics:astro-ph&from={date_str}&until={date_str}"
root = ET.fromstring(urllib.request.urlopen(url).read())

papers = []
for record in root.findall('.//oai:record', ns):
    header = record.find('oai:header', ns)
    meta = record.find('.//arxiv:arXiv', ns)
    if header is None or meta is None: continue
    
    aid = header.find('oai:identifier', ns).text.replace('oai:arXiv.org:', '')
    title = meta.find('arxiv:title', ns).text.strip().replace('\n', ' ')
    abstract = meta.find('arxiv:abstract', ns).text.strip()
    authors = [a.find('arxiv:keyname', ns).text 
              for a in meta.findall('arxiv:authors/arxiv:author', ns)]
    cats = meta.find('arxiv:categories', ns).text.split()
    
    papers.append({'id': aid, 'title': title, 'abstract': abstract,
                   'authors': authors, 'categories': cats})

# Check for resumption token for pagination
rt = root.find('.//oai:resumptionToken', ns)
if rt is not None and rt.text:
    # Fetch next page with: &resumptionToken={rt.text}
    ...
```

**Volume:** astro-ph typically has 300-450 papers per day. For practical display,
random-sample to ~30 papers if full LLM classification is not feasible.

## arXiv API for ins-det and supr-con (smaller volume)

For the smaller detector/superconductivity categories, the standard arXiv API
with date + category queries is adequate (≤30 papers per category per day):

```
https://export.arxiv.org/api/query?
  search_query=cat:cond-mat.supr-con+AND+submittedDate:[202606150000+TO+202606160000]
  &max_results=200
```

**Caveat:** Date filtering is unreliable for high-volume categories (astro-ph).
Only use this for ins-det and cond-mat.supr-con.

## LLM Classification at Scale

Historical briefings involve 100-400+ papers per date. Full LLM classification
takes 5-15 minutes per date (10-12 papers per batch, 1-3s per batch via proxy's
steady-fallback combo). This may exceed execute_code timeout (300s).

**Options:**
1. **Background process** — write a standalone script, run via `terminal(background=true, notify_on_complete=true)`. Ensure Python output is unbuffered (`-u` flag) and use `sys.stderr.flush()` after each batch.
2. **Simplified listing** — present papers with titles + abstracts, grouped by category, without LLM classification. Use random sampling to keep output manageable.
3. **Pre-filter aggressively** — for detector categories, the keyword filter is strict enough to reduce volume drastically (often to 0-3 papers).

## Cross-reference

When cron delivery fails with "技术原因", see `devops/cron-delivery-debug` skill
for the full diagnostic checklist, including the Tirith GLIBC incompatibility
(cause #8) that triggered the terminal block in this session.
