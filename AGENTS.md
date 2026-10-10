# Looking Glass

## Purpose

A local editor and review tool for collaborating with separate AI coding agents on ordinary files: plans, prose, code, and generated reports. The core workflow is review → annotate a passage → agent reads and responds → revise → review again.

Persistent, passage-anchored discussions are the priority. Feedback, attachments, and original context must survive edits, restarts, and changes of agent session. Keep the application small, documented, and usable end to end.

## Product and data contracts

- Edit mode works on ordinary disk files. Review mode keeps a persistent proposal separate until explicit human approval of the active file. Retain authorship/history: green human additions, blue agent additions, red struck-through removals.
- Agents run separately through the local CLI (command-line interface) and API (application programming interface). Review edits use that interface rather than writing originals. Comments never automatically replace text; built-in model calls/orchestration remain outside current scope.
- Preserve drafts, undo history, selections, and per-tab state through navigation/mode changes. Reload clean external changes; preserve dirty work, offer comparison, and reject stale saves/approvals.
- Anchor conservatively. Deleted or ambiguous passages require reattachment; immutable reviewed context stays readable. Never silently attach feedback to unrelated text.
- SQLite stores discussions, review drafts, and metadata in `<workspace>/.looking-glass/`. Preserve existing data across upgrades; never commit workspace databases, attachments, or tokens.
- Saving and approval never commit. Git checkpoints are explicit, include only selected files, and preserve unrelated staged, unstaged, and untracked work.
- Serve on loopback. Sandbox interactive HTML reports away from application state/tokens; sanitize discussion rendering. Never execute project code on the server. Bundle application dependencies locally, without a CDN (content delivery network).

## Design and interaction

- Minimal, elegant, quiet: Notion-style prose editing, Obsidian-style live Markdown, familiar tabs/file explorer, and anchored right-sidebar discussions. Support light/dark themes and a compact Edit/Review toggle.
- Use bundled Newsreader prose and monospace code/JSON. Keep prose at a readable line width; allow wider tables with smaller readable text, compact cells, and horizontal scrolling.
- Use consistent purple passage highlights across code, Markdown, tables, and HTML. Highlight text without filling margins. Resolved discussions leave a subtle indication rather than an active fill.
- Keep reading stable: document-highlight clicks focus sidebar discussions without moving the passage. Explicit sidebar passage links, comment icons, and navigation may move the document. Returning from original context restores reading position and editor/report state.
- Polling, autosave, and focus changes must not flicker, replace unchanged content, clear selections, reorder cards, lose replies, or steal focus. Routine status feedback stays quiet; errors/conflicts stay clear.
- Sidebars resize and collapse to thin strips with restore controls in fixed positions. Preserve pane state. Support narrow windows and keyboard access; keep shortcuts discoverable. Ctrl+Z remains undo; Ctrl+Alt+Z is zen mode.
- Keep annotation/editing consistent across source, live Markdown, preview, tables, and rendered HTML. Search respects file/resolved scopes. Navigation preserves unsent work. Thread-card clicks retain normal copying, links, and embedded controls.

## Development practices

- Read relevant code, docs, and recent PR (pull request) context first. Current user instructions supersede earlier decisions.
- Prefer focused changes within Python/Flask, HTMX, SQLite, CodeMirror 6, Tailwind, and Three.js. Extract small modules where useful; justify dependencies or architectural changes.
- Use feature/bugfix branches and PRs unless instructed otherwise. Commit logical steps and push regularly when authorized so long work is recoverable. Preserve unrelated work.
- Rebuild and commit `looking_glass/static/` when frontend sources change. Use locked dependencies; preserve reproducible assets and complete Python distributions.
- Update documentation with behavior/interface changes. Report the problem, resulting behavior, actual validation, and limitations, including browser/version differences or unresolved failures. Keep this file concise; detailed specifications, verification, benchmarks, and deferred work belong in `docs/`, without transient task/branch status here.

## Testing and responsiveness

- Protect the whole app and interactions between features. Add regressions for fixed bugs and meaningful coverage for new behavior; test observable outcomes rather than mirroring implementation.
- Use fast Python/JavaScript tests for data, anchors, review, persistence, security, Git, and CLI contracts. Use real Chromium/Firefox journeys for selection, rendering, focus, scrolling, and editing. Inspect changed layouts in both themes and narrow panes.
- Exercise relevant transitions/races: external changes, concurrent edits/replies, tab/mode switches, context return, resolve/reopen, and restart persistence. Include repeated passages, Unicode, tables, and representative large documents/dense discussions.
- Keep fast checks separate from browser runs. Reuse browser processes with fresh contexts/disposable workspaces; shard the complete collection with its completeness guard. Improve speed without dropping coverage, weakening assertions, or masking failures with retries. Wait for observable readiness instead of arbitrary sleeps.
- Run relevant checks while iterating and appropriate full regression gates before merging. Documentation-only changes need content/path checks; runtime changes also need applicable build, packaging, and browser checks. Unit tests alone do not establish UI correctness.
- Measure server work, payload size, and browser rendering separately. Bound expensive reads/diffs, reuse shared anchor work, update only changed content, and keep unchanged polls cheap. Benchmark representative workloads without brittle timing assertions. A Rust port requires evidence of a remaining backend bottleneck.

## Commands

From the repository root: Python 3.10+, uv, Node 20+; Git for revision features.

```bash
uv sync --locked
npm ci
npm run build
uv run looking-glass serve ./demo_dir  # http://127.0.0.1:8765

npm test
uv run pytest -m 'not browser' -q
uv run playwright install chromium firefox
LOOKING_GLASS_BROWSER=installed uv run pytest -m browser -q
uv run python scripts/verify_browser_shards.py 4
uv build
git diff --check
```

After committing intended asset changes, rebuilding must leave `git diff --exit-code -- looking_glass/static` clean. See `docs/TESTING.md` for coverage and CI (continuous integration) sharding.

For a CLI available from any directory:

```bash
uv tool install --editable /absolute/path/to/Looking-Glass
looking-glass projects list
looking-glass agent --root /absolute/path/to/project list --status open
looking-glass agent --root /absolute/path/to/project read 1 --context-lines 10
```

With the server running, read thread/context before acting. Use `--body-file`/`--body-stdin` for safe multiline messages. See `agent instructions`, `--help`, `docs/AGENT_API.md`, and `docs/REVIEW_MODE.md` for replies, reattachment, and review edits.

## Repository map

Keep this map and commands current when structure/workflows change.

- `looking_glass/app.py`: routes/security; `workspace.py`: files/discussions; `anchors.py`: mapping; `reviews.py`: drafts/provenance/approval; `origins.py`: immutable context; `revisions.py`: Git checkpoints/history.
- `looking_glass/cli.py`, `projects.py`, `instructions.py`: agent interface/discovery/guidance; `attachments.py`: uploads.
- `looking_glass/templates/`: HTML/HTMX; `frontend/`: client sources; `looking_glass/static/`: committed `build.mjs` output.
- `tests/`: backend/CLI/JavaScript/browser checks; `.github/workflows/`: automated gates; `scripts/verify_browser_shards.py`: completeness; `scripts/benchmark_*`: disposable benchmarks.
- `demo_dir/`: fixtures; `docs/`: architecture, interfaces, testing, performance, verification, limitations; `pyproject.toml`, `uv.lock`, `package.json`, `package-lock.json`: packaging/dependencies.
