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

## Verification

- Run frontend and backend tests for affected behavior.
- Rebuild committed frontend assets after frontend changes.
- Verify rendered Markdown/table annotation, history discussions, loading, and file limits in browser tests.

Rendered Markdown/table browser checks cover exact source anchors, repeated cells, entities, Unicode, CRLF, persistent highlights, and preview navigation.

Git-discussion checks cover commit/branch creation, full-reference validation, branch moves/deletion, replies with immutable context, attachments, resolve/delete, history selection, navigation, and reload persistence. Backend: 46 tests pass; frontend: 4 tests pass. Chromium regression checks pass, including the new history workflow.

Final review also covers multiline block quotes/list continuations, escaped table pipes, highlighted code-block discussions, actual table-source edits, invalid-source recovery, and keyboard-accessible commit selection.
