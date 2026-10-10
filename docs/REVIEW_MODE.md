# Non-destructive review mode

## Operating contract

Edit mode continues to edit ordinary disk files. Review mode is a workspace-wide viewing preference, with one persistent draft per text file, created lazily when the file is opened in review mode. Switching modes preserves both the original and review draft. Approval applies only the active reviewed file and returns to edit mode.

- Keep the base bytes/hash, accepted draft, compact provenance segments, and chronological edit events in SQLite. Deleted base segments remain visible ghosts; insertions carry human/agent role, author, and UTC timestamp. Store edit operations rather than full document copies for every keystroke.
- Track direct insert/delete/replace operations with optimistic review revisions. Human additions are green, agent additions blue, and removals red/struck through. Hover reveals author/time. Editing inserted text updates net changes while the event log retains every action.
- Reuse CodeMirror and existing Markdown/table rendering, source mappings, comments, search, syntax highlighting, tabs, and navigation. Render deleted source as inert text, never executable Markdown/HTML syntax. Approved output contains only accepted text.
- Keep review anchors separate from ordinary file anchors. New review discussions remain with the draft until approval; existing discussions get review-local anchor copies. Retain immutable original context for removed passages.
- Existing discussions share messages and resolved state across modes; only their passage positions are independent. Removed-passage context survives approval even when the approved file no longer contains that passage.
- Expose draft reads, incremental edits, revision-checked updates, and paginated event history through the authenticated local API and agent CLI. Agent changes use these operations, not filesystem writes. Approval is a human UI action.
- Refuse approval if the disk original or review revision changed. Preserve the draft, offer comparison with disk, and never silently overwrite concurrent work.
- Keep edit mode's polling path unchanged. Conditional revision polling in review mode returns no content when unchanged. Coalesce human edits and avoid whole-file diffing on every edit/poll.

## Specification decisions

There are no blocking contradictions. Literal zero additional resources is impossible: review drafts and authorship require storage. The goal is bounded, lazy overhead. Deletion color remains red regardless of author; agent insertions are blue and deletion tooltips record authorship. A mode toggle affects viewing across files; approval applies to one file at a time. Unsupported binary/viewer formats keep their existing viewers.

The existing 8 MiB text limit applies to accepted drafts. Approval writes accepted text without display markup and does not create a Git commit. Drafts, provenance, and history remain local metadata. If an interrupted approval already wrote exactly the accepted draft, retrying may finish promotion of its discussion anchors without overwriting different disk bytes.

## Verification scope

Backend: persistence/restart, provenance and Unicode/CRLF operations, author/time history, optimistic conflicts, original byte preservation, approval exactness/file permissions, external changes/deletion, separate comment anchors, authentication/limits, CLI contracts.

Frontend/browser: edit/review toggle and reload, human/agent colors, deletions, undo/redo, live/preview Markdown tables and code, comments on inserted/deleted passages, sidebar/spotlight behavior, concurrent edits, approval, light/dark themes, and existing regressions.

Performance: operation-based edits/history growth and unchanged polling; compare edit-mode regressions and representative large review documents.

See [VERIFICATION.md](VERIFICATION.md) for completed runs and [PERFORMANCE.md](PERFORMANCE.md) for measured costs. Agents use the commands in [AGENT_API.md](AGENT_API.md). Drafts and history stay in local workspace metadata; generated bundles contain application code only.
