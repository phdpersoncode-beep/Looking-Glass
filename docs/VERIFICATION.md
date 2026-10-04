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

Changes are based on `altaykacan/Looking-Glass` commit
`e8550c451444404964d35445a1bf0d72ebd84bb3` on branch `codex/viewers-and-review`,
with a separate commit for each requested item. GitHub publishing is blocked:
HTTPS Git has no usable credentials, and the connected GitHub integration rejects
branch creation with HTTP 403, "Resource not accessible by integration".
No commits have been pushed. A Git bundle preserves the unpublished branch and
can be fetched into a clone containing the base commit:

```bash
git fetch /path/to/Looking-Glass-review.bundle codex/viewers-and-review:codex/viewers-and-review
git push -u origin codex/viewers-and-review
```

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
