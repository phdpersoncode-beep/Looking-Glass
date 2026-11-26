# Startup and reconnect profile for PR #28

At PR #28 head `e3a8ef5`, the 3,000-thread **All Discussions** view was
the largest startup cost. The editor appeared in 0.73 s, while the discussion
sidebar took 25.05 s and the Chromium renderers used 1,158 MiB of proportional
memory. In the same workspace with file-scoped discussions, the editor
appeared in 0.71 s, the sidebar took 0.88 s, and renderer memory was 182 MiB.
Marker Tree made no requests when closed.

## Browser measurements

Five samples per case on Chromium 154.0.8037.57 and Python 3.12.14.
Times are medians in seconds from navigation. Parentheses contain observed
ranges for the target. Server startup took about 0.28 s before navigation
and used 38 MiB RSS at listen. The memory columns show the process snapshot
at the readiness checkpoint, including marker revalidation when enabled.

| Scenario | Shell first paint | Editor | Explorer | Target | Server RSS, MiB | Renderer PSS, MiB | JS heap, MiB |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| Fresh visit, marker tree closed | 0.47 | — | 0.80 | Explorer 0.80 (0.75–0.90) | 47 | 150 | 6.4 |
| Reopen one tab, file scope | 0.36 | 0.71 | 0.76 | Discussions 0.88 (0.81–0.90) | 52 | 182 | 10.2 |
| Reopen 16 tabs, file scope | 0.38 | 0.87 | 0.90 | Discussions 1.00 (0.94–1.10) | 57 | 193 | 10.7 |
| Reopen one tab, all discussions | 0.36 | 0.73 | 0.80 | Discussions 25.05 (24.80–25.24) | 85 | 1,158 | 34.5 |
| Reopen task board | 0.40 | — | 1.52 | Board 1.42 (1.33–1.71) | 52 | 287 | 9.7 |
| Reopen one tab, marker tree open, index missing | 0.30 | 0.69 | 0.90 | Markers 1.45 (1.36–1.57) | 52 | 189 | 9.7 |
| Reopen one tab, marker tree open, saved index | 0.39 | 0.77 | 0.93 | Markers 0.74 (0.66–0.86) | 56 | 188 | 11.4 |

With the all-discussions page already open, network recovery took a median
of **0.97 s after going online** (0.48–1.71 s) to finish the next successful
conditional response. That path reused the mounted page and cached payload.
`poll()` runs on a 2.2 s interval and performs file and Git checks before
refreshing discussions. Its phase affects the delay on return.

After two unchanged discussion polls, renderer PSS was 1,147 MiB and JS
heap was 40.8 MiB. The DOM counter dropped from about 719,000 to 552,000
nodes. Each sample returned 304 twice, and the browser still recorded
roughly 67–94 ms long tasks during the observation window. Two polls
characterize short-term work and retained memory.

## Comparison with PR #27

The same harness and fixture ran five times against `3d8ffa8`, the base
of PR #28. The largest delay was already present at that commit. Both
versions transferred exactly 27,292,663 bytes for All Discussions, and
the server took about half a second on each version. Fresh explorer and
single-file timings were close across the two sets of samples.

| Milestone | PR #27 | PR #28 |
| --- | ---: | ---: |
| Fresh explorer | 0.79 s | 0.80 s |
| One-tab editor | 0.71 s | 0.71 s |
| One-tab file discussions | 0.88 s | 0.88 s |
| 16-tab editor | 0.96 s | 0.87 s |
| All Discussions | 26.79 s | 25.05 s |
| Task board | 1.36 s | 1.42 s |

## Hypotheses and evidence

### All Discussions does eager work on both sides of the connection

The 27.29 MB response finished at 1.67 s on loopback. The median gap
from response completion to sidebar readiness was 23.41 s. The same
browser showed the active editor and file explorer before the response
finished. Scope is the only preference changed between this run and the
one-tab file-scoped run. Both still fetch the global discussion index.

At 1,000 threads with the same number of source files and the same
three-message shape, the sidebar took 6.66 s and renderer PSS was 528 MiB.
The response fell to 9.07 MB and the browser counted about 267,000 DOM
nodes. Tripling the thread count more than tripled discussion readiness
time in these samples.

The endpoint assembles full thread and message records, computes activity,
and embeds the rendered thread HTML alongside JSON. Suppressing only the
HTML renderer in a separate Flask test-client probe cut the median from
522 to 155 ms and the body from 27.29 to 8.65 MB. The browser consumes
that HTML, instantiates every card and reply form, and renders and sanitizes
all 9,000 Markdown bodies on the first mount. The much larger renderer PSS
and node count, including nodes outside the visible part of the sidebar,
explain why the JS heap column captures only a small portion of the memory.
Server and renderer evidence point to separate costs.

The Chromium trace recorded a **16.5 s main-thread task** in
`ExtractFormsAndNotifyPasswordAutofillAgent` immediately after mounting
the sidebar and completing the first layout. Every thread mounts a reply
form, including collapsed or offscreen threads. This is Chromium's native
form discovery work, which the JavaScript profiler recorded as browser code.

In the reply-form control, only the reply forms were removed from the
served thread template. The browser still mounted the same 3,000 threads
and 9,000 messages. The median readiness time fell from **25.05 s to
8.44 s** (8.11–8.94 s), even though the endpoint still sent 24.39 MB.
Renderer PSS was 1,028 MiB. The 16.61 s improvement closely matches the
form discovery task in the full-workload trace. A second trace of this
control had no `ExtractFormsAndNotifyPasswordAutofillAgent` task. The
remaining cost includes rendering the discussion body, layout, and transfer.

Reopening with all 3,000 cards collapsed reduced median renderer PSS to
579 MiB and Chromium's combined layout and style time from about 3.29 s
to 0.59 s. The sidebar still took 22.93 s (21.85–25.34 s), transferred
the same 27.29 MB, and retained about 700,000 counted DOM nodes at readiness.
The collapse setting hides the bodies after their markup and Markdown
decoration have been created.

A separate source-mapped Chromium CPU sample attributed about 3.7 s of
inclusive time to the discussion view renderer, including 2.2 s in
Markdown rendering and 1.3 s in sanitization. Another 3.4 s appeared in
CodeMirror measurement and DOM selection reads around the same update.
These are nested stack timings from one diagnostic sample.

An independent readiness check that polled with animation frames and
removed the benchmark's document-wide mutation observer reached the
same state in 26.78 s. This reproduced the delay with a different probe.

The 304 path avoids Jinja and response serialization. It still re-queries
threads and messages, builds the navigation index and serializes those
records for the ETag. The browser reuses the existing HTML and still runs
discussion-state and sidebar filtering work.

### File discovery and tab restore explain part of the default path

The fresh visit read a 2.02 MB JavaScript bundle and requested a 490 kB
file explorer fragment and 550 kB discussion index inside the empty-scope
response. The warm runs revalidated the JavaScript asset with no body
transfer. A 304 on the explorer still takes 57 ms in the Flask probe because
the route walks the tree, obtains Git status and computes an ETag before it
can short-circuit. Bypassing only Git decoration lowered a full response
from 76 to 46 ms in the clean synthetic repo. The browser still mounts
all explorer entries and applies folder visibility after the response.

The same active editor took 0.71 s with one saved tab and 0.87 s with 16.
Each text tab added a stat request and a file request. The restore code
waits for all restored documents before mounting the active one, so the
15 inactive tabs sit on the startup path even though only one is mounted.

### Marker Tree costs depend on its saved state

With the panel closed there were zero requests to `/api/marker-tree`.
With the saved panel open and no index, the cache probe returned 204 and
the next request built and wrote the index. The browser displayed the
marker count at 1.45 s. The Python call profile identifies file reads and path
validation, parsing, and JSON persistence in the cold scan. With a saved
index, the cache probe returned 200 and showed markers at 0.74 s, followed
by a conditional filesystem check returning 304. The editor still reached
readiness at 0.69–0.77 s across those case medians.

### Task board mounting is a browser cost at this size

The 1,200-record task snapshot took 8 ms in Flask. The browser received
720 kB by 0.64 s and painted the complete board at 1.42 s. It creates both
the board cards and the sidebar hierarchy, totaling roughly 68,000
counted DOM nodes with the rest of the app. Default file startup did not
request tasks. The same-revision task poll took 0.4 ms in Flask.

With 80 task records and the same source files and discussions, the board
appeared at 0.74 s, renderer PSS was 185 MiB, and the node count was about
32,000. That isolates the cost of restoring the larger board.

## Isolated HTTP measurements

Flask test-client medians over five samples. kB and MB are decimal
response-body sizes. Conditional requests exclude response headers.

| Probe | Status | Server time, ms | Body |
| --- | ---: | ---: | ---: |
| Explorer | 200 | 75.9 | 490 kB |
| Explorer, skip Git decoration | 200 | 45.6 | 490 kB |
| Unchanged explorer | 304 | 56.7 | — |
| Global discussion index | 200 | 11.2 | 550 kB |
| Current file discussions, ten threads | 200 | 16.9 | 636 kB |
| All discussions, 3,000 threads | 200 | 522.3 | 27.29 MB |
| All discussions, skip HTML rendering | 200 | 154.9 | 8.65 MB |
| Unchanged all discussions | 304 | 84.0 | — |
| Task board, 1,200 records | 200 | 8.4 | 720 kB |
| Unchanged task board | 304 | 0.4 | — |
| Build Marker Tree index | 200 | 548.1 | 591 kB |
| Restore Marker Tree snapshot from disk | 200 | 16.4 | 591 kB |
| Unchanged Marker Tree | 304 | 53.7 | — |

## Reproduce

With Chromium installed, run the following commands from the repository root.

```bash
uv sync --locked
uv run --locked python scripts/benchmark_startup.py > /tmp/looking-glass-startup.json
```

Use `--chromium installed` for Playwright's Chromium after
`uv run playwright install chromium`. Use `--scenario` more than once to select
cases, `--runs` to change repetitions, or `--backend-only` to skip the browser.
Compare with the base by checking it out in a separate worktree and passing its path.

```bash
git worktree add --detach /tmp/looking-glass-pr27 3d8ffa8eab98c71239577f4d79e3358ec7bfb6ff
uv run --locked python scripts/benchmark_startup.py --app-dir /tmp/looking-glass-pr27 > /tmp/looking-glass-pr27.json
uv run --locked python scripts/benchmark_startup.py --cards 80 --threads 1000 \
  --scenario all-threads --scenario board > /tmp/looking-glass-control.json
uv run --locked python scripts/benchmark_startup.py --cards 80 --scenario board > /tmp/looking-glass-board-control.json
uv run --locked python scripts/benchmark_startup.py --browser-only \
  --scenario all-threads-no-reply-forms > /tmp/looking-glass-reply-control.json
```

To inspect the browser's JavaScript stacks in DevTools, record a separate
sample with `--browser-only --runs 1 --cpu-profile-dir /tmp/looking-glass-cpu`.
The CPU sampler adds overhead. Use the ordinary runs for wall-clock comparisons.

To inspect the fixture interactively, generate it in a new directory and open it
using the ordinary CLI. The generated Git repo has no remote. Its discussion and
planning data lives in its local SQLite database.

```bash
uv run --locked python scripts/startup_fixture.py /tmp/looking-glass-synthetic
uv run --locked looking-glass serve /tmp/looking-glass-synthetic
```

The full fixture has 2,017 tracked files, including 15 inactive 131 KiB tabs,
2,000 Python, JavaScript, Markdown, and Jupyter files with 4,000 TODO, NOTE, and
P0–P3 markers, 1,200 task records (24 milestones), and 3,000 anchored threads
with 9,000 Markdown messages and immutable origins. The overview has ten
threads. Every fifth thread is resolved. The benchmark creates and cleans up
its own fixtures. It uses a fresh threaded Werkzeug process and Chromium
instance per sample, with the selected checkout's bundled assets. Server
startup measures process launch through binding a loopback socket.

Browser timestamps start at navigation and record the first contentful paint
and two animation frames after each target shows its expected state. Returning
visits use browser storage and a primed HTTP cache. The saved-marker case
loads a disk snapshot built by a previous server process and then checks it
against the filesystem. The connection recovery case takes the loaded page
offline through a failed discussion request and measures the next successful
conditional refresh after bringing it online. The JSON includes HTTP status
codes, resource timings and byte counts, long tasks, Chromium heap and DOM
counters, and Linux process memory. Renderer PSS sums renderer processes for
the test browser and excludes its parent, GPU, and network processes. Heap
counts are sampled without forcing garbage collection.

Server probes run through Flask's test client in a separate process, without
network, browser, or sampling profiler overhead in the timing samples.
Separate cProfile runs attribute Python work. Cold means a fresh browser or
no saved Marker Tree cache as specified per case. OS disk caches are left
alone. These are loopback measurements in headless Chromium on a shared
Linux container, with a two-CPU quota. Real cache state, proxy throughput,
network round-trip times, editor contents, attachments and hardware can
change the figures.
