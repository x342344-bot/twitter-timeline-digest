# Architecture

## Data flow

1. Connect to an already logged-in Chrome tab through the Chrome DevTools Protocol (CDP).
2. Inject JavaScript with `Runtime.evaluate`.
3. Reuse the tab's cookies and CSRF token to call the X/Twitter GraphQL timeline endpoints.
4. Fetch both Following and For You timelines.
5. Run hard-rule prefiltering.
6. Score, deduplicate, and aggregate buzz.
7. Send the reduced candidate set to an LLM for final digest selection.
8. Save all intermediate artifacts as JSON.

## Why CDP direct instead of full browser automation?

- Smaller dependency surface.
- Easier to run on any machine with Chrome.
- Works with an existing logged-in session.
- Keeps the fetch path explicit: CDP -> JS -> GraphQL.

## Core modules

- `src/fetch_timeline.py`: CDP websocket connection, JS injection, GraphQL fetch, raw storage.
- `src/prefilter.py`: cheap rule-based filtering to cut volume before AI.
- `src/scoring.py`: score boosts for crypto-native and alpha-heavy content.
- `src/dedup.py`: cluster repeated tweets into event-level units.
- `src/buzz.py`: detect entities mentioned by multiple authors.
- `src/digest.py`: call OpenAI or Anthropic and store JSON digest output.
- `src/storage.py`: atomic JSON persistence and cleanup.
