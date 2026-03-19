# Customization

This repo is intentionally small, so most customization happens in `config.yaml`
and a few source files with obvious control points. The goal is to let you tune
recall, ranking, and delivery without rewriting the whole pipeline.

## Mental model

There are three layers you will usually change:

1. recall: what gets through prefilter
2. ranking: what gets scored highest
3. delivery: where the final digest goes after JSON is produced

Change them in that order. If recall is bad, no scoring tweak will save you.

## 1. Add or refine keywords

Keywords live under `filters.keywords` in `config.yaml`.

Example:

```yaml
filters:
  keywords:
    must:
      - btc
      - bitcoin
      - solana
      - stablecoin
    interest:
      - etf
      - payment
      - wallet
      - exploit
      - rwa
```

Guidelines:
- keep `must` short and high-signal
- use `interest` for broader recall
- prefer lower-case plain strings unless your matcher is explicitly regex-based
- review false positives every few runs before adding more terms

A good pattern:
- `must` = core topics you never want to miss
- `interest` = adjacent topics that may matter depending on context

A bad pattern:
- dumping every buzzword you can think of into both lists

## 2. Adjust scoring weights

Most ranking behavior is controlled from `scoring` in `config.yaml` plus regexes in
`src/scoring.py`.

Typical config shape:

```yaml
scoring:
  crypto_boost: 1.4
  alpha_boost: 1.25
  for_you_boost: 0.85
  institutional_floor: 60
  selective_boosts:
    etf_flow: 1.2
    payment_wallet: 1.15
    compliance: 1.1
    security: 1.3
```

How to think about the knobs:
- `crypto_boost`: broad multiplier for crypto-native content
- `alpha_boost`: stronger emphasis on launches, exploits, listings, funding, etc.
- `for_you_boost`: usually below `1.0` if you trust Following more than recommendations
- `institutional_floor`: prevents major accounts from being under-ranked on low raw engagement
- `selective_boosts.*`: category-level tilt without rewriting the base formula

Practical workflow:
- change one multiplier at a time
- run one or two real fetches
- inspect top 20 scores manually
- keep notes on what moved up or down

## 3. Add a new boost category

If you want a new thematic boost, edit `src/scoring.py`.

Pattern:

1. define a new regex near the top
2. add a config key under `selective_boosts`
3. apply the multiplier inside `score_tweet()`

Example for an AI-infra category:

```python
AI_INFRA_RE = re.compile(r"gpu|inference|training|model serving|datacenter", re.I)
```

Then inside scoring:

```python
if AI_INFRA_RE.search(lower):
    base *= selective["ai_infra"]
```

And in config:

```yaml
scoring:
  selective_boosts:
    ai_infra: 1.2
```

Rule of thumb:
- add a category only when you can explain why it should systematically outrank peers
- if a tweak is very temporary, prefer changing keywords instead

## 4. Expand ticker filtering logic

Ticker/cashtag behavior lives in `src/scoring.py` as well.

`COMMON_STOCKS` exists to avoid over-triggering on obvious large-cap cashtags.
If your universe overlaps more with equities or macro, update that set.

Examples of when to expand it:
- you follow many macro/equity accounts
- `$SPY` and `$QQQ` dominate otherwise-good crypto/news ranking
- you want to avoid treating common finance shorthand as special alpha

## 5. Switch AI provider

Provider routing happens in `src/digest.py` and config.

Example config:

```yaml
digest:
  provider: openai
  model: gpt-4.1-mini
  api_key_env: OPENAI_API_KEY
  anthropic_api_key_env: ANTHROPIC_API_KEY
  prompt_path: prompts/digest.md
  output_count: 25
```

To switch to Anthropic:

```yaml
digest:
  provider: anthropic
  model: claude-sonnet-4-5
```

What changes when you switch providers:
- endpoint and request shape
- model name
- env var used for auth

What should not change:
- payload schema
- prompt intent
- downstream JSON contract

If you add a new provider, keep the adapter isolated in `src/digest.py`.
Do not leak provider-specific assumptions into scoring or storage.

## 6. Change the prompt safely

Prompt text lives in `prompts/digest.md`.

Safe edits:
- tighten selection criteria
- change tone and formatting
- require a stricter output schema
- ask for more explicit clustering or prioritization

Unsafe edits:
- asking for huge narrative summaries of hundreds of tweets
- mixing delivery formatting with selection logic
- depending on private context that is not in the payload

The payload is intentionally compact. Keep the prompt aligned with that.

## 7. Add webhook delivery

The repo intentionally stops at JSON/stdout, but adding a webhook wrapper is easy.
The cleanest pattern is a separate script that reads the digest output and posts it.

Minimal Python example:

```python
import json
import requests
from pathlib import Path

payload = json.loads(Path("data/digest_2026-03-18.json").read_text())
requests.post(
    "https://example.com/webhook",
    json=payload,
    timeout=15,
).raise_for_status()
```

Minimal curl example:

```bash
curl -X POST https://example.com/webhook \
  -H 'Content-Type: application/json' \
  --data @data/digest_2026-03-18.json
```

Recommendation:
- keep webhook delivery outside the core fetch/rank/digest modules
- retries and alerting belong in the wrapper layer
- log response codes so failures are debuggable

## 8. Add Slack / Discord / Telegram later

Treat those exactly like webhook delivery:
- wrapper script reads digest JSON
- transforms it into channel-specific formatting
- posts it with a channel-specific client

Do not hardwire chat delivery into `src/digest.py`.
That keeps the repo portable and easier to open-source.

## 9. Schedule with cron

A simple cron entry can run the whole pipeline on an interval.

Example:

```cron
*/30 * * * * cd /path/to/twitter-timeline-digest && \
  /usr/bin/python3 scripts/run_fetch.py --config config.yaml >> logs/fetch.log 2>&1

5 * * * * cd /path/to/twitter-timeline-digest && \
  /usr/bin/python3 scripts/run_digest.py --config config.yaml >> logs/digest.log 2>&1
```

Tips:
- use absolute paths in cron
- export env vars before cron or source them from a file
- write stdout/stderr to log files
- stagger fetch and digest so the second stage sees fresh data

## 10. Schedule with launchd on macOS

For a Mac-native setup, `launchd` is usually better than cron.

High-level pattern:
- create a plist in `~/Library/LaunchAgents/`
- set `ProgramArguments` to your Python command
- set `WorkingDirectory` to the repo
- set `StartInterval` or calendar-based triggers
- set `StandardOutPath` and `StandardErrorPath`

Example snippet:

```xml
<key>ProgramArguments</key>
<array>
  <string>/usr/bin/python3</string>
  <string>scripts/run_fetch.py</string>
  <string>--config</string>
  <string>config.yaml</string>
</array>
<key>WorkingDirectory</key>
<string>/path/to/twitter-timeline-digest</string>
<key>StartInterval</key>
<integer>1800</integer>
```

Use `launchctl load` / `unload` or modern `bootstrap` workflows to manage it.

## 11. Tune the funnel with real numbers

Do not customize blindly. Track a few numbers every run:

- raw count
- candidate count
- deduped count
- final digest count
- percent of final digest items you would actually have wanted to read

Best practice:
- keep a short changelog of config tweaks
- compare before/after for at least a few runs
- optimize for decision usefulness, not just more output

## 12. Where to edit what

Use this cheat sheet:

- recall too low or too noisy → `filters.keywords.*`, prefilter thresholds
- ranking feels wrong → `scoring.*`, `src/scoring.py`
- common story repeats too much → `src/dedup.py`
- emergent themes missing → `src/buzz.py`
- digest tone/schema wrong → `prompts/digest.md`
- model/provider issues → `src/digest.py`
- posting to external systems → wrapper scripts, not core modules

That separation is the point. Keep each layer boring and obvious.