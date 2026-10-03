# First milestone

One Flask process serves a loopback-only application and a small JSON HTTP API.
Files under the chosen project root are authoritative; SQLite stores threads,
messages, anchor positions and the last observed file text used for reconciliation.
CodeMirror 6 owns document editing and undo history. HTMX refreshes the file tree
and discussion sidebar. A locally bundled JavaScript module owns tabs, editor
decorations and Three.js viewers; Tailwind is compiled locally.

```
looking_glass/
  app.py         HTTP routes, loopback/token protection
  workspace.py   file reads, optimistic saves, SQLite discussions
  anchors.py     conservative anchor mapping across edits
  revisions.py   selected-file Git checkpoints with a temporary index
  cli.py         server and agent commands
  templates/     application shell and HTMX fragments
  static/        committed local build assets
frontend/        client source and Tailwind source
demo_dir/        Markdown, text, code, JSONL, HTML, ASCII and binary STL
tests/          persistence, conflict, anchors, isolation, Git and browser checks
```

The server opens one directory per invocation. A root-bound database at
`.looking-glass/state.sqlite3` and a persistent local API token sit inside it.
Choosing another directory means restarting the server with that directory.
This keeps permissions and agent routing explicit.

Anchors use Unicode character offsets plus quotes and context. Sequence matching
maps unchanged passages and ordinary edits inside a passage. Removed passages,
duplicate relocation candidates and uncertain matches become `needs_reattachment`.
Dirty editor ranges are mapped immediately by CodeMirror; server reconciliation
is authoritative after save or external change. Thread creation first saves a
dirty document and verifies the current content hash.

HTML uses a sandboxed iframe without `allow-same-origin`. Creating a preview needs
the application token; its separate temporary URL grants access only to that HTML.
Report scripts receive no API token and cannot read the parent or call protected APIs.
The preview is self-contained; local linked assets and rendered-HTML annotations
are deferred. Source HTML supports the same anchored discussions as code.

Git is optional until a user explicitly initializes a repository. Saving never
commits. Checkpoints build a temporary index from HEAD, add only selected paths,
create a commit, and advance HEAD with compare-and-swap. Selected pre-staged files
are rejected. Unrelated staged files, unstaged files and untracked files stay intact.

Verification focuses on data preservation: edits, stale saves, deleted/ambiguous
anchors, SQLite restarts, token isolation, path traversal, selected checkpoints,
and the browser workflow. No models are called and no files are executed.
