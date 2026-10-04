# Performance and port decision

## Recommendation

Keep the Python backend for now. The measurements below do not justify a full Rust
port. A faster server will not remove a large browser rendering workload. Revisit
Rust in a separate session only after a browser/server profile identifies a CPU-bound
backend operation that remains slow after reducing unnecessary work.

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
