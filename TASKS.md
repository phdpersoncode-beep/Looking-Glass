# Sidebar and Markdown review improvements

Use this checklist for the current feature branch. Commit and push each completed item with its regression tests and rebuilt frontend assets.

- [x] Collapse the file explorer to a thin left strip, keeping its restore arrow at the same height and edge.
- [x] Add a matching thin-strip collapse/restore control for discussions, retaining its width and state.
- [x] Reduce Markdown margins and give tables more width, with horizontal scrollbars when columns overflow.
- [x] Restore selection-based commenting on rendered live Markdown tables, preserving exact source anchors.
- [x] In zen mode, scroll the main pane to the next discussion when resolving the current thread.

## Verification

- Add browser regressions for each item, including Chromium and Firefox.
- Preserve drafts, sidebar widths, table source editing, discussion state, navigation, and document shortcuts from focused tables.
- Run frontend and backend tests, rebuild assets, and build the Python package.
- Run the full browser suite before delivery; record the final build/test results in the pull request.

Verification: 73 backend tests and 4 frontend tests pass; reproducible asset and Python package builds pass. New browser regressions pass in Chromium and Firefox. Full-suite results: [PR #5](https://github.com/phdpersoncode-beep/Looking-Glass/pull/5).
