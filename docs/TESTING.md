# Regression suite

The suite protects the whole application. New features add checks alongside the
existing ones; browser sharding changes where tests run, never which cases run.

| Behavior | Main coverage |
| --- | --- |
| Edit/save, undo/redo, find/replace, tabs, external changes and conflict recovery | `test_browser.py`, `test_workspace.py`, `test_app_integration_browser.py` |
| Non-destructive review, human/agent provenance, removed text, autosave, approval and concurrent edits | `test_reviews.py`, `review-model.test.mjs`, `test_review_mode_browser.py` |
| Passage anchors, reattachment, immutable context and restart persistence | `test_anchors.py`, `test_origins.py`, `test_context_return_browser.py`, `test_cli.py` |
| Comments, replies, editing/deletion, attachments, resolution/reopening and quiet polling | `test_discussion_workflow.py`, `test_requested_features.py`, `test_app_integration.py` |
| Fuzzy thread search, ranking, thread numbers, file/resolved scopes and draft passages | `thread-search.test.mjs`, `test_thread_search_browser.py` |
| Live/source/preview Markdown, numbered lists/tasks, wide tables, syntax highlighting and local Mermaid | `test_markdown_discussions.py`, `test_requested_features.py`, `test_navigation_browser.py`, `test_context_return_browser.py` |
| HTML source mapping, runtime anchors, report interactions and iframe isolation | `html-source.test.mjs`, `test_html_annotations.py`, `test_html_annotations_browser.py`, `test_browser.py` |
| Stable Edit/review controls, confirmation/cancellation and revision races, JSON/HTML exclusion, quiet autosave, dense-highlight DOM stability, selectable thread cards and passage navigation | `test_interaction_polish_browser.py` |
| Spotlight, unchanged reading positions, sidebar geometry, zen mode and navigation | `test_discussion_reading_browser.py`, `test_spotlight_navigation_browser.py`, `test_navigation_browser.py` |
| Repeated spotlight arrows, unavailable anchors, explicit original context, stable reading surfaces, thin themed reading scrollbars and native scrolling | `test_spotlight_regressions_browser.py` |
| Native oversized downloads without browser buffering, expiring file-scoped download URLs, document top/copy controls, stable spotlight search, sidebar arrow focus, scoped queues and zen resolve/delete advancement | `test_file_downloads.py`, `test_reading_controls_browser.py`, `test_spotlight_controls_browser.py`, `app-state.test.mjs` |
| Monospace line numbers through editing and narrow layouts, uniform rounded fenced code, quiet multiline blockquotes in both themes | `test_reading_pane_polish_browser.py` |
| Recent-file Back/Forward, history dropdown/clear, rapid and failed navigation, saved visits, preserved drafts/scroll, Python outline parsing/jumps/live edits/review and layouts | `file-history.test.mjs`, `python-outline.test.mjs`, `test_file_navigation_outline_browser.py` |
| Git graph/branches, durable commit/branch discussions and selected checkpoints preserving the index | `history.test.mjs`, `test_history.py`, `test_history_browser.py`, `test_git_discussions.py`, `test_revisions.py` |
| JSON/JSONL folding, formatting/search/navigation/download, images, STL and software fallback | `json-format.test.mjs`, `test_requested_features.py`, `test_navigation_browser.py`, `test_browser.py` |
| Local agent CLI, project discovery, token/origin checks and bounded reads/work | `test_cli.py`, `test_reviews.py`, `test_workspace.py`, `test_anchors.py`, `test_discussion_workflow.py` |
| Pure application transitions, awaited navigation, stale completions, independent mode undo and unchanged node/cursor identity | `app-state.test.mjs`, `navigation.test.mjs`, `passages.test.mjs`, `review-sync.test.mjs`, `discussion-lifetime.test.mjs`, `test_architecture_browser.py` |
| Shared Python/JavaScript Unicode/CRLF review operations | `tests/fixtures/review-operations.json`, `test_review_operations_shared.py`, `review-model.test.mjs` |
| Cross-feature approval, discussion origins/attachments, stale writes, other file drafts and Git staging | `test_app_integration.py`, `test_app_integration_browser.py` |

Fast feedback (no browser installation needed):

```bash
uv sync --locked
npm ci
npm test
uv run pytest -m 'not browser' -q
```

The complete browser run remains available locally:

```bash
uv run playwright install chromium firefox
LOOKING_GLASS_BROWSER=installed uv run pytest -m browser -q --durations=10
```

Automatic CI runs only fast checks on PR updates and pushes to `main`, avoiding
duplicate push/PR runs for feature branches. Run relevant tests during iteration;
start the full browser collection after the final code push, rather than at each
intermediate push.

To start the final browser run, add the **run-browser-tests** label to the PR,
or use **Actions → Regression tests → Run workflow** and select the branch.
With GitHub CLI, the manual equivalent is:

```bash
gh workflow run tests.yml --ref <branch>
```

Only adding the label triggers browsers; leaving it present does not rerun them
on subsequent pushes. To request another run after changes, remove and re-add
the label. Fast checks and browsers have separate concurrency groups, so a new
fast-check run does not cancel an explicitly requested browser run.

After starting a remote run, confirm that it is queued/running, record its URL
and tested commit, and hand it back to the user without waiting or polling.
Ask the user to return in about 5–10 minutes. On return, inspect that run's jobs
and compare its tested commit to the latest PR head; an older run does not
validate newer edits.

The full browser run uses the same collection in four jobs, with zero-based `--browser-shard=0/4`
through `--browser-shard=3/4`. Each job includes Chromium and Firefox cases. Cases
are sorted by their full pytest IDs and distributed round-robin, so added tests
automatically enter a shard. `uv run python scripts/verify_browser_shards.py 4`
checks that their union is the full collection, with no duplicates. Failure of
one shard does not cancel the other jobs; failures are not automatically retried.

Browser processes and the Playwright driver are reused within each job. Every
test still receives a fresh browser context, viewport, page, disposable workspace,
app/server and isolated project registry. Cookies, local/session storage,
permissions, routes and event listeners belong to the context and are discarded
even when a test fails. The software-rendering end-to-end test retains its
separate launch arguments. Real polling/selection checks and their deadlines are
unchanged. Test servers use a shorter idle polling interval so shutdown doesn't
wait up to half a second per case; application polling is unchanged.

Reading-position checks finish preceding navigation and wait for stable editor
geometry/fonts before recording their baseline. HTML alignment uses instant
scrolling to stop an earlier sidebar animation. The preservation assertions and
deadlines remain unchanged; separate cases also exercise reports that request
smooth scrolling during a highlight click and verify normal wheel navigation.
JSONL comparison checks sample frames starting at the row click and again after
restoration, so neither a transient reset nor a late editor-anchor jump can pass.
Row changes restore inside CodeMirror's layout cycle before it captures the new
scroll anchor; shorter entries clamp naturally and ordinary wheel scrolling stays
available.

Production assets must rebuild without differences after the intended asset
changes are committed. CI also builds wheel/source distributions. See
`VERIFICATION.md` for measured results and environment details; timing is
diagnostic rather than a brittle per-test assertion.
