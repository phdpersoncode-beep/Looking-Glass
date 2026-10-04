# Milestone boundaries

- One open workspace at a time per server. Switching workspaces reloads the page
  and drops tabs from the previous workspace. No multi-user collaboration, built-in model calls, or editing-pass orchestration.
- Rendered HTML annotations cover selectable document text, including script-generated
  text. Canvas, images, nested frames, and shadow DOM have no text anchors.
  Highlights require the browser's CSS Custom Highlight API. Anchor matching occurs
  when the report is open; runtime-only content must reappear after reopening.
  Large DOM updates can delay matching. Reports that replace the entire document,
  block injected scripts with their own security policy, or contain malformed script
  markup can prevent the annotation bridge from running.
  HTML reports should be self-contained: no local relative CSS, JavaScript or image
  resources. External HTTPS resources may still be loaded by report scripts.
  Report navigation, nested frames, form submission and application-origin
  requests are restricted. HTML is not a general unrestricted browser.
- Live Markdown supports heading styling, emphasis, inline code, links, quote
  styling, list markers, interactive task checkboxes, editable rendered tables, and
  syntax exposure at the active line. Fenced Python, Bash, JSON, and HTML have basic
  highlighting; unrecognized languages remain plain text. Markdown images and
  other block layouts are best viewed in the reading preview. It is a first inline
  Markdown editor, not feature parity with Obsidian.
- PNG/JPEG/SVG, JSONL and STL are viewers without editing or annotations.
  Image zoom and pan are view-only; SVG scripts are inert in the image viewer. The JSONL left side
  is a raw row list; basic JSON syntax highlighting is on the formatted right.
  STL uses WebGL with an SVG software fallback when WebGL is unavailable.
  Large software previews sample up to 12,000 triangles, which can omit small
  features; use WebGL for full detail. Unsupported/broken STL shows an error
  inside the viewer instead of geometry.
- Text files must be UTF-8 and at most 8 MiB. Uniform CRLF/LF line endings and
  executable mode are preserved. Mixed line endings are normalized to the first
  detected style during editing. STL and image files are limited to 64 MiB. The file list
  is capped at 10,000 entries; no lazy tree or large-file virtualization yet.
- Anchor reconciliation is conservative, character-based and optimized for
  small review documents. Large rewrites and moved/duplicated passages may need
  manual reattachment. It is not a semantic diff or collaborative editing system.
- External changes use polling while the browser tab is visible. A stale save
  is checked again just before an atomic file replacement, but another process
  can still race in the final interval because ordinary filesystem writes have
  no universal compare-and-swap. Coordinate saves when multiple tools edit the
  same file simultaneously. Multi-server use of one workspace is unsupported.
- Drafts live in the current browser session. Tab switches retain undo history;
  a browser reload/close warns about unsaved work but does not restore drafts.
  Thread history is durable in SQLite. It is not yet exported into Git commits.
- Tab pinning and author/theme preferences are local browser metadata. Close
  other tabs preserves pinned tabs. The UI is desktop-focused.
- Git gutter indicators compare the current draft with HEAD. Diff computation has
  a time limit for large rewrites, which can reduce marker detail. Reading previews
  and image/JSONL/STL viewers have no Git gutter. Ignored untracked files also
  have no gutter; tracked files still show changes regardless of ignore patterns. Font controls apply to editor documents,
  Markdown reading previews, and JSONL; isolated HTML reports keep their own styling.
- Checkpoints preserve unrelated changes, but selected pre-staged files and
  in-progress merges/cherry-picks/reverts must be handled in the terminal. No
  Git history viewer, amend, branch management, push or automatic commit exists.
  Checkpoints use Git plumbing; commit hooks and automatic commit signing are
  not invoked in this milestone.
  Avoid concurrently changing Git's HEAD/index while creating a checkpoint.
- The server is for trusted local use on loopback, without remote account auth
  or TLS. It runs the lightweight Werkzeug server with no debugger. Filesystem
  confinement blocks ordinary traversal and symlinks, not hostile local processes
  replacing directories in the middle of a request. The API also opens files outside
  the workspace by absolute path, so the token grants read/write access to every
  file your user can access. Only grant it to agents you trust with that.
- SQLite snapshots contain last-observed text to map anchors. Disk files remain
  authoritative; snapshots are not a backup or alternate document store.
- Agent commands require a running server. The project registry keeps the last
  address for each root; stopped or switched-away projects remain listed as unreachable.
  Servers started before an upgrade must restart to expose updated API routes.
  Search covers one selected project per call. It loads threads before filtering;
  pagination limits output, but does not yet reduce database or reconciliation work.
