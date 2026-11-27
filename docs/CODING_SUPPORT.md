# Coding support

## TODO and NOTE comments

Use the [Marker Tree](EXPLORER.md#marker-tree) to browse and jump to saved TODO and
NOTE comments. Previously imported discussions keep their flag, replies, and
original context and now follow ordinary discussion anchoring and resolution.

## Python indentation

In `.py` and `.pyi` files, Enter uses syntax-aware indentation for suites and
bracketed expressions. Tab and Shift+Tab use the same indentation unit. The
editor defaults to four spaces and follows an existing space or tab style when
it finds a multiline suite near the start of the file. Enter keeps the
indentation of an indented blank line and adds one level for an explicit
backslash continuation.

## Python definitions

In `.py` and `.pyi` files, Ctrl+click a name to go to its definition (Cmd+click
on macOS). Modifier hover underlines the identifier. A chooser handles multiple
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

An optional connection to an existing local VS Code session is specified in
[the VS Code bridge proposal](VSCODE_BRIDGE_SPEC.md). It proposes shared saved
files, quiet per-file locks while VS Code has an unsaved draft, and saved-Edit-only
provider requests. The bridge is not implemented; existing behavior above remains
the current fallback in both Edit and Review.

## Completion assessment and effort

These are engineering estimates for implementation, focused regressions and
browser validation, not time already spent:

| Option | Estimated effort | Behavior and cost |
| --- | --- | --- |
| Accept existing suggestions with Tab | 0.5–1 day | Recommended first step if desired. CodeMirror already suggests local names, builtins, keywords and snippets. Bind Tab only when a suggestion is active; retain indentation otherwise. No analysis requests or new runtime dependencies. Needs IME, snippets, keyboard focus and indentation checks in both browsers. |
| Import/type-aware suggestions with Jedi | 2–4 days | Reuse static inference, but add a persistent bounded worker, debounce, cancellation, stale-result protection, result cache and completion edits. Needed to avoid paying process startup on every request. Python runtime/configuration and unsaved imported modules need explicit scope decisions. |
| Broader VS Code-style Pyright/LSP support | 5–10 days | Better route if hover, diagnostics, signatures, rename and broader workspace completion are also wanted. Adds server lifecycle, incremental documents, project/interpreter settings, resource limits and more packaging/testing work. |

Lightweight local completion is already present: Ctrl+Space opens it and Enter
accepts. Tab acceptance and semantic completions remain unchanged pending a
product decision. No per-keystroke Jedi requests have been added.

Diagnostic measurements in the managed Linux environment (six fresh method
lookups on a small Python file): 723–791 ms, median 778 ms for the entire backend
request including process startup and static inference. This latency is reasonable
for an explicit definition command and unsuitable as a per-keystroke completion
implementation. Browser rendering is measured separately by real navigation,
layout and draft-preservation checks; these backend numbers exclude browser paint.

## Interfaces and verification

- `POST /api/python/definition`: `{path, content, line, column}` takes a one-based
  line and zero-based Unicode column. Returns `definitions` with workspace path,
  line, column, name and analyzed destination version. Existing local token and
  same-origin protections apply. Oversized buffers return 413, busy workers 429,
  timeouts 408 and analysis failures 422.

Coverage is in `test_python_navigation.py`,
`python-navigation.test.mjs` and `test_coding_support_browser.py`, alongside the
existing discussion, review, explorer, navigation and sidebar regressions. Browser
cases run in Chromium and Firefox in the hosted suite. Local Firefox installation
is blocked by the environment's denied browser-download domains; local browser
results use Chromium. The sentinel test verifies that importing a reference for
analysis does not execute project module bodies or project `sitecustomize.py`.

Multiline browser composition and clipboard text accept LF, CRLF, and CR input
while retaining the file's newline convention on save. Input normalization stays
within one editor transaction so undo, Review provenance, selection positions,
and Python definition line/column calculations use the same logical lines.
