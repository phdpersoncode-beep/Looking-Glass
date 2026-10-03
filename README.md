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
the tree. Folder expansion persists across refreshes. Common dependency, Git and application metadata folders
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
The application asks for confirmation before deletion.

Ctrl+P opens fuzzy file search throughout the application and overrides browser printing.
Type parts of a filename or path, use ↑/↓ to select, and press Enter to open.
Escape closes the picker. The picker includes workspace files and open outside files.
Use **A− / A+** in the document toolbar to adjust document text size.
The setting persists. Toolbar, sidebar, and search controls keep their size.
Live Markdown task lists display clickable checkboxes. The active line exposes
ordinary Markdown syntax. Checkbox clicks update the Markdown draft; save to write it.

Ctrl+A selects the active editor document. Ctrl+F and Ctrl+H open CodeMirror's
document search/replace panel. Ctrl+Z and Ctrl+Shift+Z undo/redo. On macOS, use
Command in place of Ctrl. Browser/input shortcuts retain their normal meaning
when focus is outside the editor. Python and Bash have basic syntax highlighting.
Text and Markdown use Times New Roman with Times/serif fallback; code/JSON use
your system monospace font. The top-right button switches light/dark themes.

Tabs have pin and close buttons. Right-click a tab to close the other unpinned
tabs. Unsaved tabs ask before discarding edits. Pinned tabs are protected by
“Close other tabs”, but can still be closed individually.

## Work alongside a coding agent

Keep the server running. Make the `looking-glass` command available in your agent's
environment. Either run `uv run looking-glass ...` from this repository, or install it
as a global tool with `uv tool install /path/to/Looking-Glass`.
The CLI (command-line interface) uses a small local HTTP API, documented in
[docs/AGENT_API.md](docs/AGENT_API.md).

Click **Agent instructions** beneath the file explorer, then **Copy instructions**.
Paste the instructions into your coding agent. Commands include the current workspace,
server address, and this installation's path, so the agent can run them from any directory.

```bash
uv run looking-glass agent --root ./demo_dir list
uv run looking-glass agent --root ./demo_dir list --path welcome.md
uv run looking-glass agent --root ./demo_dir read 1
uv run looking-glass agent --root ./demo_dir create welcome.md \
  --quote 'Select this passage' --author Codex \
  --body 'Can we add a concrete example here?'
uv run looking-glass agent --root ./demo_dir reply 1 --author Codex \
  --body 'I suggest explaining the disk-file workflow first.'
uv run looking-glass agent --root ./demo_dir resolve 1
uv run looking-glass agent --root ./demo_dir reopen 1
uv run looking-glass agent --root ./demo_dir delete 1 --message 2
uv run looking-glass agent --root ./demo_dir delete 1
```

Pass `--root` as the workspace the server has open now. For a file outside the
workspace, pass its absolute path, e.g. `create /home/you/notes.md --quote ...`.
Use `--url http://127.0.0.1:8766` after `--root` if the server uses another port.
`create` requires a unique exact quote. For repeated text, provide a one-based
`--occurrence`. All commands return JSON. Thread IDs come from `list` or `create`.
Comments never automatically apply edits.

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
after saving. They reset after a checkpoint. Files outside Git have no markers.

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

- **JSONL:** all raw lines on the left, selected JSON value formatted on the right.
  Malformed and empty lines are marked individually; other rows still work.
  Ctrl+F searches all raw rows, including malformed rows. Enter and Shift+Enter
  move between matching rows. Escape closes search.
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
uv run pytest -q
uv run playwright install chromium
LOOKING_GLASS_BROWSER=installed uv run pytest tests/test_browser.py -v
```

For an already-installed Chromium, set `LOOKING_GLASS_BROWSER` to its executable
path. The browser test copies `demo_dir` into a disposable directory and verifies
editing/saving, UI and terminal discussions, a server restart, external changes,
JSONL/STL/HTML viewers, HTML isolation, and selected Git checkpoints.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the repository plan,
[docs/LIMITATIONS.md](docs/LIMITATIONS.md) for deferred work, and
[docs/VERIFICATION.md](docs/VERIFICATION.md) for results.

If this project was delivered as an archive, extract it into your checked-out
Looking-Glass repository and review the diff before committing. The archive
contains no Git history, environments, API tokens, or annotation databases.
