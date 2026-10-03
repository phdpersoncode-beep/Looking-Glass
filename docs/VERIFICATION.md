# First milestone verification · 2026-10-03

Latest result: **22 tests passed**, including three browser integration tests.
The frontend was built locally using the committed npm lockfile. No application
dependency is fetched from a CDN at runtime.

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

## Repository delivery

The supplied `altaykacan/Looking-Glass` repository returned 404 through the GitHub
connection, and normal Git cloning had no usable authentication. The connection
lists an installation for `phdpersoncode-beep`, with no accessible Looking-Glass
repository. Existing remote contents/instructions could not be inspected.

This deliverable is a standalone local implementation, with all source, local
build assets, fixtures, tests and setup documentation. It has **not been pushed**
to GitHub or integrated with unseen remote files. The downloadable archive excludes
Git metadata, dependencies, local API tokens and annotation databases.
