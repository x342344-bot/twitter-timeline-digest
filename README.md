# twitter-timeline-digest

An open-source pipeline for pulling your X/Twitter timeline through CDP, filtering the noise, and turning it into an AI digest.

## Architecture

```text
Logged-in Chrome tab
        |
        v
CDP websocket (Runtime.evaluate)
        |
        v
In-page GraphQL fetch
(Following + For You x 5 scroll rounds)
        |
        v
raw_YYYY-MM-DD.json
        |
        v
prefilter.py
(keywords / big accounts / engagement)
        |
        v
candidates_YYYY-MM-DD.json
        |
        +--> buzz.py (multi-author handle/ticker aggregation)
        |
        v
scoring.py + dedup.py
        |
        v
Top candidates payload
        |
        v
OpenAI / Anthropic
        |
        v
Digest JSON + stdout / optional webhook
```

## What this is

This repo shares the general architecture behind a timeline monitoring stack:

- fetch authenticated timeline data from a logged-in browser
- prefilter with cheap rules
- score for relevance
- deduplicate repeated events
- aggregate buzz across authors
- hand a much smaller set to an LLM for final digesting

It is intentionally sanitized:

- no cookies
- no private prompts
- no Discord or Telegram delivery code
- no embedded bearer token
- no private keyword universe

## Quick start

1. Start Chrome with remote debugging enabled.
   - Example: `Google Chrome --remote-debugging-port=9222`
2. Log into X/Twitter in that browser and keep the home timeline tab open.
3. Copy `config.example.yaml` to `config.yaml` and fill in your CDP target and GraphQL query IDs.
4. Export required secrets:
   - `export TWITTER_BEARER_TOKEN='...'`
   - `export OPENAI_API_KEY='...'` or `export ANTHROPIC_API_KEY='...'`
5. Run:
   - `python3 scripts/health_check.py --config config.yaml`
   - `python3 scripts/run_fetch.py --config config.yaml`
   - `python3 scripts/run_digest.py --config config.yaml`

## Configuration

### Required

- `cdp.host` / `cdp.port`: the local Chrome DevTools endpoint
- `cdp.target_id`: target tab id from `http://HOST:PORT/json/list`
- `twitter.graphql.following_query_id`
- `twitter.graphql.for_you_query_id`
- `TWITTER_BEARER_TOKEN` environment variable

### Optional but important

- `filters.keywords.must`
- `filters.keywords.interest`
- `filters.big_accounts`
- `filters.institutional_accounts`
- `scoring.*`
- `buzz.min_authors`
- `digest.provider`
- `digest.model`

## Typical funnel

A typical run looks like this:

- `10,000` raw tweets across a day
- `6,000` candidate tweets after cheap filtering
- `300-800` strong scored items after event deduplication
- `25` final digest items after the LLM step

The exact ratio depends on your keyword list, timeline quality, and how aggressive you make the rules.

## How it works

### 1. `src/fetch_timeline.py`

- opens a CDP websocket directly: `ws://localhost:{CDP_PORT}/devtools/page/{TARGET_ID}`
- uses `Runtime.evaluate` to inject JavaScript into the logged-in timeline tab
- calls X/Twitter GraphQL endpoints from inside the page context
- pulls both the Following timeline and the For You timeline
- scrolls the For You feed for 5 rounds by default
- stores raw tweets and candidate tweets as JSON

### 2. `src/prefilter.py`

Fast hard rules. A tweet passes if it matches one of these buckets:

- high engagement
- known big account
- large follower count
- must-have keyword hit
- broader interest keyword hit
- softer engagement + ticker fallback

### 3. `src/scoring.py`

Ranking layer with explicit boosts:

- crypto boost
- alpha boost
- institutional floor
- For You boost
- selective boosts for ETF flow, wallets/payments, compliance, and security

### 4. `src/dedup.py`

Clusters repeated tweets into rough event fingerprints so the same story does not dominate the digest just because ten accounts repeated it.

### 5. `src/buzz.py`

Counts repeated mentions of handles and tickers across authors. Useful for catching emergent attention before it turns into a full narrative.

### 6. `src/digest.py`

Builds a compact JSON payload and sends it to either OpenAI or Anthropic. The prompt template lives in `prompts/digest.md`.

### 7. `src/storage.py`

Atomic JSON writes, per-day partitioning, and retention cleanup.

## Notes on X/Twitter internals

This project avoids shipping hardcoded private data, so you must provide your own:

- a valid logged-in browser session
- the bearer token via `TWITTER_BEARER_TOKEN`
- current GraphQL query IDs for Following and For You

X/Twitter rotates query ids and sometimes changes response shapes. Expect light maintenance.

## Output

The project only writes JSON and prints summaries to stdout.

If you want delivery, add it in your own wrapper:

- cron job
- webhook
- email
- Slack
- anything else

Keeping delivery out of the core repo makes the open-source version safer and more portable.

## Contributing

PRs are welcome for:

- response-shape fixes when X/Twitter changes
- better event dedup logic
- lower-cost scoring heuristics
- provider adapters beyond OpenAI / Anthropic
- documentation and example configs

## License

MIT
t maintenance.

## Output

The project only writes JSON and prints summaries to stdout.

If you want delivery, add it in your own wrapper:

- cron job
- webhook
- email
- Slack
- anything else

Keeping delivery out of the core repo makes the open-source version safer and more portable.

## Contributing

PRs are welcome for:

- response-shape fixes when X/Twitter changes
- better event dedup logic
- lower-cost scoring heuristics
- provider adapters beyond OpenAI / Anthropic
- documentation and example configs

## License

MIT
