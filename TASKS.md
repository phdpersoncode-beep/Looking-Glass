# Requested improvements

Use one feature branch. Update this checklist and commit/push after each implementation.

- [x] Put icon-only resolve/reopen and delete controls together in thread headers.
- [x] Add discussions anchored to specific Git commits and branches in history.
- [x] Keep live Markdown tables rendered for selection/annotation; provide explicit source editing and visible highlights.
- [x] Show and create passage discussions in Markdown reading preview.
- [x] Show an elegant loading indicator in the discussion sidebar.
- [x] Render Mermaid diagrams in live Markdown using local assets.
- [x] Reject oversized files before reading/rendering and show a clear UI warning.
- [x] Enlarge and clarify expand/collapse-all controls for files and threads.

## Additional requests

- [x] Keep explorer filenames/folder names on one line with ellipsis and full-name hover hints at narrow widths.
- [x] Add a minimal expandable contents bar pinned above live Markdown, generated from headings and closed after navigation.
- [x] Make the explorer collapse-all control larger and consistent with discussion controls.
- [x] Add a simple left-chevron explorer toggle with a way to restore the sidebar.
- [ ] Add JSONL previous/next entry arrows and retain the detail pane's scroll position for comparison.

## Verification

- Run frontend and backend tests for affected behavior.
- Rebuild committed frontend assets after frontend changes.
- Verify rendered Markdown/table annotation, history discussions, loading, and file limits in browser tests.

Rendered Markdown/table browser checks cover exact source anchors, repeated cells, entities, Unicode, CRLF, persistent highlights, and preview navigation.

Git-discussion checks cover commit/branch creation, full-reference validation, branch moves/deletion, replies with immutable context, attachments, resolve/delete, history selection, navigation, and reload persistence. Backend: 46 tests pass; frontend: 4 tests pass. Chromium regression checks pass, including the new history workflow.

Final review also covers multiline block quotes/list continuations, escaped table pipes, highlighted code-block discussions, actual table-source edits, invalid-source recovery, and keyboard-accessible commit selection.

Local verification is complete: 46 backend tests, 4 frontend tests, and all 35 Chromium browser tests pass. The frontend rebuild and Python wheel build also pass. The 3D-viewer regression waits for the requested file after asynchronous size preflight before inspecting its renderer.

Narrow-explorer verification covers nested files and folder names at the 120 px minimum width, single-line truncation, full-path hints, and keyboard resizing.

Explorer visibility persists across reloads while retaining its width, folder expansion, tabs, and unsaved document state. Browser checks cover hide/restore, keyboard focus, and interaction with zen mode.

The 30 px live-Markdown contents bar lists formatted ATX/setext headings, excludes fenced-code headings, tracks current drafts, navigates exact source positions (including CRLF), and closes on selection, Escape, or outside clicks. Browser checks cover pinned positioning, navigation, mode/file changes, and documents without headings.
