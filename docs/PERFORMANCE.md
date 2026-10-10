# Performance and port decision

## Recommendation

Keep the Python backend for now. The measurements below do not justify a full Rust
port. A faster server will not remove a large browser rendering workload. Revisit
Rust in a separate session only after a browser/server profile identifies a CPU-bound
backend operation that remains slow after reducing unnecessary work.

## Changed-file anchoring · 2026-10-06

The previous reconciliation ran `SequenceMatcher(..., autojunk=False)` on the
entire old/new document separately for every attached source thread, while
holding the workspace lock. A disposable 60 KB repetitive edit exceeded a
two-second subprocess deadline for **one** thread. This matches the mechanism
behind the reported CPU spike and queued/time-out requests. Access logs alone
do not identify the exact edit or profile the original user's process.

Reconciliation now creates one mapper per changed file. It maps uniquely preserved
whole snapshots directly, caches exact quote/context searches, limits
ambiguity searches to two hits, and reuses results for shared selections.
Changed quotes require unique surviving outside context and substantial matching
text, excluding whitespace as evidence. Only a small changed middle is diffed:
at most 2,048 characters per side. Fuzzy comparisons share 1,000,000 work units
per file, charged for both full passage lengths and each middle's length product.
This also bounds linear scans of long, overlapping edited selections.
Exact/context searches share a 256 Mi-character worst-case scan allowance.
Short unique quotes inside verified unchanged document edges also keep their
positions when nearby content changes; repeated quotes still require context.
These are work limits, not wall-clock guarantees. Exhaustion marks uncertain
anchors for manual repair, with no retry on unchanged-file polls. The existing
workspace lock still serializes mutations; no background worker or new service
is needed to remove the unbounded diff.

Run `uv run python scripts/benchmark_anchors.py`. Five disposable workspaces per
case, 28 threads each; medians below include Flask test-client request handling,
file read, reconciliation, SQLite writes, and JSON serialization. They exclude
network and browser rendering. Moved passages are reordered and relocated across
the document; rewritten repetitive passages deliberately have ambiguous context.

| Source size | Edit | First changed request | Unchanged poll | Result |
| --- | --- | ---: | ---: | --- |
| 60 KB | Rewritten repetitive passages | 1.79 ms | 1.05 ms | 28 need repair |
| 61 KB | Moved unique exact passages | 2.33 ms | 0.92 ms | 28 attached |
| 2 MB | Rewritten repetitive passages | 21.68 ms | 4.09 ms | 28 need repair |
| 2 MB | Moved unique exact passages | 30.70 ms | 3.57 ms | 28 attached |

`agent reattach ID --quote 'Exact replacement passage'` provides the explicit
repair path, including corrections to an already attached wrong passage.
It uses the existing hash-checked PATCH route and preserves immutable origins,
messages, attachments, and resolved/open state. A semantic rewrite still needs
a reviewer or agent to choose the intended replacement. A Rust port would retain
the same ambiguity and does not address the underlying algorithmic problem.

## Measured discussion workload · 2026-10-04

Run `uv run python scripts/benchmark_discussions.py`. It creates a disposable
workspace with 100 files (about 65 KB each), 1,000 threads and one message per thread.
The following are medians of five local Flask test-client requests, including database
access, serialization and template rendering. They exclude network transfer, browser
layout and painting. These are diagnostic measurements, not timing assertions.

| Refresh path | Median | Source reads | Response body |
| --- | ---: | ---: | ---: |
| Legacy thread JSON + HTML fragment | 61.76 ms | 200 | 1,926,612 bytes |
| Combined discussion response | 36.82 ms | 0 | 2,118,538 bytes |
| Navigation index | 1.82 ms | 0 | 50,895 bytes |
| Unchanged discussion response | 7.41 ms | 0 | 0 bytes |

The earlier branch already batches message/attachment queries, avoids source reads
when browsing all discussions, caches scope responses, uses conditional requests,
and retains unchanged thread elements. File polling uses stat fingerprints and still
checks content hashes when saving. This session adds conditional file-tree refreshes:
unchanged trees retain their existing elements, filter, expansion and scroll state.
Failed directory scans report an error and preserve the last tree, rather than
masquerading as an empty workspace. A genuinely empty directory still displays empty.

## Next performance work, in order

1. Measure click-to-paint time and browser long tasks for 100, 1,000 and 10,000
   discussions, with multiple open files. Separate server time from browser time.
2. Reduce the initial all-discussions payload and number of rendered elements:
   page or virtualize the list, and fetch full messages/attachments when expanding
   a thread. Keep the small global navigation index so arrows still cross files.
   The current 2.1 MB changed response contains both structured data and full HTML.
3. Profile unchanged polling. It still reads and hashes discussion rows, checks each
   open file, runs Git baseline queries, and periodically scans the file tree.
   Consider a database revision counter, less frequent inactive-file checks, and a
   cached/background tree with explicit refresh. Preserve external-change detection.
4. Profile STL idle rendering and large JSONL/Markdown views before changing languages.
   Render on demand and move expensive parsing off the browser's main thread where
   measurements warrant it.
5. If backend CPU time then dominates, prototype only that operation in Rust and
   compare identical workloads. Keep the frontend and public behavior unchanged.

## Regression gates for a future port

| Gate | Command | What must remain true |
| --- | --- | --- |
| Fast Python contracts | `uv run pytest -m 'not browser' -q` | File/anchor semantics, stale saves, persistence, CLI, Git isolation, attachment lifecycle, authentication, conditional responses |
| Fast JavaScript contracts | `npm test` | JSON whitespace formatting preserves number/string tokens, duplicate keys, undo-compatible output and newline style |
| Browser behavior | `LOOKING_GLASS_BROWSER=installed uv run pytest -m browser -q` | Editing, selection, report sandbox, viewers, navigation, fixed controls, resizing, zen/undo, collapse, attachments and refresh recovery |
| Reproducible assets | `npm run build` then `git diff --exit-code -- looking_glass/static` | Committed assets match source and the lockfile |
| Packaging | `uv build` | Installable distribution includes all runtime assets |

Install browsers once with `uv run playwright install chromium firefox`. The fast
suite is about four seconds here; the formatter tests take under 0.1 seconds.
Browser checks run separately in continuous integration (GitHub Actions), so the
fast feedback loop does not require launching browsers.

For a port, preserve the HTTP API (application programming interface), CLI output,
ordinary-file behavior and existing `.looking-glass` data. The tests currently create
a Python app/Workspace directly; adapt their fixture and seed mechanism to launch the
replacement server. Keep the same browser assertions and public request/response
contracts. Internal unit tests alone cannot establish behavior parity. Require
before/after latency measurements as well as passing functional checks.


## History and review context · 2026-10-05

The commit graph loads 100 commits at a time on demand and performs no background
Git fetch or history polling. Original-context tabs are read-only and skip file
polling. Discussion refreshes return small origin metadata; full source copies
are loaded only when requested. Review source is compressed once per unique
content hash, shared across threads/messages, and garbage-collected when no
remaining discussion uses it. Attachments stream to disk; the composer retains
browser File/Blob references and small previews until sending, rather than
embedding image bytes in every discussion response. No new frontend dependency
or backend framework was added.

## Non-destructive review drafts · 2026-10-09

Drafts are created lazily, with coalesced human saves and operation-based history.
Unchanged polls inspect a small revision record and return 304 without reading or
transferring draft text. Human saves request small acknowledgements; full content
is fetched when the revision changes. Browser edit tracking updates provenance
segments incrementally. Disk files remain unchanged until approval.

Measured with `uv run python scripts/benchmark_reviews.py --mib N --iterations 20`:

| Approximate source size | Ordinary save median | Review save median | Unchanged poll median | Maximum save acknowledgement |
| --- | ---: | ---: | ---: | ---: |
| 1 MiB (1,048,525 bytes) | 5.11 ms | 13.47 ms | 0.62 ms | 173 bytes |
| 8 MiB (8,388,550 bytes) | 35.74 ms | 88.84 ms | 0.62 ms | 173 bytes |

Both runs verified exact preservation of the original. This local microbenchmark
uses append operations, no discussions, and the Flask test client; it does not
measure browser rendering, network latency, complex replacement workloads, or
long histories. Saves still serialize/store the accepted draft and segments, so
their cost grows with document size. Base/draft content, provenance and history
require additional disk space. The 8 MiB text limit applies to accepted drafts.
Review mode adds bounded work, not zero overhead.
