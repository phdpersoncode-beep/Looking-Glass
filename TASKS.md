# Sidebar and Markdown review improvements

Use this checklist for the current feature branch. Commit and push each completed item with its regression tests and rebuilt frontend assets.

- [ ] Collapse the file explorer to a thin left strip, keeping its restore arrow at the same height and edge.
- [ ] Add a matching thin-strip collapse/restore control for discussions, retaining its width and state.
- [ ] Reduce Markdown margins and give tables more width, with horizontal scrollbars when columns overflow.
- [ ] Restore selection-based commenting on rendered live Markdown tables, preserving exact source anchors.
- [ ] In zen mode, scroll the main pane to the next discussion when resolving the current thread.

## Verification

- Add browser regressions for each item, including Chromium and Firefox.
- Preserve drafts, sidebar widths, table source editing, discussion state, and navigation.
- Run frontend and backend tests, rebuild assets, and build the Python package.
- Run the full browser suite before delivery; record results here.
