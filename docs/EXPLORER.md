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
its source line. The **−** and **+** controls collapse or expand all nested outline
elements. Each file's fold choices persist across navigation and reloads.

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
