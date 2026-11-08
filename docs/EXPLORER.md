# Files, outline, and discussion references

The left explorer supports files and empty folders, with the same workspace-root
`.looking.ignore` rules as Quick Open. Folder expansion is remembered per
workspace. **Alt+Q** collapses every folder and clears an active explorer filter,
including while editing or reading a sandboxed HTML report. The existing expand
and collapse symbols remain available in the explorer header.

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

**Ctrl+P** opens the fuzzy file picker with the most recent file visits first,
using the history dropdown's order with duplicate paths removed. Other workspace
files follow alphabetically. Reopening the picker while an earlier file visit is
finishing keeps the new picker open and focused. Type to filter; Up/Down choose a
result and Enter opens it. Recently visited paths and open tabs remain available even when they
are outside workspace discovery, as with the history dropdown. Normal text input,
including uppercase P, is unchanged.
