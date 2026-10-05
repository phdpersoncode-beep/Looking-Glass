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
