# Looking Glass

## Purpose and goals
A local prose/code editor and review tool for working with coding agents on ordinary files. Persistent, passage-anchored discussions are the priority: highlight text, exchange comments, and navigate editing passes. Keep a small architecture and a clean Notion-style experience with Obsidian-style live Markdown.

## Current capabilities
- CodeMirror editing: live/raw/preview Markdown, plain text, Python/Bash highlighting, undo/redo, save, search/replace, tabs, fuzzy file search, and Git change gutters.
- Persistent threads on source text and rendered HTML: replies, resolve/reopen, deletion, passage navigation, and reattachment.
- Interactive sandboxed HTML reports, split JSONL viewer with search, and ASCII/binary STL viewing with orbit/pan/zoom/fit and software fallback.
- Directory switching, outside-file opening, external-change detection, conflict comparison, selected-file Git checkpoints, and agent project discovery/search/context.

## Constraints
- Python 3.10+, Flask, HTMX, SQLite, CodeMirror 6, Tailwind, and Three.js. Build application assets locally; no CDN dependencies.
- Disk files are authoritative; preserve ordinary Markdown/plain text. SQLite holds discussions/metadata in `<workspace>/.looking-glass/`; never commit its database or token.
- Reload clean external changes; preserve dirty drafts and reject stale saves. Ambiguous/deleted anchors need reattachment.
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
uv run pytest -q
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
looking-glass agent --root /absolute/path/to/project reply 1 --author Codex --body 'Reply'
```
Use `uv run looking-glass` from this checkout if not installed globally. See `--help`, `agent instructions`, and `docs/AGENT_API.md` for remaining commands.

## Repo map
Keep this map and commands current when structure or workflows change.
- `looking_glass/app.py`: routes/security; `workspace.py`: files, SQLite, threads; `anchors.py`: anchor mapping; `revisions.py`: Git checkpoints.
- `looking_glass/cli.py`: server/agent commands; `projects.py`: project registry; `instructions.py`: agent guidance.
- `looking_glass/templates/`: HTML/HTMX; `frontend/app.js`, `frontend/style.css`: client sources; `looking_glass/static/`: committed output of `build.mjs`.
- `tests/`: backend/CLI/browser checks; `demo_dir/`: representative files; `docs/`: API, architecture, limitations, verification.
- `pyproject.toml`, `uv.lock`: Python packaging/dependencies; `package.json`, `package-lock.json`: frontend dependencies.
