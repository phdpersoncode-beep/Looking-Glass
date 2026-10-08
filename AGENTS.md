# Looking Glass

## Purpose and goals
A local prose/code editor and review tool for working with coding agents on ordinary files. Persistent, passage-anchored discussions are the priority: highlight text, exchange comments, and navigate editing passes. Keep a small architecture and a clean Notion-style experience with Obsidian-style live Markdown.

## Current capabilities
- CodeMirror editing: live/raw/preview Markdown with a pinned heading-contents bar in live mode, rendered passage/table annotations, explicit table source editing, local Mermaid diagrams, plain text, Python/Bash highlighting, undo/redo, save, search/replace, tabs, fuzzy file search, and Git change gutters.
- Persistent source/HTML threads: replies, attachments/renaming, resolve/reopen, deletion, cross-file navigation, collapse controls, commit anchors/original-context tabs, and reattachment. Clipboard screenshots and files use compact comment composers. Loading feedback and file-size warnings. Resizable sidebars; zen mode uses Ctrl+Alt+Z, preserving Ctrl+Z undo.
- Interactive sandboxed HTML reports with rendered-to-source annotations (runtime-only text keeps rendered anchors), split JSONL viewer with search, entry arrows, and retained detail scroll position, and ASCII/binary STL viewing with orbit/pan/zoom/fit and software fallback.
- Directory switching, outside-file opening, a resizable/hideable explorer with truncated names and full-path hints, external-change detection, conflict comparison, selected-file Git checkpoints, a paged multi-branch commit graph with commit/branch discussions, and agent project discovery/search/context.

## Constraints
- Python 3.10+, Flask, HTMX, SQLite, CodeMirror 6, Tailwind, and Three.js. Build application assets locally; no CDN dependencies.
- Disk files are authoritative; preserve ordinary Markdown/plain text. SQLite holds discussions/metadata in `<workspace>/.looking-glass/`; never commit its database or token.
- Reload clean external changes; preserve dirty drafts and reject stale saves. Ambiguous/deleted live anchors need reattachment; immutable review context stays readable.
- Saving never commits. Git checkpoints are explicit and preserve unrelated staged/unstaged work.
- Loopback-only server; isolate report scripts from editor state/tokens. Agents run separately through the local interface; no built-in model calls or project-code execution.
- Minimalist light/dark themes, neon-purple highlights, monospace code/JSON, and locally bundled Newsreader prose. Preserve Ctrl+A/F/H and selection-aware shortcuts.

## Run and build
From the repository root (uv and Git required; Node 20+ for frontend builds):
```bash
uv sync
uv run looking-glass serve ./demo_dir  # http://127.0.0.1:8765
npm ci
npm run build                        # rebuild committed static assets
uv build                             # Python wheel/source distribution
npm test
uv run pytest -m 'not browser' -q
LOOKING_GLASS_BROWSER=installed uv run pytest -m browser -q  # playwright install chromium firefox first
```

For a CLI available from any directory:
```bash
uv tool install --editable /absolute/path/to/Looking-Glass
looking-glass serve /absolute/path/to/project
```

With the server running, in another terminal:
```bash
looking-glass projects list
looking-glass agent --root /absolute/path/to/project list --status open
looking-glass agent --root /absolute/path/to/project read 1 --context-lines 10
looking-glass agent --root /absolute/path/to/project reattach 1 --quote 'Exact replacement passage'
looking-glass agent --root /absolute/path/to/project reply 1 --author Codex --body 'Reply'
```
Use `uv run looking-glass` from this checkout if not installed globally. See `--help`, `agent instructions`, and `docs/AGENT_API.md` for remaining commands.

## Repo map
Keep this map and commands current when structure or workflows change.
- `looking_glass/app.py`: routes/security; `workspace.py`: files, SQLite, threads; `anchors.py`: anchor mapping; `revisions.py`: Git checkpoints/history; `origins.py`: immutable review context.
- `looking_glass/cli.py`: server/agent commands; `projects.py`: project registry; `instructions.py`: agent guidance; `attachments.py`: thread-owned uploads.
- `looking_glass/templates/`: HTML/HTMX; `frontend/app.js`, `frontend/style.css`, and small `.mjs` modules: client sources; `looking_glass/static/`: committed output of `build.mjs`.
- `tests/`: backend/CLI/browser checks; `.github/workflows/`: automated checks; `scripts/benchmark_discussions.py`, `scripts/benchmark_anchors.py`: disposable benchmarks; `demo_dir/`: fixtures; `docs/`: API, architecture, performance, verification.
- `pyproject.toml`, `uv.lock`: Python packaging/dependencies; `package.json`, `package-lock.json`: frontend dependencies.
