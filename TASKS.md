# Whole-app integration and regression coverage

Branch: `test/whole-app-regressions`.

- [x] Merge PR #11 into main (`b8decb0`) and verify the merged PR identity.
- [x] Audit the entire app's desired behavior and document the coverage map in `docs/TESTING.md`.
- [x] Add seven backend and sixteen browser cases spanning editing/review, per-file approval, drafts/undo, discussion editing/search/resolution, immutable origins, attachments, persistence, conflicts, Git staging and HTML smooth-scroll interruption.
- [x] Preserve every existing test; reuse browser processes with fresh contexts and shorten disposable test-server shutdown polling.
- [x] Split the complete Chromium/Firefox suite into four CI shards, with an automated completeness/no-duplicates guard.
- [x] Reproduce and fix native mouse focus moving HTML reading positions; verify four cases fail before and pass after.
- [x] Diagnose pinned-browser repeats, cancel animated HTML restoration explicitly, retain the pointerdown passage identity, and establish stable navigation/geometry before recording context-test baselines.
- [x] Pass 108 backend, 20 JavaScript and 387 browser cases; verify reproducible builds and exact packaged assets.
- [x] Measure the same nine browser cases: 39.70 s before, 22.89 s after. Full four-shard local run: 382.35 s.
- [x] Publish [PR #12](https://github.com/phdpersoncode-beep/Looking-Glass/pull/12) and pass the initial locked-dependency GitHub run: 108 backend, 20 JavaScript and 387 browser cases. The final browser collection includes 391 cases; all checks at the final head must pass before merge. PR #11 itself is already merged.

See `docs/VERIFICATION.md` for results and local browser versions.

---

# Context return and resolved passage presentation

Branch: `feature/context-return-and-resolved-passages` (integrated with main after PR #10).

- [x] Preserve numbered and parenthesized list markers in live Markdown, including nested lists and tasks.
- [x] Render Markdown context with shared headings, tables, lists, and syntax-colored fences; retain read-only code highlighting.
- [x] Treat thread/message context as a temporary tab with Return/Esc and automatic cleanup after resolution, deletion, or unfocus.
- [x] Preserve reader position, undo history, unsaved drafts, and isolated HTML report state on return; omit temporary context from restored sessions.
- [x] Use faint underlines for resolved passages across source, live Markdown, tables, previews, and HTML; preserve local draft anchors and overlapping open highlights.
- [x] Preserve Review mode discussion scope and capture the current draft when replying from an immutable context tab.
- [x] Rebuild production assets and pass backend/frontend and package checks.
- [x] Complete all browser regressions.
- [x] Publish the branch and open [PR #11](https://github.com/phdpersoncode-beep/Looking-Glass/pull/11). The uploaded implementation tree matches the verified local tree.

Verification: 101 backend, 20 frontend and 375 distinct browser cases pass (205 existing plus 170 new, across Chromium and Firefox). Reproducible assets, wheel/source builds, packaged-byte equality and light/dark visual checks pass. See `docs/VERIFICATION.md` for run details and delivery status.

---

# Spotlight navigation and reading-position fixes

Continue on `feature/markdown-discussion-reading-polish` (PR #8).

- [x] Make collapsed sidebar comment icons navigate to the passage and focus its discussion in spotlight.
- [x] Preserve the clicked text's screen position near the viewport bottom, through live syntax and sidebar reflow; keep drag, wheel, and keyboard navigation usable.
- [x] Show a compact Esc hint beside All discussions and verify Escape from both panes.
- [x] Cover the reproduced jumps in Chromium/Firefox, rebuild assets, run regression/package checks, and push the fixes.

Implementation pushed at `8e5f448`: all 161 browser checks pass locally in
Chromium/Firefox, alongside 80 backend and 11 frontend tests. Reproducible assets,
package builds, packaged asset contents, and light/dark visual checks pass.
The GitHub fast job also passes; see `docs/VERIFICATION.md` for coverage and
the workflow link.

---

# Passage sidebar spotlight

Continue on `feature/markdown-discussion-reading-polish` (PR #8).

- [x] Remove floating cards; highlight clicks filter the sidebar to the passage's discussions without moving the reading pane.
- [x] Add a quiet “This passage · N threads” header and “All discussions”; preserve the original list order, scroll position, drafts, and refresh behavior.
- [x] Cover overlapping passages, Markdown tables, HTML reports, dismissal, explicit navigation, and background updates in both browsers.
- [x] Rebuild assets, run regression/package checks, and update the pull request with verification.

Verification at `adf344a`: 131 browser tests pass locally and in the
[locked-dependency workflow](https://github.com/phdpersoncode-beep/Looking-Glass/actions/runs/37911110074).
All 80 backend and 11 frontend tests pass; reproducible frontend assets and
Python wheel/source builds pass. Light/dark layouts were visually inspected.
See `docs/VERIFICATION.md` and [PR #8](https://github.com/phdpersoncode-beep/Looking-Glass/pull/8).

---

# Markdown selections and discussion reading (initial implementation)

Branch: `feature/markdown-discussion-reading-polish`, based on main after merging HTML source annotations (PR #7).

The initial floating-card behavior below is superseded by the passage spotlight above.

- [x] Paint live and reading-preview selections over text only, including wrapped and multiline passages.
- [x] Render discussion messages with the shared Markdown/table/code/diagram renderer at a compact size; preserve raw stored bodies and safe HTML handling.
- [x] Show selected discussions temporarily beside the reading pane without scrolling it; restore their list positions on collapse or defocus and preserve reply drafts through refreshes.
- [x] Cover these behaviors in Chromium and Firefox and run the existing regression suite, asset reproducibility, and package checks.

Verification: 11 frontend tests, 80 backend tests, and all 119 browser checks pass
locally and on GitHub.
Frontend assets rebuild reproducibly; Python wheel/source builds pass. Final locked
dependency verification and coverage are recorded in `docs/VERIFICATION.md` and
[PR #8](https://github.com/phdpersoncode-beep/Looking-Glass/pull/8).

---

# Sidebar and Markdown review improvements

Use this checklist for the current feature branch. Commit and push each completed item with its regression tests and rebuilt frontend assets.

- [x] Collapse the file explorer to a thin left strip, keeping its restore arrow at the same height and edge.
- [x] Add a matching thin-strip collapse/restore control for discussions, retaining its width and state.
- [x] Reduce Markdown margins and give tables more width, with horizontal scrollbars when columns overflow.
- [x] Restore selection-based commenting on rendered live Markdown tables, preserving exact source anchors.
- [x] Restore readable prose margins independently of wide rendered tables in live Markdown and reading preview.
- [x] Match native rendered-table text selections to the editor's purple highlight in both themes.
- [x] Use smaller rendered-table fonts, minimal cell padding, and natural table widths while retaining overflow scrolling.
- [x] In zen mode, scroll the main pane to the next discussion when resolving the current thread.

## Verification

- Add browser regressions for each item, including Chromium and Firefox.
- Preserve drafts, sidebar widths, table source editing, discussion state, navigation, and document shortcuts from focused tables.
- Run frontend and backend tests, rebuild assets, and build the Python package.
- Run the full browser suite before delivery; record the final build/test results in the pull request.

Verification: 73 backend tests and 4 frontend tests pass; reproducible asset and Python package builds pass. New browser regressions pass in Chromium and Firefox. Full-suite results: [PR #5](https://github.com/phdpersoncode-beep/Looking-Glass/pull/5).

## Git history layout bugfix

Branch: `bugfix/git-history-layout`, based on the latest sidebar/Markdown branch (`09309df`).

- [x] Repair the grid mismatch introduced in `81a8954`: the accessible commit button contains graph and text, so its parent row needs two columns, not the original three. Retain keyboard selection.
- [x] Keep graph lanes at their intended width, metadata on one line, and crowded branch labels inside a scrollable area within each row. Narrow panes scroll horizontally rather than squeezing the commit text.
- [x] Hide deselected branch labels while retaining commits reachable from selected branches, including merged ancestry.
- [x] Toggle Select all branches / Deselect all branches; preserve an empty selection across reloads while refreshing the available branch choices.
- [x] Add Chromium/Firefox regressions for crowded local/remote labels, narrow panes, keyboard selection, all/partial/empty branch selections, reloads, and clearing an in-flight request.

The layout regression failed before the fix (text width approximately 42 px; metadata outside the row). Both new regression scenarios pass in Chromium and Firefox. Backend tests: 73 passed; frontend unit tests: 4 passed. Full browser suite: 88 passed, 1 failed (the existing live Markdown encoded-character selection check timed out waiting for Add comment). That check passed when rerun alone on both this fix and the unchanged `09309df` baseline; no Markdown code was changed for it. All 11 history browser tests passed. Frontend assets and Python wheel/source builds succeeded; the repaired layout was also visually inspected.

## Rendered HTML source annotations

Branch: `feature/rendered-html-source-annotations` (from main).

- [x] Parse HTML with source locations; mark only the disposable preview, preserving original bytes and report behavior.
- [x] Map rendered selections to source ranges across tags, entities, Unicode, CRLF, tables, and repeated text.
- [x] Reuse source thread persistence, original context, edits/reattachment, and highlight/navigation in both views.
- [x] Keep legacy and script-generated passages usable as explicitly rendered-only threads; never guess a source range.
- [x] Match Markdown/code selection controls and purple highlights; preserve iframe isolation.
- [x] Add unit, backend, and Chromium/Firefox regressions; run the full suite and package builds.

Verification: 11 frontend tests, 80 backend tests, and all 99 browser tests pass.
Frontend assets rebuild reproducibly; Python wheel/source builds pass. See
[PR #7](https://github.com/phdpersoncode-beep/Looking-Glass/pull/7) and
`docs/VERIFICATION.md` for coverage and test-environment details.

## Non-destructive review mode

- [x] Persistent per-file review drafts, provenance segments, and chronological operation history.
- [x] Revision-checked local API and agent CLI for draft editing and history.
- [x] Minimal edit/review toggle, colored insertions/deletions, and active-file approval.
- [x] Preserve rendered Markdown/tables, syntax highlighting, and review-local discussions.
- [x] Verify persistence, source preservation, approval/conflicts, browser regressions, and bounded performance.

The initial implementation passed 99 backend, 14 frontend, and 175 Chromium/Firefox
browser checks on GitHub. Follow-up regressions cover HTML deletion order/source
mapping and draft context for agent replies. See `docs/VERIFICATION.md` and
[PR #10](https://github.com/phdpersoncode-beep/Looking-Glass/pull/10) for results.
