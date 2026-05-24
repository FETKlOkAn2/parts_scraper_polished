# Production tuning knobs

This document captures the lessons from the first US deployment of the
pipeline — the kind of "I learned this at 3am" details that don't fit
in the architectural docs but matter once you put real workloads
through the system.

All knobs are environment variables. Defaults are tuned for a new
deployment that wants to run reliably first and optimise cost later;
turn them up only when you have evidence the current setting is the
bottleneck.

## OpenAI Batch sizing

| Var | Default | What it does |
| --- | --- | --- |
| `OPENAI_BATCH_MAX_ITEMS` | `2000` | Hard cap on how many image classifications go into one OpenAI batch. |
| `WATERMARK_ENSEMBLE_SIZE` | `1` | How many independent classifier runs per image. Majority vote. |
| `OPENAI_EMBED_IMAGES` | unset | When `true`, downloads each image and sends it base64-embedded in the batch instead of by URL. |

**Why the 2000 ceiling.** OpenAI's Batch API enforces a per-batch
limit that depends on request payload. With image URLs the practical
ceiling is around 2,500 items per batch. Earlier revisions of this
codebase defaulted to 40,000, which caused silent batch rejections
once a customer's catalogue grew past the first chunk. 2,000 leaves
headroom; tune up if your org's limit has been raised.

**The ensemble option.** Setting `WATERMARK_ENSEMBLE_SIZE=N` (max 10)
sends each image through the classifier N times with varied prompts
and temperatures, then majority-votes. Field experience: N=1 lands at
~5% false positives; N=3-5 lands at ~2%. Linear cost scaling, so this
is a quality knob for runs where false positives are expensive
(e.g. catalogues where every flagged image is reviewed manually).

**Base64 embedding.** With `OPENAI_EMBED_IMAGES=true`, the operator
console downloads each image and sends it inside the request body as
a `data:image/png;base64,…` URL instead of a regular S3 URL. In field
deployments this has cut OpenAI token consumption by roughly 5x
(observed: 80k → 16k tokens for a 10-image request set). Trade-off:
your network has to carry the image bytes from your workstation to
OpenAI rather than from S3. Worth it when the operator workstation
has good upstream bandwidth and the catalogue is large.

## Scraper sizing

| Var | Default | What it does |
| --- | --- | --- |
| `MAX_IMAGES_PER_PART` | `5` | How many candidate images to download per part. |
| `SEARCH_BACKEND` | `bing` | `bing` or `duckduckgo`. |

**Why the 5-image default.** The original code pulled 10 per part.
The first US deployment found that the perceptual-hash dedup discards
most of them anyway — pulling 10 doubled the downstream classifier
spend without measurably improving final image quality. 5 is a sweet
spot.

**The DuckDuckGo backend.** Bing's image search has a tendency to
"poison" the response stream when it detects a sustained scraping
pattern: instead of blocking outright, it starts returning generic
nature shots that look like real results to the parser. The first US
deployment had to switch to DuckDuckGo mid-run to recover. The
codebase now supports both via `SEARCH_BACKEND=duckduckgo`; the
operator can flip the env and resubmit the affected shards.

If you ever see a shard's images suddenly all look like the same
generic stock photo, suspect poisoning and switch backends.

## Shard distribution

| Var | Default | What it does |
| --- | --- | --- |
| `SHARD_STRATEGY` | `interleaved` | `interleaved` (round-robin) or `block` (contiguous). |

**Why interleaved.** With block sharding (the historical default),
shard k gets part_ids `k*chunk_size` to `(k+1)*chunk_size`. If a
search backend starts poisoning the stream at part #1234, every
contaminated image lands in one shard and you can't tell where the
contamination started without inspecting every image manually.

With interleaved sharding, shard k gets indices `k, k+num_chunks,
k+2*num_chunks, …`. Poisoning that begins at "the Nth pull from the
backend" shows up as "every shard has bad images starting at row N",
which immediately pinpoints the affected range and the boundary. The
cost of identifying and isolating corruption drops from "discard the
entire run" to "discard rows >= N in each shard".

This is the rolling-split design from the first US deployment's
post-mortem. New deployments default to interleaved; existing
deployments can set `SHARD_STRATEGY=block` to keep the old behaviour
if they have downstream tooling that assumes contiguous part ids per
shard.

## Sizing your first managed run

Realistic numbers for a Slovak SMB e-shop with 20–50k SKU:

- 20k parts × 5 images = 100k images → ~50 OpenAI batches at 2k each
- OpenAI batch completion: typically 1–3 hours
- With 10 concurrent batches: ~5–15 hours wall clock for the
  watermark stage
- EC2 worker fleet with target tracking handles the search and
  filter stages in parallel; the OpenAI batch is the bottleneck

If a customer has 200k+ SKU, expect 3–7 days end-to-end at the
default settings. Lower `MAX_IMAGES_PER_PART` to 3, leave
`WATERMARK_ENSEMBLE_SIZE` at 1, and ask the OpenAI org for a higher
concurrent-batch limit before quoting a delivery date.

## What you don't get yet

- Automated detection of search-backend poisoning. The interleaved
  shard layout makes it diagnosable; flipping `SEARCH_BACKEND` is
  manual.
- Cross-batch concurrency control. OpenAI applies its own per-org
  cap; the operator console submits all batches at once and lets
  OpenAI queue them.
- Smart fallback that combines local CV heuristics with the OpenAI
  classifier (which would let `WATERMARK_ENSEMBLE_SIZE=1` give
  ensemble-equivalent precision). See Section 22 of the
  consultant-facing documentation for the broader extension paths.
