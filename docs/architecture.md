# Architecture

## Overview

This project is a thin pipeline around one core idea: reuse your existing logged-in
X/Twitter browser tab, pull timeline data through CDP, reduce it aggressively with
cheap heuristics, then let an LLM produce the final digest from a much smaller set.

The design goal is pragmatic rather than elegant:

- keep the fetch path explicit
- keep state on disk as JSON
- keep dependencies minimal
- keep delivery out of the core repo
- keep private data outside source control

## End-to-end data flow

```text
┌─────────────────────────────┐
│ Logged-in Chrome tab        │
│ x.com/home                  │
└──────────────┬──────────────┘
               │ existing auth state
               v
┌─────────────────────────────┐
│ CDP websocket               │
│ Runtime.evaluate            │
└──────────────┬──────────────┘
               │ inject JS into page
               v
┌─────────────────────────────┐
│ In-page GraphQL fetch       │
│ Following + For You         │
│ ct0 cookie + bearer token   │
└──────────────┬──────────────┘
               │ normalized tweet dicts
               v
┌─────────────────────────────┐
│ raw_YYYY-MM-DD.json         │
│ append-only day partition   │
└──────────────┬──────────────┘
               │
               v
┌─────────────────────────────┐
│ prefilter.py                │
│ cheap pass / fail rules     │
└──────────────┬──────────────┘
               │ candidates
               ├──────────────────────┐
               │                      │
               v                      v
┌─────────────────────────────┐  ┌─────────────────────────────┐
│ dedup.py                    │  │ buzz.py                     │
│ event clustering            │  │ multi-author entity counts  │
└──────────────┬──────────────┘  └──────────────┬──────────────┘
               │                                │
               └──────────────┬─────────────────┘
                              v
                   ┌─────────────────────────────┐
                   │ scoring.py                  │
                   │ relevance ranking           │
                   └──────────────┬──────────────┘
                                  │ top payload
                                  v
                   ┌─────────────────────────────┐
                   │ digest.py                   │
                   │ OpenAI / Anthropic          │
                   └──────────────┬──────────────┘
                                  │ digest JSON
                                  v
                   ┌─────────────────────────────┐
                   │ stdout / webhook wrapper    │
                   │ optional downstream output  │
                   └─────────────────────────────┘
```

## Module responsibilities

### `src/fetch_timeline.py`

Responsibility:
- connect directly to the Chrome DevTools Protocol websocket
- inject JavaScript into the already-authenticated page
- fetch Following and For You timelines through in-page GraphQL requests
- normalize raw response entries into compact tweet dictionaries
- persist raw output and prefiltered candidates

Inputs:
- `config.yaml`
- `TWITTER_BEARER_TOKEN`
- active Chrome tab with a valid X/Twitter session
- GraphQL query ids and operation names

Outputs:
- in-memory `following` list
- in-memory `for_you` list
- `raw_YYYY-MM-DD.json`
- `candidates_YYYY-MM-DD.json`
- summary counts for CLI/logging

Important implementation notes:
- fetch uses the page's own `document.cookie` to read `ct0`
- bearer token is injected into page context as `globalThis.__OPEN_SOURCE_BEARER`
- feed-level dedup happens inside `fetch_feed()`
- cross-feed dedup happens in `run_fetch()` with Following taking priority

### `src/prefilter.py`

Responsibility:
- perform cheap screening before any heavier ranking or model calls
- allow tweets through when they satisfy obvious relevance signals

Inputs:
- normalized raw tweet dicts
- keyword lists
- account allowlists
- engagement thresholds

Outputs:
- candidate tweet list that is materially smaller than raw input

Typical rules:
- must-have keyword hits
- broader interest keyword hits
- big-account passes
- engagement-driven passes
- ticker/fallback passes

### `src/scoring.py`

Responsibility:
- turn candidate tweets into a sorted list with explicit score boosts
- encode opinionated ranking knobs that are easy to modify

Inputs:
- candidate tweets
- config scoring weights
- optional mention counts from dedup/buzz stages

Outputs:
- `score` field attached to each tweet
- descending relevance ranking

Current scoring dimensions:
- likes / retweets / follower base
- crypto text boost
- alpha / launch / exploit style boost
- selective boosts for ETF flow, payments, compliance, security
- institutional floor
- For You source multiplier
- mention-count multiplier

### `src/dedup.py`

Responsibility:
- collapse repeated tweets about the same event into a smaller cluster set
- prevent one news item from dominating purely due to repetition

Inputs:
- candidate tweets after prefilter

Outputs:
- event keys / grouped tweets / reduced set for ranking or digesting

### `src/buzz.py`

Responsibility:
- detect repeated mentions of handles or tickers across distinct authors
- surface emergent topics before they become fully obvious

Inputs:
- candidate or deduped tweets

Outputs:
- buzz aggregates with author counts and entity labels

### `src/digest.py`

Responsibility:
- build the LLM payload
- choose provider adapter
- parse final JSON output

Inputs:
- scored tweets
- buzz aggregates
- prompt template
- provider config and API key env var

Outputs:
- digest JSON object ready for downstream printing or delivery

Provider behavior:
- OpenAI uses `/v1/chat/completions`
- Anthropic uses `/v1/messages`
- both adapters expect valid JSON output from the model

### `src/storage.py`

Responsibility:
- atomic JSON writes
- date-partitioned file naming
- retention cleanup

Inputs:
- lists of raw tweets, candidates, or digest artifacts
- storage settings from config

Outputs:
- stable files under `data/`
- cleanup of older partitions beyond retention

## File naming conventions

The repo keeps storage intentionally boring. That is a feature.

Conventions:
- `raw_YYYY-MM-DD.json`: all newly fetched tweets for the day
- `candidates_YYYY-MM-DD.json`: prefilter output for the day
- `digest_YYYY-MM-DD.json`: final digest artifacts if your wrapper stores them
- `config.example.yaml`: safe template for public use
- `config.yaml`: local private config, ignored by git
- `prompts/digest.md`: digest selection prompt

Why date suffixes instead of timestamp-heavy paths:
- easy manual inspection
- easy cron-friendly appends
- easy retention cleanup
- easy diffing between days

## Typical funnel numbers

A realistic daily run looks roughly like this:

- raw fetch: `8,000-12,000` tweets across both feeds
- prefilter survivors: `3,000-6,000`
- post-dedup / strong scored items: `300-800`
- LLM payload candidates: `50-150`
- final digest: `10-25` items

The exact funnel depends on:
- how broad your keyword universe is
- how chaotic your Following graph is
- how much weight you give For You content
- whether the market/news cycle is unusually active

A useful rule: if prefilter keeps more than ~60% of raw tweets, your rules are too loose.
If it keeps less than ~10%, your rules are probably too brittle.

## Control surfaces and extension points

This repo is deliberately modular. The easiest extension points are:

1. `prefilter.py`
   - add new pass buckets
   - tighten or loosen early recall
   - support domain-specific keyword classes

2. `scoring.py`
   - add new regex families
   - adjust multipliers
   - add penalties as well as boosts
   - treat account cohorts differently

3. `dedup.py`
   - improve clustering
   - add URL-based or semantic event grouping
   - merge quote-tweet variants more aggressively

4. `buzz.py`
   - support sectors, themes, wallet labels, protocol names
   - require stronger author diversity before counting buzz

5. `digest.py`
   - add Gemini / local model adapters
   - add retries, backoff, validation, or schema enforcement
   - cache model outputs for repeated runs

6. wrapper scripts
   - add webhook delivery
   - add Slack / Discord / Telegram posting
   - add observability and alerts

## Failure boundaries

When the pipeline breaks, the failure is usually in one of four places:

1. Chrome/CDP connectivity
   - remote debugging not enabled
   - wrong target id
   - stale websocket target

2. X/Twitter fetch shape drift
   - query id rotated
   - response instruction shape changed
   - auth state expired

3. local config drift
   - missing env vars
   - bad YAML edits
   - wrong prompt path or data dir

4. provider/API drift
   - model name invalid
   - output not valid JSON
   - rate limiting or auth problems

Keeping raw/candidate artifacts on disk makes these failures debuggable.

## Design tradeoffs

This project intentionally does not:
- ship delivery integrations
- ship private keyword universes
- ship browser profile automation
- hide that it depends on X/Twitter internal endpoints

That keeps the open-source version honest. The core value is the funnel design,
not pretending the upstream dependencies are stable.
