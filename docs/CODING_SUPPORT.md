# Coding support

## TODO and NOTE discussions

The discussion sidebar has two compact controls:

- **Track TODO / NOTE** opts the current file into automatic source-comment
  discussions. It saves dirty Edit text first, refuses stale file versions, and
  persists the preference in the workspace database. Press again to pause imports.
- **Markers only** limits the list, search and existing previous/next passage
  controls to flagged source threads. It composes with Across files, Show resolved
  and Only unattached. Explicit thread references can still inspect other threads.

Recognized tags are uppercase `TODO` and `NOTE`, with or without whitespace after
the comment prefix: `# TODO`, `#TODO`, `# NOTE`, `#NOTE`. Python uses its tokenizer,
so strings and docstrings do not create discussions. Markdown recognizes marker
lines beginning with hash, slash, star or HTML-comment prefixes. Other supported
sources recognize hash comments (shell, YAML, TOML, R, Ruby, Perl), slash and block
comments (JavaScript/TypeScript, C/C++, C#, Java, Go, Rust, CSS/SCSS, Swift, Kotlin,
PHP), HTML comments, SQL/Lua line comments, and SQL block comments. The generic scanner skips
quoted strings and JavaScript template literals; language-specific edge cases such
as regex literals, heredocs, raw strings and interpolated template expressions
are not a full compiler parse. Tags later in ordinary prose are not imported.

Each marker becomes an ordinary persistent discussion with a TODO/NOTE flag and
an initial **Source comment** message. Existing reply, resolve/reopen, original
context, passage highlighting, agent API, navigation and search behavior applies.
The quoted passage follows saved source; the initial message and immutable
original context retain what was imported. Manually resolved attached threads stay
resolved across later saves. Missing, removed or ambiguous markers auto-resolve
and retain their history for inspection with Show resolved. Ordinary manually
created discussions retain their existing resolution behavior. Reappearing markers
which cannot be conservatively mapped receive fresh threads rather than inheriting
an unrelated discussion.

Synchronization runs only for opted-in files when their saved text is reconciled
(open, changed-file polling, save, API/CLI discussion reads). Unchanged file polls
retain the existing fingerprint/304 path. Discovery does not scan the entire
workspace. Up to 1,000 markers in source order are tracked per file; the control
and status show when additional markers exceed this limit. Explorer moves retain
preferences and threads; deletion resolves their unattached markers. Pausing
imports preserves discussions and still resolves a marker when its anchor is lost.
Deleting a tracked thread may import it again on the next source change while
tracking remains enabled; resolve it to dismiss it persistently.

Tracking is enabled/paused from Edit mode. Existing threads follow Review anchors;
losing a marker anchor in a saved Review resolves it, as discussion resolution is
shared between modes. New markers in Review import only after approval writes
the source. No provisional Review text is written to disk by tracking.

## Python definitions

In `.py` and `.pyi` files use Ctrl+click, Cmd+click, F12, or the filename's ↗
button. Modifier hover underlines the identifier. A chooser handles multiple
definitions. Workspace functions, classes, methods, scoped variables, import
aliases and relative package imports use Jedi 0.19.2 static analysis. The current
buffer can be unsaved or in Review. Other modules use their saved disk contents.
An imported destination whose open draft differs from disk is refused with a
clear status; save it or switch to its disk version before navigating. Clean
Review destinations with the same text as disk are supported. File Back/Forward
preserves source drafts, undo and reading state.

Each request starts an isolated Python worker with a four-second deadline, a
512 KiB source-buffer limit, at most 20 definition candidates and one concurrent
analysis worker. On platforms with `resource.RLIMIT_AS`, the worker also has a
512 MiB address-space limit. Temporary parser caches are discarded after each
request. No worker or index runs while typing or polling. Jedi's unsafe extension
loading, automatic module imports and smart project path evaluation are disabled;
the project is parsed rather than imported or executed. Workers start with Python
isolated mode and the app's working directory, so project `sitecustomize.py` is
not loaded. Ordinary editor/server threads remain available while analysis runs.

Definitions open only inside the served workspace, subject to existing metadata
and symlink restrictions. External library/builtin definitions, runtime-generated
attributes/imports and arbitrary project interpreter configurations are outside
this implementation. Incomplete Python is supported where static inference can
still identify the symbol. Missing names and timed-out analysis leave the reading
position intact. Late results are discarded after edits, tab/mode changes or newer
lookups; destination versions are checked before selecting a line. Unicode and
CRLF positions convert between Python code points and CodeMirror UTF-16 offsets.

Jedi adds one direct Python dependency plus Parso, both locked in `uv.lock`.
CodeMirror's existing Python parser remains responsible for highlighting, outline
and local completion. A full Pyright/LSP integration would add a language-server
process, document synchronization and an interpreter/project configuration UI;
that ongoing cost is not needed for this definition-only feature.

An optional [private VS Code companion](../vs_code_extension/README.md) now
implements shared saved files, quiet per-file dirty-buffer locks and saved-Edit-only
provider requests. Existing behavior above remains the fallback for unsaved Edit
buffers and all Review proposals. See the companion README for installation,
actual cloud validation and pending desktop/provider coverage; the
[target bridge contract](VSCODE_BRIDGE_SPEC.md) records its constraints.

## Completion assessment and effort

These are engineering estimates for implementation, focused regressions and
browser validation, not time already spent:

| Option | Estimated effort | Behavior and cost |
| --- | --- | --- |
| Accept existing suggestions with Tab | 0.5–1 day | Recommended first step if desired. CodeMirror already suggests local names, builtins, keywords and snippets. Bind Tab only when a suggestion is active; retain indentation otherwise. No analysis requests or new runtime dependencies. Needs IME, snippets, keyboard focus and indentation checks in both browsers. |
| Import/type-aware suggestions with Jedi | 2–4 days | Reuse static inference, but add a persistent bounded worker, debounce, cancellation, stale-result protection, result cache and completion edits. Needed to avoid paying process startup on every request. Python runtime/configuration and unsaved imported modules need explicit scope decisions. |
| Broader VS Code-style Pyright/LSP support | 5–10 days | Better route if hover, diagnostics, signatures, rename and broader workspace completion are also wanted. Adds server lifecycle, incremental documents, project/interpreter settings, resource limits and more packaging/testing work. |

The completed marker tracking and definition navigation represent roughly 3–5
engineering days including integration, persistence/race tests and browser checks.
Lightweight local completion is already present: Ctrl+Space opens it and Enter
accepts. Tab acceptance and semantic completions remain unchanged pending a
product decision. No per-keystroke Jedi requests have been added.

Diagnostic measurements in the managed Linux environment (six fresh method
lookups on a small Python file): 723–791 ms, median 778 ms for the entire backend
request including process startup and static inference. Importing 1,000 Markdown
markers took 18 ms; an unchanged read took 1 ms. These are observations, not timing
assertions or representative large-project guarantees. This latency is reasonable
for an explicit definition command and unsuitable as a per-keystroke completion
implementation. Browser rendering is measured separately by real navigation,
layout and draft-preservation checks; these backend numbers exclude browser paint.

## Interfaces and verification

- `POST /api/source-markers`: `{path, enabled, version}` uses the saved file hash.
  Returns `{enabled, truncated}`. File reads expose `track_source_markers` and
  `source_markers_truncated`; saves return the latter. Threads and lean navigation/
  search indexes expose nullable `source_marker` (`TODO` or `NOTE`).
- `POST /api/python/definition`: `{path, content, line, column}` takes a one-based
  line and zero-based Unicode column. Returns `definitions` with workspace path,
  line, column, name and analyzed destination version. Existing local token and
  same-origin protections apply. Oversized buffers return 413, busy workers 429,
  timeouts 408 and analysis failures 422.

Coverage is in `test_source_markers.py`, `test_python_navigation.py`,
`python-navigation.test.mjs` and `test_coding_support_browser.py`, alongside the
existing discussion, review, explorer, navigation and sidebar regressions. Browser
cases run in Chromium and Firefox in the hosted suite. Local Firefox installation
is blocked by the environment's denied browser-download domains; local browser
results use Chromium. The sentinel test verifies that importing a reference for
analysis does not execute project module bodies or project `sitecustomize.py`.
