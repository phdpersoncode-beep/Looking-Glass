# Files, outline, and discussion references

## Marker Tree

Open **Marker Tree** above **File Tree** in the left sidebar. Marker Tree starts
collapsed, and File Tree starts expanded. Expand a folder or file to see its
marker count and matching comments. Select a marker to open its file at the tag.
Markdown reading preview switches to source for the jump. A saved marker can
still be located in an open draft if its line survives exactly once.

Use the filter icon to match tag, text, or relative path. The tag
control groups results by P0 through P3, TODO, and NOTE, keeping the folder
hierarchy within each group. The stacked panels expand or collapse all branches.
The refresh icon rescans saved files. Hover each control for its name.

The tree reads saved Markdown, supported source code, and Jupyter notebooks
(`.ipynb`). It accepts hashes with or without spaces, optional colons, Markdown
list markers, bare TODO at the start of a Markdown line, and HTML comments.
Source comments use the delimiters for their language. Supported source extensions
include Python, shell, JavaScript and TypeScript, C and C++, Java, Kotlin, Go, Rust,
HTML and CSS, SQL, Ruby, R, Perl, Lua, Swift, C#, and PHP. Plain text and data or
configuration formats such as JSON and YAML are skipped.

Notebook results come from Markdown cells and supported code cells. Tooltips show
the cell and source line. Selecting a notebook result or opening a notebook from
the File Tree offers **Copy file path** for use in a notebook editor. Outputs,
metadata, and raw cells are skipped.

The Marker Tree includes untracked files and projects without Git. To turn saved
TODO and NOTE comments into persistent discussions, use **Track TODO / NOTE**
in the discussion sidebar.

The first scan starts on expansion. While visible, the tree refreshes after
file operations and on the explorer's 12-second interval. It reuses workspace
discovery, including `.looking.ignore` and built-in exclusions. An in-memory
cache uses filesystem metadata to skip reading or parsing unchanged files.
Only marker excerpts and locations are retained. Limits are 10,000 discovered
files, 8 MiB per text file, 1,000 matches per file, and 5,000 displayed matches
per workspace. The section reports when discovery or results hit a count limit.
Git's staging index describes staged paths and contents. Scanning the working
tree keeps unstaged and untracked markers visible.

## Breadcrumb picker

For an open workspace file, click its name above the reading pane to see files
and folders in the same directory. Click a folder segment to see its siblings.
Choose a folder in the picker to browse inside it, or use the up arrow to return
to its parent. Type to filter the current folder. Use ↑/↓ to move through results,
Enter to choose, or Escape to close and return to the breadcrumb.

Opening a neighbor uses ordinary tabs and file history, so returning to an
edited file restores its unsaved work. The picker follows `.looking.ignore` and
the File Tree's hidden metadata and symlink rules. It reads only the selected
directory when opened. Files explicitly opened outside the workspace retain an
absolute path and the path-copy control.

## File Tree

The left explorer supports files and empty folders, with the same workspace-root
`.looking.ignore` rules as Quick Open. Folder expansion is remembered per
workspace. **Alt+Q** collapses every folder and clears an active explorer filter,
including while editing or reading a sandboxed HTML report. The existing expand
and collapse symbols remain available in the explorer header.

**New file** and **New folder** are available in the header and right-click menu,
including in an empty workspace. Select a folder (or a file in it) to choose the
header actions' destination. Right-click a folder to create inside it, or empty
tree space to create at the root. Enter a single name in the themed dialog;
Enter creates it, and Escape/Cancel leaves disk unchanged. Creation expands the
destination folders and clears the explorer filter; new files open as empty disk
files while existing tabs keep their drafts and undo history. Collisions, protected
paths, symlinks, and paths with older review history are rejected with an error
that keeps the entered name for correction.

The explorer shows a warning when more than 10,000 discoverable files exist.
Add generated or unused paths to the workspace-root `.looking.ignore`, then
refresh. Ignored paths do not consume the cap. Exactly 10,000 files is a complete
listing and does not warn; truncation changes invalidate the tree's ETag even if
the displayed file names stay the same. `GET /api/workspace` retains `files` and
adds `files_truncated` and `file_limit`. `POST /api/explorer/create` accepts
`{"path":"src/new.py","kind":"file"}` (or `"kind":"folder"`), requires an
existing parent, and returns the normalized `path` and `directory` with status 201.

Right-click a file or folder to open a small theme-matched menu at the cursor:
**Rename**, **Delete**, **Copy relative path**, and **Copy absolute path**.
Rename and deletion use Looking Glass dialogs. Escape dismisses the menu;
Up/Down and Enter select its actions. Clipboard writes require the browser's
normal clipboard permission.

Drag a file or folder onto a folder to move it there. Hover over a closed folder
to expand it. Drop onto a file to use its containing folder, or onto empty space
at the root of the tree to move back to the workspace root. Moves preserve open
text drafts, undo history, discussions, review drafts, PDF bookmarks, and managed
image registrations. Saves and navigation wait for an in-progress move. Name
collisions, stale source versions, moving a folder inside itself, symlinks, and
protected metadata/dependency directories are rejected. A destination with older
review history is also rejected rather than mixing discussions from different
files. Operations are limited to 10,000 entries and to this workspace.

Deletion refuses open unsaved drafts and moves saved files into
`.looking-glass/trash/<id>/files/`, beside a `restore.json` manifest recording
the original relative path. Discussions, immutable original context, and review
history remain available; deleted-file discussions require reattachment. There is
no trash browser yet: to restore, move the saved file/folder back to the manifest's
path using your filesystem tools. Rename and move do not rewrite authored links,
imports, or earlier discussion text. Changes stay ordinary uncommitted disk edits.

For a Python file, open **Python outline** on the right. A small chevron beside a
class or function folds its nested definitions; clicking the name still jumps to
its source line. The small stacked-panel minus/plus icons match the sidebar controls and collapse
or expand all nested outline elements. Each file's fold choices persist across navigation and reloads.
Wheel or trackpad scrolling moves through long outlines. The thin scrollbar
shows your position.

In a new comment, reply, or comment edit, type **@** followed by part of a file
path. The fuzzy picker uses the same scoring as Quick Open and refreshes its
workspace list for each search, respecting `.looking.ignore`. Use Up/Down and
Enter or click a result; Escape dismisses suggestions while retaining the comment.
Ctrl/Cmd+Enter still submits the comment. Paths with spaces are inserted as
`@"notes/design sketch.md"`; ordinary paths look like `@src/part.py`.

These references remain plain text in the CLI/API. An agent can include the same
syntax in any message; the browser renders it as a quiet clickable file link,
matching thread references. Code spans, code blocks, existing links, and email
addresses retain their usual meaning. Ignore rules filter suggestions, not
explicit references or already-open paths. References point at the current
workspace path and are not automatically rewritten after later moves.

Selecting a word in the editor marks its other occurrences in amber, with
contrasting text and a thin underline in both themes. These occurrence marks
are distinct from purple discussion highlights and green/blue/red review changes.

The explorer colors Git-ignored names gray, modified names orange, and new files
green, including staged additions. Changed visible descendants also color their parent
folders. Refresh files (or wait for the normal tree refresh) to update these
colors after saves, staging, commits, or ignore-rule edits. `.gitignore` affects
coloring; `.looking.ignore` still controls which paths are discovered. Built-in
metadata/dependency exclusions remain hidden. Git colors are optional decoration;
a workspace without Git still has its ordinary explorer.

The Python outline has a draggable left edge. Its width is remembered per
workspace, including after a reload, and is clamped to fit narrow panes. Focus
the divider and use Left/Right or Home/End to resize with the keyboard;
double-click resets the width. Escape during a drag cancels that resize.

Selected-text matches also appear as amber ticks beside the editor's vertical
scrollbar. Click a tick to select and scroll to that match. Markers cover the
whole document, including offscreen matches, and clear when the selection is
collapsed. Dense occurrences share a marker within each line band to keep the
overview responsive (at most 250 bands). Editor modes use their current draft;
changing files or modes creates the appropriate overview for that surface.

Use **Alt+←** and **Alt+→** to move back and forward through file visits.
**Ctrl+P** opens the fuzzy file picker with the most recent file visits first,
using the history dropdown's order with duplicate paths removed. Other workspace
files follow alphabetically. Type to filter; Up/Down choose a result and Enter
opens it. Recently visited paths and open tabs remain available even when they
are outside workspace discovery, as with the history dropdown. Normal text input,
including uppercase P, is unchanged.
