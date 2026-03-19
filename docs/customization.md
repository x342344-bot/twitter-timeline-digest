# Customization

## Keywords

Edit `filters.keywords.must` and `filters.keywords.interest` in `config.yaml`.
Keep the must-list short. If you overfit the keyword list, the candidate pool becomes noisy and defeats the point of prefiltering.

## Big accounts and institutional accounts

- `filters.big_accounts`: accounts that should always pass prefilter.
- `filters.institutional_accounts`: accounts that get a score floor in ranking.

## Digest prompt

Edit `prompts/digest.md` to change tone, output schema, or selection criteria.
Keep the prompt generic if you intend to open-source your setup.

## Output hooks

This project intentionally ships with stdout-first output.
If you want downstream delivery, wire a webhook in your own wrapper script instead of editing the core pipeline.

## Query IDs

X/Twitter rotates GraphQL query IDs from time to time.
When fetching breaks, inspect network requests in DevTools and update:

- `twitter.graphql.following_query_id`
- `twitter.graphql.for_you_query_id`
