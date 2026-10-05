# Looking Glass

A local editor for reviewing files with coding agents. Select a passage, start
a persistent discussion, and let an agent read or reply from its own terminal.
Project files on disk stay authoritative. Saving writes a file; a Git checkpoint
is a separate, explicit action.

## Install and run

Requires [uv](https://docs.astral.sh/uv/), Git, and a modern browser. uv installs
Python 3.10+ for you when none is available. WebGL accelerates STL viewing;
a software preview is available when it is unavailable.
The local frontend build is included, so Node is needed only to change the frontend.

```bash
uv sync --no-dev
uv run looking-glass serve ./demo_dir
```

`uv sync` creates `.venv/` and installs the locked dependencies from `uv.lock`.
`uv run` syncs the environment before each command. To use the `looking-glass`
command without the `uv run` prefix, run `source .venv/bin/activate` first.

To install the CLI (command-line interface) as a user-level tool available from any directory:

```bash
uv tool install --editable /absolute/path/to/Looking-Glass
looking-glass --help
looking-glass serve /absolute/path/to/project
```

Editable installation follows changes in this checkout. Ensure `~/.local/bin` is
on your `PATH`; `uv tool update-shell` can configure your shell if needed.

Open http://127.0.0.1:8765. To work on another local directory:

```bash
uv run looking-glass serve /absolute/path/to/project --port 8765
```

The server binds to loopback and serves one directory at a time. **Open directory**
browses the filesystem and switches the running server to another workspace.
The terminal prints the new root, and the API token changes with it.
**Open file** opens any readable file by path, e.g. `~/notes.md` or
`/home/you/.claude/projects/<project>/<session>.jsonl`. Files outside the
workspace are keyed by their resolved absolute path. Their discussions are stored
in the current workspace. The file sidebar lists files recursively
as a collapsible tree and supports filtering. Use **Collapse all folders** to fold
the tree. Drag the sidebar divider to resize the explorer; its width persists across
refreshes. The focused divider also supports arrow keys, Home/End, and double-click
to reset. Folder expansion persists across refreshes. Common dependency, Git and application metadata folders
are excluded. Symlinks are not opened. No project code is executed.

## Review a file

1. Open Markdown, text or code from the left sidebar.
2. Edit directly. Markdown has inline live formatting, raw source and reading preview.
3. Select a passage and click the floating **＋ Add comment** button beside it
   (or the toolbar button, or Ctrl+Enter in the editor). Markdown stays stable
   while you drag across formatted passages.
4. Write in the compact composer next to your selection. Click **Start thread**
   or press Ctrl+Enter to post; Escape cancels. A dirty file is saved before its
   new thread is anchored.
5. Click a highlight or **View thread** beside a selected highlight to open its
   discussion in the sidebar. Reply, resolve/reopen, or use ↑/↓ to move between
   passages. Reply fields appear for the active thread.
6. Save with Ctrl+S. The dot on a tab marks an unsaved draft.

Use **×** beside a comment to delete that comment. **Delete thread** removes the
whole discussion and its highlight. Deleting the last comment also removes its thread.
The application asks for confirmation before deletion. Turn on **Across files** above
the discussions to see threads throughout the workspace, including outside files
opened in this workspace. ↑/↓ always traverses discussions across files, even when
the toggle is off, and preserves unsaved drafts. Navigation stays at the top.

Drag the discussions divider to resize it; the width persists. Collapse a thread
with its chevron and reopen it with its comment icon. The header also has collapse-all
and expand-all controls. **Zen mode** (top-bar button or **Ctrl+Alt+Z**, **Cmd+Alt+Z**
on macOS) hides the file explorer and tabs and expands only the focused thread.
Leaving zen restores the normal collapse settings. **Ctrl+Z remains undo.**

Use **Attach files** on a thread to upload images, STL, JSON, or other files
(up to 64 MiB each). Images can be previewed; all attachments can be downloaded,
renamed, or removed. They live with discussion data in `.looking-glass/attachments/`,
not beside the reviewed document. Deleting a thread removes its attachments.

The JSON toolbar's **Format JSON** button indents a compact JSON document without
rounding large numbers or removing duplicate keys. Formatting is undoable and stays
unsaved until you save. Invalid JSON stays unchanged and produces an error.

Ctrl+P opens fuzzy file search throughout the application and overrides browser printing.
Type parts of a filename or path, use ↑/↓ to select, and press Enter to open.
Escape closes the picker. The picker includes workspace files and open outside files.
Use **A− / A+** in the document toolbar to adjust document text size.
The setting persists. Toolbar, sidebar, and search controls keep their size.
Live Markdown task lists display clickable checkboxes. The active line exposes
ordinary Markdown syntax. Checkbox clicks update the Markdown draft; save to write it.
Markdown tables render in live mode; click a table to edit its source. Fenced Python,
Bash, JSON, and HTML blocks have basic syntax highlighting in live/source mode and
reading preview. Inactive fence markers and language labels are hidden in live mode.

Ctrl+A selects the active editor document. Ctrl+F and Ctrl+H open CodeMirror's
document search/replace panel. Ctrl+Z and Ctrl+Shift+Z undo/redo. On macOS, use
Command in place of Ctrl. Browser/input shortcuts retain their normal meaning
when focus is outside the editor. Python and Bash have basic syntax highlighting.
Text and Markdown use locally bundled Newsreader with Times/serif fallback; code/JSON use
your system monospace font. The top-right button switches light/dark themes.

Tabs have pin and close buttons. Right-click a tab to close the other unpinned
tabs. Unsaved tabs ask before discarding edits. Pinned tabs are protected by
“Close other tabs”, but can still be closed individually.

## Work alongside a coding agent

Keep the server running. Install the CLI with the user-level command above.
You can also use `uv run looking-glass ...` from this repository.
The CLI uses a small local HTTP API, documented in
[docs/AGENT_API.md](docs/AGENT_API.md).

You can use the following concise instructions for your coding agent as user level settings:
```
Use the looking-glass CLI if it is installed to collaborate with me. It is for reviewing project discussions. The local server must be running. Discover projects with `looking-glass projects list` and inspect files with `looking-glass projects show PATH`. From inside a project:
- Find open threads: `looking-glass agent list --status open`.
- Search comments: `looking-glass agent search "TEXT" --status open`.
- Read messages and passage context: `looking-glass agent read ID --context-lines 10`.
- Reply: write the Markdown reply to a UTF-8 file, then use `looking-glass agent reply ID --author "Agent" --body-file reply.md`.
- Resolve completed work: `looking-glass agent resolve ID`.

Read context before replying. Ask for guidance on detached anchors.

Use `looking-glass agent --root PATH ...` from another directory.

Follow `next_offset` with `--offset` for additional pages.

Append `--help` when you need help with a command. Run `looking-glass agent instructions` for the full guide.
```

Click **Agent instructions** beneath the file explorer, then **Copy instructions**.
Paste the instructions into your coding agent. Commands use the installed executable
and include the current workspace and server address.

```bash
looking-glass projects list
looking-glass projects show /absolute/path/to/project
looking-glass agent --root ./demo_dir list --status open
looking-glass agent --root ./demo_dir search 'example' --status open
looking-glass agent --root ./demo_dir list --path welcome.md --author Altay
looking-glass agent --root ./demo_dir read 1 --context-lines 10
looking-glass agent --root ./demo_dir create welcome.md \
  --quote 'Select this passage' --author Codex \
  --body 'Can we add a concrete example here?'
looking-glass agent --root ./demo_dir reply 1 --author Codex \
  --body 'I suggest explaining the disk-file workflow first.'
looking-glass agent --root ./demo_dir resolve 1
looking-glass agent --root ./demo_dir reopen 1
looking-glass agent --root ./demo_dir delete 1 --message 2
looking-glass agent --root ./demo_dir delete 1
looking-glass agent --root ./demo_dir instructions
looking-glass agent search --help
```

Omit `--root` when your current directory is inside the project. The CLI finds the
nearest ancestor with Looking Glass metadata or a registered root. Otherwise,
pass `--root` as the workspace the server has open now. For an outside file,
pass its absolute path, e.g. `create /home/you/notes.md --quote ...`.
The CLI uses the registered server address. Override it with `--url http://127.0.0.1:8766`
before the operation. The CLI verifies the server's project root before accessing threads.
`create` requires a unique exact quote. For repeated text, provide a one-based
`--occurrence`. Commands return JSON; `instructions` prints copyable text.
Thread IDs come from `list`, `search`, or `create`.
Comments never automatically apply edits.

For Markdown bodies, use `--body-file reply.md`, or pipe text into `--body-stdin`
(`--body-file -` also reads stdin). `create` and `reply` accept exactly one of these
or `--body`. Shell double quotes still execute backticks and `$(...)` before the
CLI runs; body files and quoted here-documents avoid that substitution. See the
[body input examples](docs/AGENT_API.md) for safe multiline replies.

`list` and `search` return paginated summaries with `threads`, `total`, `limit`,
`offset`, and `next_offset`. Use `--limit` and `--offset` to page through results.
Use `--full` for all messages. Filters include `--status all|open|resolved`,
`--path`, `--author`, and `--anchor-status attached|needs_reattachment`.
Search matches literal, case-insensitive text in quotes and all comment bodies.
`read` returns all messages and current passage context. Rendered HTML returns
the visible quote and its surrounding anchor text. Detached anchors have no source context.

`serve` registers projects under `~/.config/looking-glass/projects.sqlite3`.
Browser directory switches also register the new root. `projects list` reports
known roots, addresses, and reachability, including stopped projects.
`projects show` lists current disk file paths and thread counts for a running project.
`XDG_CONFIG_HOME` changes the configuration base; `LOOKING_GLASS_CONFIG_DIR`
overrides the Looking Glass configuration directory. The registry stores no tokens.
Append `--help` to any command for options and an example.

## External edits and anchors

Open tabs are checked about every two seconds while the browser tab is visible.
Clean documents reload. Dirty documents retain their draft and show a conflict
banner. Compare the disk file with your editable draft, accept a merged draft,
then save. Saves check a content hash and reject stale writes. You may instead
copy the draft, or explicitly discard it and reload. Deleted files show a warning.
The file list refreshes every twelve seconds, with a manual refresh button.

Highlights map through ordinary edits and insertions. Removed or ambiguous
passages show **needs reattachment**. Select the correct new passage and click
**Attach to selection**. SQLite stores discussion history under
`<project>/.looking-glass/`; keep that directory to retain comments across restarts.
Do not share its API token or commit this directory. Add `.looking-glass/` to
your project's `.gitignore`; the included repository already does this.

## Git checkpoints

Code, Markdown, and text editors show changes against the last Git commit in their
left gutter. Green bars mark added lines. Blue bars mark changed lines.
Red horizontal triangles mark removed lines. Markers include unsaved drafts and remain
after saving. They reset after a checkpoint. Files outside Git and ignored untracked files have no markers. Tracked files
continue showing changes even when they match an ignore pattern.

Choose **Changes & checkpoints**, select saved files, inspect their changes,
and give the checkpoint a name. Looking Glass reuses the enclosing repository.
When there is none, it offers an explicit **Initialize Git** button. Configure
your Git identity in your terminal before the first checkpoint if needed:

```bash
git config user.name 'Your Name'
git config user.email 'you@example.com'
```

Only selected paths are committed. Unrelated staged, unstaged and untracked work
is preserved. Selected files with existing staged changes are rejected; handle
them in your terminal first. Checkpoints do not push. Saving never commits.

## Viewers

- **PNG, JPEG, SVG:** view images with zoom buttons, wheel zoom, actual size, fit,
  and drag to pan. SVG runs as an image, so embedded scripts do not execute.
- **JSON:** collapse all objects/arrays, then unfold individual entries using their
  fold markers. **Expand all** restores the complete tree. The same controls appear
  in the formatted JSONL pane.
- **JSONL:** all raw lines on the left, selected JSON value formatted on the right.
  Malformed and empty lines are marked individually; other rows still work.
  Ctrl+F searches all raw rows, including malformed rows. Enter and Shift+Enter
  move between matching rows. Escape closes search. **Download** saves the JSONL
  file with its original filename.
- **STL:** ASCII (text) and binary STL; drag to orbit, right-drag to pan, scroll
  to zoom, and use **Fit to view**. Uses WebGL when available, with an SVG
  software fallback. Software previews of large models reduce detail to 12,000
  sampled triangles and are labeled accordingly. Invalid files show an error
  inside the viewer.
- **HTML:** rendered interactive report or raw editable source. The iframe has
  an opaque sandbox origin, no application API token and no access to parent
  state. Inline scripts and HTTPS report resources are allowed. Use self-contained
  reports; workspace-relative linked assets are not currently served to previews.
   Select visible report text and use **Add comment** or Ctrl+Enter to annotate
   rendered HTML. Highlights and passage navigation stay in the report.
   Ctrl/Cmd+P opens the application file picker even when the report has focus.
   **Download** saves the current HTML draft for opening directly in a browser,
   without saving pending edits to the workspace. Self-contained reports retain
   their scripts and styling in the downloaded file.
   Source HTML also supports anchored comments. Each thread records its anchor mode.
   Rendered anchors store the selected text and surrounding context. Missing or
   ambiguous passages request reattachment. Select a new rendered passage and click
   **Attach to selection**. Comments persist in SQLite; the HTML file stays unchanged.

## Development and checks

Use Node 20+ to rebuild all assets locally; no CDN (content delivery network)
is used for application dependencies.

```bash
npm ci
npm run build
uv sync   # includes the dev dependency group
npm test
uv run pytest -m 'not browser' -q  # fast backend and CLI contracts
uv run playwright install chromium firefox
LOOKING_GLASS_BROWSER=installed uv run pytest -m browser -q
```

For native Wayland selection checks, run Firefox with visible windows inside
your Linux Wayland desktop session (Firefox must be installed by Playwright):

```bash
MOZ_ENABLE_WAYLAND=1 LOOKING_GLASS_HEADED=1 LOOKING_GLASS_BROWSER=installed \
  uv run pytest tests/test_requested_features.py -k "linux_text_selection and firefox" -q
```

The selection regression covers Chromium and Firefox, forward/backward and
multiline drags, existing annotations, and recovery after missed release events.

For an already-installed Chromium, set `LOOKING_GLASS_BROWSER` to its executable
path. The browser test copies `demo_dir` into a disposable directory and verifies
editing/saving, UI and terminal discussions, a server restart, external changes,
JSONL/STL/HTML viewers, HTML isolation, and selected Git checkpoints.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the repository plan,
[docs/LIMITATIONS.md](docs/LIMITATIONS.md) for deferred work, and
[docs/VERIFICATION.md](docs/VERIFICATION.md) for results.
See [docs/PERFORMANCE.md](docs/PERFORMANCE.md) for measurements, the Rust-port
decision, and regression requirements. GitHub Actions runs fast checks and a separate
Chromium/Firefox browser job on pushes and pull requests.

If this project was delivered as an archive, extract it into your checked-out
Looking-Glass repository and review the diff before committing. The archive
contains no Git history, environments, API tokens, or annotation databases.


### Review history and screenshots

Open **Commit history** at the top of the file sidebar. It opens a normal tab with
newest-first branch/merge lanes, a branch filter dropdown, colored identities,
branch labels, and older-commit pagination. Hover a row for its full message;
click for the full message and author/committer details. Remote branches reflect
what your local Git repository has already fetched.

Each thread and comment has a commit/context button. It opens the saved reviewed
source read-only, even after the file or passage disappears. New comments record
HEAD and keep the exact source snapshot; uncommitted work remains recoverable.
Existing discussions are labelled **Recovered context** when their original
commit was never recorded.

Use the dim paperclip beside a comment/reply box, or focus that box and paste a
clipboard screenshot with **Ctrl+V**. Small pending chips can be renamed or
removed before sending. Files belong to the posted comment; image-only comments
are supported. Click an image filename to preview it, or use **⋯** for download,
rename, and removal. Text and files stay in the composer if sending fails.
