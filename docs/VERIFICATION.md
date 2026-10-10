# Non-destructive review mode · 2026-10-09

Implementation: [PR #10](https://github.com/phdpersoncode-beep/Looking-Glass/pull/10),
on `feature/non-destructive-review-mode`.

- Initial implementation `a5467ba`: all **99 backend**, **14 JavaScript**, and
  **175 browser** tests passed in the
  [locked-dependency GitHub run](https://github.com/phdpersoncode-beep/Looking-Glass/actions/runs/37965250790).
  Browser tests used Chromium and Firefox and completed in 638.00 seconds.
  Clean asset reproducibility and Python wheel/source builds also passed.
- Review coverage includes persistence/restart, untouched original bytes, human
  and agent provenance, timestamps/history, Unicode/CRLF operations, invalid
  batch rollback, stale edits, exact approval and file permissions, external disk
  conflicts, separate discussion positions, removed-passage context, and real
  local command-line editing and commenting.
- Browser workflows exercise mode switching/reload, human replacements, agent
  updates, draft comments, comment editing, undo, live/preview Markdown tables,
  runtime HTML comments, conflict comparison, and approval protections. Existing
  selection, sidebar, Git, report isolation, and navigation regressions remain
  part of the full suite. Light/dark, narrow-pane, Markdown/table and highlighted
  Python layouts were inspected during implementation.
- Follow-up fixes position HTML deletion text at mapped character boundaries and
  preserve source selections after text-node splits. Five new scenarios run in
  each browser, including beginning/middle/end deletions, entities, and multiple
  removals with Unicode. The expanded real command-line regression verifies
  `reply --review` captures the draft's immutable content and shifted passage,
  while ordinary replies retain disk context.
- After these fixes, **99 backend** and **14 JavaScript** tests pass locally;
  all **12 review scenarios pass in Firefox**. Local Firefox uses
  `MOZ_DISABLE_CONTENT_SANDBOX=1` for container compatibility; HTML report
  isolation remains enabled. The expanded full browser suite contains 185 cases.
  [Latest locked Chromium/Firefox checks](https://github.com/phdpersoncode-beep/Looking-Glass/pull/10/checks)
  report the follow-up gate separately from the historical initial run above.
- The 1 MiB and near-8 MiB benchmarks verify original byte preservation and
  173-byte save acknowledgements. See [PERFORMANCE.md](PERFORMANCE.md) for measured
  save/poll costs and workload limits. Review mode adds storage and save work;
  these figures do not establish zero overhead or browser-rendering latency.

---

# Bounded source anchoring and agent repair · 2026-10-06

- Local fast suite: **59 passed** in 6.78 seconds; **4 JavaScript tests passed**.
- Wheel/source distribution build and `git diff --check` passed. No frontend
  source/assets or runtime dependencies changed.
- A 60 KB repetitive edit previously exceeded a two-second subprocess deadline
  for one thread. The regression now handles 28 threads and consecutive HTTP
  requests within a five-second subprocess deadline (normally well below one second).
- Tests cover the reported wrong-line pattern, ambiguous/deleted duplicate quotes
  and identical whole-paragraph insertions/deletions,
  meaningful text versus shared whitespace, Unicode/multiline quotes, normal
  interior/boundary edits, unchanged-range shifts, relocated exact passages,
  per-file work exhaustion (including long unchanged quote edges), shared mapping work, and no failed-anchor retry on polls
  or restart. A resolved thread keeps its status and immutable origin when orphaned.
- Real HTTP/CLI checks cover manual reattachment, correction of an attached wrong
  passage, explicit repeated-quote occurrence selection, empty/missing/ambiguous
  quotes, invalid occurrences, missing files/threads, and rendered-anchor refusal.
  Comments, immutable origins, resolved state, and disk contents are preserved.
  A file change between reading a quote and sending PATCH is rejected as stale.
- `scripts/benchmark_anchors.py` verifies rewritten repetitive and moved unique
  passages in disposable 60 KB/2 MB files with 28 threads. Median changed-file
  requests are 1.79–30.70 ms here. See [PERFORMANCE.md](PERFORMANCE.md) for scope
  and work budgets. The user's original edited plan/database were not supplied;
  reproduction uses representative synthetic inputs and the supplied access logs.
- Browser checks were not run locally; the pull request's existing GitHub Actions
  workflow runs the separate Chromium/Firefox suite and asset reproducibility gate.
  [Latest pull request checks](https://github.com/phdpersoncode-beep/Looking-Glass/pull/2/checks).

---

# Commit graph, durable review context, and clipboard attachments · 2026-10-05

Based on the fork's latest branch, `codex/discussion-workflow` at `cb875b8`.
Three feature commits were published separately to
`codex/history-and-persistent-discussions`.

- Local fast suite: **35 passed** in 4.69 seconds; **4 JavaScript tests passed**.
- Local Chromium browser suite: **28 passed** in 97.64 seconds. Targeted checks
  repeated after the final composer cleanup also passed.
- GitHub Actions on `9f61154`: **both fast and browser jobs passed**, using locked
  dependencies and installed Chromium/Firefox. Asset reproducibility and Python
  packaging passed on the clean runner.
  [Verified run](https://github.com/phdpersoncode-beep/Looking-Glass/actions/runs/37356220243).
- Source distribution and wheel built locally; their new templates and origin
  module were verified in the package contents. Installed frontend versions
  match `package-lock.json`.
- Light/dark graph and composer screenshots were inspected at 1440×960.
- The new history, deleted-context, and clipboard/retry browser cases are
  explicitly parametrized for both Chromium and Firefox in continuous integration.

New checks cover split/merge lanes, stable first-parent colors, branch filtering,
read-only history, pagination, unsaved draft retention, exact uncommitted source,
per-comment commit references, source/rendered anchors, deletion, reattachment,
restart, legacy migration, token protection, snapshot deduplication/cleanup,
image-only multipart comments, message-owned attachment cleanup, rollback after
partial upload failure, and safe retries retaining text/files. Clipboard checks
inject browser paste events containing PNG data and verify ordinary text paste
is not intercepted. Physical Windows/Ubuntu clipboard integration was not run.

---

# Discussion workflow completion · 2026-10-04

Continued `codex/discussion-workflow` from `76ae7bb`; the earlier commits already
implemented uploads/renaming, JSON formatting, cross-file arrows and toggle,
resizing, collapse controls, zen mode (Ctrl+Alt+Z), and conditional discussions.

This follow-up fixes:

- Failed directory scans no longer replace a valid file tree with an empty one.
- Unchanged file-tree responses keep existing elements and use HTTP 304; refresh
  requests are serialized. Actual file additions/removals still refresh the tree.
- Folder expansion records user gestures synchronously, avoiding delayed toggle
  events from filtering or redraws overwriting the saved state.
- Successful replies clear only the submitted draft. Unsent text remains intact;
  focused discussion buttons no longer suppress external agent updates forever.

Verification in this session:

- **GitHub Actions passed both jobs** on commit `16b9551`: 29 fast Python tests,
  2 JavaScript tests, and **28 Chromium/Firefox browser tests in 123.12 seconds**.
  The clean runner also verified rebuilt assets and packaging.
  [Verified run](https://github.com/phdpersoncode-beep/Looking-Glass/actions/runs/37225152259).
  Local Firefox startup stalled; the clean runner completed those checks.
- **54 Python/browser checks passed in 92.46 seconds**, with three Firefox
  cases excluded from that run. Chromium used the available headless shell build 1187;
  the Python environment used the locked Playwright 1.63.0.
- **29 fast Python checks passed in 4.21 seconds**; **2 JavaScript checks passed**
  in approximately 0.08 seconds.
- `npm run build`, `uv build`, and `git diff --check` passed.
- New browser regressions reproduce scan failure/recovery, unchanged-element
  identity, real empty-directory updates, folder state, submitted reply clearing,
  preserved unsent drafts, and resumed external agent replies.
- The full end-to-end tests initially exposed the stale submitted-draft bug;
  they pass after the fix, including agent reopen/delete updates and HTML anchors.

The new GitHub Actions workflow separates fast tests/build/package checks from
browser tests. Browser installation is a one-time setup cost, excluded from timings.
See [PERFORMANCE.md](PERFORMANCE.md) for measured server costs and the port decision.

---

# Linux selection follow-up · 2026-10-04

Full suite: **44 passed** in 105.61 seconds. Frontend build and `git diff --check`
also passed. Firefox used Playwright 1.55.0, browser 141.0.

The annotation toolbar could remain hidden after a missing pointer-release event:
Looking Glass's drag flag listened to pointer events, while CodeMirror uses mouse
events for selection. The regression reproduced the hidden toolbar before the fix.
Selection now begins on pointer or mouse press, settles on captured release/cancel,
and recovers when the mouse returns with the primary button up, when focus leaves,
or when the page is hidden. Markdown syntax stays stable throughout the drag.

Linux Chromium and Firefox checks cover ordinary and mouse-only input, suppressed
release events, forward/backward and multiline drags through Markdown formatting,
plain text, Unicode, existing annotations, and posting the selected quote.
Tests ran headlessly on Ubuntu 24.04. Native Wayland compositor/input delivery and
Linux middle-click PRIMARY clipboard integration were not verified here; this fix
does not claim to diagnose the exact laptop-specific cause. The README includes a
visible Firefox test command for a native Wayland session.

# Viewer and review improvements · 2026-10-03

All 38 tests pass, including every opt-in browser test, using Playwright 1.55.0
with its installed Chromium headless shell. The frontend build and wheel build
also succeed. The wheel contains all six bundled Newsreader fonts, their license,
and the HTML preview keyboard bridge.

```bash
npm run build
LOOKING_GLASS_BROWSER=installed .venv/bin/pytest -q
.venv/bin/python -m pip wheel --no-deps . -w ../wheel-check
git diff --check
```

Verified the requested items individually before their commits:

- Live Markdown tables: alignment, inline formatting, editable source, and preview.
- JSON and JSONL: collapse all, selectively unfold nested entries, expand all,
  and keep malformed JSONL rows usable.
- PNG/JPEG/SVG: zoom, fit, actual size, pan, restored tabs, invalid-image errors,
  and inert SVG scripts.
- All-file discussions: file labels, traversal across Markdown/code/HTML,
  retained dirty drafts, and resolved-thread filtering.
- CLI body files and stdin: exact Unicode/Markdown/backtick/quote preservation,
  create and reply, mutually exclusive input options, and missing-file errors.
- Explorer resizing: mouse drag, persisted width, keyboard controls, and bounds.
- Newsreader: normal/italic faces and extended characters load from local assets.
- HTML/JSONL downloads: filenames and bytes, unsaved HTML drafts, and working
  scripts when a downloaded self-contained report is opened directly in a browser.
- Gitignored files: no gutter for ignored untracked files, including nested paths;
  tracked files still show modifications, and changed ignore rules refresh the gutter.
- Ctrl/Cmd+P inside rendered HTML: opens the app file picker and prevents printing.
- Markdown fences: hidden inactive language tags, highlighted Python/Bash in the
  editor and preview, and safe plain-text fallback for unknown languages.

The existing end-to-end workflows also passed. Updated their stale default-author
expectation from Codex to Agent to match the existing CLI default. No product
change to the default author was made.

## Delivery

The original requested items were published to
`phdpersoncode-beep/Looking-Glass` on `codex/viewers-and-review`, one commit per
item plus verification documentation. The branch includes the newer concise
`AGENTS.md` from main. Its published file tree was fetched back and verified
against the local tree. Publication to the originally named altaykacan fork had
been blocked by connection permissions; the requested destination is writable.

---

# First milestone verification · 2026-10-03

Latest CLI update: 23 non-browser tests passed. The browser instruction workflow
also passed separately. The full default run skipped three opt-in browser tests.
The frontend was built locally using the committed npm lockfile. No application
dependency is fetched from a CDN at runtime.

## Agent CLI update · 2026-10-03

Commands run:

```bash
uv run pytest -q
LOOKING_GLASS_BROWSER=installed uv run pytest tests/test_browser.py::test_review_workflow_features -q
git diff --check
```

- Verified server registration, project reachability, directory switching, and stopped servers.
- Verified current-directory root inference and registered nondefault server addresses.
- Verified comment and quote search, Unicode text, combined filters, summaries, and pagination.
- Verified full messages and source context for multiline, CRLF, and Unicode passages.
- Verified rendered context and unavailable context for detached source anchors.
- Verified invalid query rejection, loopback URL validation, and wrong-root rejection even with matching tokens.
- Verified every CLI command exposes help and an example.
- Verified portable instructions through the terminal and browser clipboard.
- Test registries use temporary directories and never update the user's project registry.

## End-to-end browser workflow

The October 3 workflow update also verified:

- Collapsible nested folders, expansion across refreshes, and collapse-all.
- Ctrl+P fuzzy search, keyboard opening, and Escape dismissal.
- Document font adjustment with fixed control sizes and persistence after reload.
- Clickable live Markdown task checkboxes and checked reading-preview rendering.
- Individual comment and whole-thread deletion, including durable removal.
- Ctrl+F JSONL search across valid and malformed rows, with forward/backward navigation.
- Copyable agent commands containing the current workspace and server port.
- Added, changed, and removed Git gutter markers for drafts and saved files.
- HEAD baselines in nested workspaces and preservation of staged Git content.
- Rendered HTML selection across inline elements and entities, persistent highlights,
  replies, navigation between modes, DOM formatting changes, and missing/ambiguous
  passage reattachment. Interactive report controls and opaque-origin isolation remain active.

Run with headless Chromium 153 against a disposable copy of `demo_dir`:

- Opened Markdown in live mode; switched to raw source; edited, undid/redid and
  saved with keyboard shortcuts; confirmed the actual disk file changed.
- Selected live Markdown with forward/backward mouse drags and across styled
  passages, without changing the layout during selection. Selected multiline
  plain text and text inside an existing anchored highlight with the mouse.
- Used the floating add-comment button and compact, nonmodal composer near the
  selection. Checked its position, size, focus, Escape cancellation, Ctrl+Enter
  posting, and visible selection tint after focus moved into the composer.
- Searched a passage and created an anchored discussion in the interface.
- Replied through the terminal CLI and through the sidebar; read both replies
  back through the CLI. Resolved/reopened and navigated between passages.
- Edited Python with Ctrl+H search/replace, saved it, and created a code discussion
  from the terminal. Verified its appearance in the browser.
- Preserved CRLF line endings through a browser edit and save. Created a Unicode
  anchor over `🪞 München` and verified the visible highlight.
- Reloaded a clean externally changed text file. Detected a second external
  change while a draft was dirty, kept the draft, merged, and saved deliberately.
- Opened JSONL, selected a malformed line without disrupting the viewer, then
  selected and inspected a valid formatted row.
- Opened both ASCII and binary STL fixtures, checked their four triangles,
  orbited/zoomed, and used fit-to-view. Checked screenshot pixels for visible
  geometry, including tiny and huge coordinate scales. Disabled WebGL and
  verified visible ASCII/binary software previews and working orbit/fit controls.
  Confirmed that malformed STL shows an error inside the viewer.
- Ran an interactive HTML report button; its own script confirmed that access
  to the parent application's document was blocked. Switched to HTML source
  and created an anchored comment there.
- Inspected a diff and created a selected-file checkpoint through the interface;
  verified that the resulting commit included only `notes.txt`.
- Restarted server state and reopened the discussions with all messages intact.
- Verified tab pinning, closing other unpinned tabs, individual closing, Times
  New Roman prose styling, light/dark modes, and no uncaught browser errors.

Screenshots: [light](screenshots/light.png), [dark](screenshots/dark.png).
Updated comment composer: [light](screenshots/comment-light.png),
[dark](screenshots/comment-dark.png).

## Backend and process checks

- A separate test terminated and restarted the actual server process, then read
  terminal-created threads/replies back and resolved/reopened them.
- Tested hash-based stale-save rejection, atomic-save executable permissions,
  ordinary anchor shifts and internal/boundary edits, ambiguous/deleted anchor
  orphaning, reattachment, Unicode offsets and persistent SQLite/token state.
- Tested traversal, symlink and metadata-path rejection, API-token enforcement,
  cross-origin/host rejection, comment escaping and HTML preview sandbox headers.
- Tested selected Git checkpoints with unrelated staged and unstaged work,
  initial repositories, subdirectory workspaces, deletions, and literal filenames
  containing Git path-pattern characters. Existing selected staged work is rejected.

The delivery status above supersedes the original standalone archive handoff.

## Rendered HTML source annotations (2026-10-08)

Implementation: `771a4a7`, on `feature/rendered-html-source-annotations`.

- Frontend: **11 passed**, including entities (legacy/numeric/multi-codepoint),
  CRLF, Unicode, optional table tags, repeated text, marker collisions, exclusion
  of scripts/templates/form values, original-byte preservation, and 10,000 elements.
- Backend: **80 passed**, including source-thread lifecycle/original context,
  stale and invalid offsets, and preview isolation/file preservation.
- Full browser suite: **99 passed** in 378.38 seconds. Ten new Chromium/Firefox
  cases cover raw/rendered navigation, native dragging, keyboard comments, table
  cells, partial entities, source-created threads, fragments, hidden duplicates,
  persistence, replies, resolve/reopen, external edits, reattachment, unsaved draft
  highlighting, runtime-only text, legacy threads, scrolling, and highlight clicks.
- Frontend rebuild is reproducible (`git diff --exit-code -- looking_glass/static`);
  Python wheel and source distribution build successfully. GitHub's fast job also
  passed with the repository's locked dependencies.
- The selection popover and purple selection styling were visually inspected.

Local browser verification used Playwright 1.56, Chromium 141, and Firefox 142
because the pinned browser downloads were unavailable in this container. Firefox's
process sandbox was disabled for the container; the application's opaque-origin
report iframe sandbox remained enabled and its isolation is explicitly tested.
GitHub's separate browser job uses the repository's pinned Playwright dependencies.

Source-backed threads never depend on quote-only DOM matching. Runtime-generated
or otherwise unprovable mappings remain explicitly rendered-only; existing
rendered-only threads are preserved without speculative migration.

## Markdown selections and discussion reading (2026-10-08)

Implementation: `4208669`, on `feature/markdown-discussion-reading-polish`, based
on main after merging [PR #7](https://github.com/phdpersoncode-beep/Looking-Glass/pull/7).

- Frontend: **11 passed**. Backend: **80 passed** locally and in GitHub's locked
  dependency job. Frontend assets rebuild reproducibly; Python wheel and source
  distribution builds pass.
- Full browser suite: **119 passed** locally in **431.06 seconds**, and
  **119 passed** in **425.00 seconds** in the
  [locked-dependency run](https://github.com/phdpersoncode-beep/Looking-Glass/actions/runs/37848191803).
- Twenty new Chromium/Firefox cases cover forward/backward native multiline
  selections in live and reading-preview Markdown, wrapped prose, Unicode/CRLF,
  exact saved source anchors, and clean side margins. Both themes retain the
  existing purple selection color, including rendered tables.
- Discussion bodies and replies share Markdown styling, compact tables, syntax
  coloring, and Mermaid diagrams. Checks cover headings, lists, quotes, links,
  smaller fonts, theme changes, reloads, unchanged stored Markdown, and sanitized
  HTML that cannot execute scripts or impersonate discussion controls.
- Thirty long Markdown threads exercise floating-card placement and independent
  scrolling in live, preview, and source views. Opening keeps document/sidebar
  scroll within two pixels. Dismissal restores the original card order and keeps
  the reading position stable; external updates preserve reply drafts, focus,
  and cursor selection.
  Twenty-five HTML threads verify report-scroll preservation and defocus behavior;
  existing iframe isolation and source-annotation regressions remain in the suite.
- Final focused Markdown/discussion browser checks: **40 passed**. Immediate Escape dismissal cancels
  delayed passage activation. Posting, sidebar expansion, original context, and
  explicit passage navigation keep controls in the normal list. Replies preserve
  whether the card is floating or in the list; passage clicks temporarily float it.
- A live-table regression failed before the repair: a new background discussion
  replaced the selected table and cleared its native selection. Annotation-only
  updates now reuse the DOM and defer mark changes during selection. Both browser
  cases pass and verify posting the preserved exact quote after the update. The
  encoded-character test helper now focuses the native table region like a real
  cell drag, instead of leaving CodeMirror's source caret focused.
- Text-only selections and compact discussion tables/code were visually inspected
  in light and dark themes.

Local focused browser checks used Playwright 1.56, Chromium 141, and Firefox 142.
The complete final browser gate uses the repository's pinned Playwright/browser
versions in GitHub Actions. Local Firefox process-sandbox relaxation was only for
container compatibility; the report iframe's opaque-origin isolation stayed enabled.

## Passage sidebar spotlight (2026-10-09)

Implementation: `adf344a`, on `feature/markdown-discussion-reading-polish`.
This replaces the previous floating-card interaction; text-only selections,
compact Markdown messages, and live-table selection preservation remain intact.

Full browser suite: **131 passed** locally in **630.29 seconds**, and
**131 passed** in **489.18 seconds** in the
[locked-dependency run](https://github.com/phdpersoncode-beep/Looking-Glass/actions/runs/37911110074).

- Frontend: **11 passed**; backend: **80 passed**. Frontend assets rebuild
  reproducibly; Python wheel/source distribution builds pass. GitHub's locked
  dependency fast job also passes.
- The discussion-reading browser module now contains **32 cases**. Its 12
  additional cases cover overlapping passages in live/preview/source Markdown
  and live tables, new passage threads during refreshes, unrelated discussions,
  deletion, file changes, and resolution without zen-mode navigation.
- Thirty long threads exercise reading-scroll stability, original card identity
  and order, restored list scroll after switching passages, collapse/expand,
  Escape (including the delayed pointer-release race), explicit navigation,
  and reopening the hidden sidebar. Refreshes preserve reply drafts, focus,
  and cursor selection. Bulk controls affect only spotlighted discussions.
- Twenty-five HTML threads plus an overlapping rendered-only discussion exercise
  report-scroll stability, passage grouping, persistent focus through report
  interactions, and Escape inside the isolated iframe. Existing report isolation
  and exact source-anchor tests remain in the complete suite.
- Light/dark sidebar layouts were visually inspected. The small passage header
  stays above the sidebar scroller; cards remain in their original DOM/list order,
  without placeholders, overlays, or motion.

## Spotlight navigation and reading-position fixes (2026-10-09)

Implementation: `8e5f448`, on `feature/markdown-discussion-reading-polish` (PR #8).

- Full local browser suite: **161 passed** in **677.25 seconds**, using Chromium
  and Firefox. Backend: **80 passed** in **12.92 seconds**; frontend: **11 passed**.
- The new navigation module contains **30 browser cases**. Actual pointer clicks
  cover highlights eight pixels from the reading pane's bottom, live/source/preview
  Markdown, long hidden link URLs, live tables, and isolated HTML reports. Narrow
  viewports exercise reopening the sidebar and the resulting document reflow.
- Before the fix, revealing live link syntax moved the reading position by about
  153 pixels and moved the clicked glyph by about 306 pixels. Reopening a sidebar
  could push the clicked glyph below the viewport. Regressions now require the
  clicked glyph to remain within two pixels of its prior screen position; when
  the sidebar is already open, the scroll offset also remains within two pixels.
  If opening the sidebar changes wrapping, the scroll offset compensates for that
  reflow to keep the clicked text in place.
- Sidebar icon tests require deliberate passage navigation with surrounding
  context and sidebar spotlight, including cross-file navigation. Escape restores
  the full list position and preserves the reply draft. Live table highlight
  clicks also work after a prior source-range selection. Wheel scrolling,
  highlight dragging, keyboard editing, and unchanged disk contents are checked.
- A small Esc key hint is visible next to All discussions, with accessible shortcut
  metadata. Escape works from the editor, reply field, and isolated report iframe.
  Existing overlap, refresh, zen-mode, anchor, and selection checks remain green.
- Frontend assets rebuild reproducibly; wheel/source distribution builds pass.
  Packaged template and JavaScript/CSS bytes match the checkout. Light/dark sidebar
  layouts were visually inspected, including the return control and key hint.
- The [locked-dependency workflow](https://github.com/phdpersoncode-beep/Looking-Glass/actions/runs/37918336516)
  passes its fast job, including backend/frontend tests, rebuilt asset equality,
  and packaging. Its browser job is still running when these notes are written.

## Temporary discussion context and resolved passages

Branch: `feature/context-return-and-resolved-passages`, integrated with main
`1f974f6` after PR #10.

- **101 backend** and **20 JavaScript** tests pass with locked dependencies.
- **170 distinct new browser cases** pass across the context suite and targeted
  follow-up runs in Chromium and Firefox. Coverage includes numbered and
  parenthesized lists/tasks; rendered Markdown/code context; Return/Esc and
  resolution/deletion/unfocus; exact scroll restoration; preserved editor DOM,
  unsaved text, reply drafts and isolated HTML report state; faint resolved
  marks in dirty drafts, tables, previews and HTML; overlapping open discussions;
  native selection clearing; deletion of comments added during a context visit;
  and Review mode scope/reply snapshots. Unrelated HTML selections remain intact.
- The complete existing browser suite passes: **205 cases** in **1040.53 seconds**.
  Together with the new module, **375 distinct browser cases** pass. The new module's initial run
  passed 138 cases before encountering a test harness string wait blocked by
  the application's CSP. That wait now uses a DOM assertion; 16 follow-up
  cases, 12 Markdown selection cases and 12 final HTML cases pass, with eight
  repeated HTML cases. These runs cover all 170 distinct cases in the module.
- Local browser verification uses **Playwright 1.55.0**, **Chromium 140.0.7339.16**
  and **Firefox 141.0**. Locked Playwright 1.63.0 browser downloads returned
  incomplete archives. Firefox's process sandbox is disabled for this container;
  report iframe isolation remains enabled and tested. Dependencies are unchanged.
- A clean `npm ci` build and a repeated asset rebuild produce identical bytes.
  Wheel/source distribution builds pass; packaged static assets and templates
  match the checkout. Light/dark context and resolved-passage layouts were
  inspected visually. The patch applies cleanly to the recorded
  main baseline.
- Published to `phdpersoncode-beep/Looking-Glass` as
  [PR #11](https://github.com/phdpersoncode-beep/Looking-Glass/pull/11). The
  implementation tree was fetched back and matches the verified local tree
  (`b771d606fdb36b8c673a6ff834728db3ec0baf0d`) byte for byte. GitHub reports
  the PR mergeable. Hosted CI status is available on the PR; the local browser
  fallback above remains distinct from the locked-dependency workflow.

## Whole-app regression coverage and suite speed · 2026-10-10

PR #11 is merged into main at `b8decb0404b58e0b120aa33a5e802807eeaf7118`.
Follow-up branch: `test/whole-app-regressions`, targeting main after PR #11.
The results below record the completed local verification; locked-dependency
GitHub checks are required before merging this follow-up.

- The full existing collection is retained. **7 backend** and **12 browser**
  cases were added: Unicode/CRLF discussion origins and attachments across
  review approval/restart; stale writes preserving draft/discussion state;
  approval/checkpoints preserving other files and staged work; independent
  tab drafts/undo; edited-comment search, context, resolution/reopening and
  reload; browser context isolation; and pre-focus HTML reading position.
  `TESTING.md` maps the entire application's existing and added coverage.
- Final locked-dependency backend run: **108 passed** in **22.61 seconds**,
  while browser jobs ran concurrently. An earlier run passed in 16.20 seconds.
  **20 JavaScript tests** pass in **0.34 seconds**. No dependencies changed.
- Full final local browser run: **387 passed**, no failures or skipped cases.
  Four independent pytest shards ran concurrently in **382.35 seconds**
  (6 minutes 22 seconds). Shard counts/times: 97/382.00 s, 97/292.53 s,
  97/332.19 s and 96/309.98 s. Each shard includes Chromium and Firefox.
  The collection guard confirms every case appears exactly once.
- Process reuse retains fresh contexts, workspaces, servers and registries.
  Per-test context cleanup also covers failed assertions. The legacy full
  end-to-end journeys use the shared driver and retain their clipboard and
  software-rendering launch settings. Shorter server idle polling reduces
  teardown wait; production polling, assertions and timeouts are unchanged.
- Same-machine sequential comparison of the **same nine existing cases**:
  **39.70 seconds before**, **22.89 seconds after** (about **42% faster**).
  Includes live Markdown/tables/contents, review lifecycle, fuzzy search and
  numbered lists across both browsers. One run per version, same Python and
  browser installations; this is diagnostic, not a whole-suite speed claim.
- The original PR #11 locked CI run passed the fast job and **374/375 browser
  cases** in 1271.98 seconds. Firefox reported a four-pixel movement in the
  existing low HTML highlight check. The follow-up captures the reading point
  at pointerdown, before native mouse focus can scroll, and clears the hold for
  dragging, wheel and keyboard navigation. All **four** new focus-nudge cases
  fail on PR #11's old assets and pass with the fix. The original 30 spotlight
  cases pass locally, and all remain in the final full collection.
- Browser verification uses the available **Playwright 1.55.0 / Chromium 140 /
  Firefox 141** fallback. The locked Playwright 1.63.0 workflow has not run on
  this follow-up yet. Firefox's container process sandbox setting does
  not disable the application's report iframe isolation checks.
- Asset rebuilds are reproducible; wheel/source distribution builds pass.
  All **18** packaged static assets/templates match the checkout byte for byte.
  `git diff --check` passes. The follow-up workflow runs all four browser shards
  without canceling remaining shards after a failure or automatically retrying
  failed assertions, and checks shard completeness in the fast job.
