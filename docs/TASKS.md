# Shared Tasks board

Open **Tasks** beside **Commit history**. It opens a normal tab that can be pinned,
closed, and restored after a browser refresh. The board belongs to the open
workspace, including when agents use the CLI from another directory.

The four columns are **◌ Backlog**, **◐ In progress**, **◎ To review**, and **✓ Done**.
Drag a card onto another card to insert before it, or onto a column to append.
While dragging, a preview gap shows where the card will land and nearby cards
slide into the proposed positions. The board order is saved on drop. With
reduced motion enabled, the preview gap updates immediately.
Use the archive icon in **Done** to archive the tasks shown in that column.
**Show archive** switches the board to archived tasks. The sidebar keeps
archived tasks in their original hierarchy, where you can open and restore them.
Click a card (or press Enter while focused) to open its centered detail popup.
The card's name is its heading: edit it directly in place, then Save with the
other fields. There is no separate Title box. Milestones keep their M-number
prefix beside the editable name; #C identity remains underneath. Compact status
and milestone dropdowns sit side by side directly below the heading, above the
description. Status symbols match the board columns (◌, ◐, ◎, ✓); ◇ marks milestone
assignment. Changing status in the editor is the keyboard alternative
to dragging. All titles and descriptions are treated as plain text.

The upper-right toolbar beside × uses line icons for Save, discard edits (Cancel),
promotion/demotion, archive/restore, and delete. Each has a hover tooltip and
accessible name. Save commits all fields, including the heading; Delete keeps its
confirmation step. Actions stay available while scrolling the popup.

Milestones appear in the right sidebar with a purple left bar. The board shows
their tasks and each task's milestone label.
Every card keeps a permanent reference such as **#C01**, including while promoted.
Milestone titles display **M1: My awesome card** (without changing the stored title).
Reorder milestones in the right sidebar to change their numbers. The new order
reuses the existing active milestone numbers, including gaps. Archived milestones
keep their reserved numbers. New promotions take the
lowest unused number. Demotion restores the original #C identity and remembers
the previous milestone number; re-promotion reuses it when free, otherwise assigns
an unused number. The milestone editor also shows its permanent #C identity.
Existing boards retain the numbers displayed before this upgrade.

Use **Filter by milestone** to show its tasks on the board. Select the same
milestone again or choose **All milestones** to clear the filter. Hover a
truncated name to see its full text. Search `#M1` or `M1` to find assigned
tasks, or `#C01` / `C01` to find a task by its permanent ID. Stable #C numbers
survive restarts and remain the references stored in activity history.
Assignments and edit headings follow milestone renumbering without changing the
underlying relationships or clearing unsent fields.

Use **Add milestone** in the sidebar header to insert a milestone at the current
row position. A cursor inside a branch inserts after that milestone and its
tasks. Use **◇** on a board card to promote an existing task. Milestones keep
their own status, description, and a completion count for their active
descendants. Every card has a nested **Tasks** list;
each subitem is itself a full card with a permanent ID, status, and conversation.
Click the row or its **#Cxx** reference to open its detail popup. Parent
field drafts remain available when following these links or returning to the board.
Check a child to finish it; unchecking returns it to backlog. Completion never
automatically changes a parent's status. Milestones cannot be nested; task
hierarchies support up to 32 levels and inherit the top milestone's assignment.

## Task outline and keyboard editing

In the Tasks tab, the right discussion sidebar becomes a hierarchical task list.
It uses the same resize and minimize controls; returning to a file restores the
discussion controls. Milestones appear first, in ascending number order, followed
by unassigned tasks. Drag milestone rows or use Alt+Up/Down to reorder them with
their branches. Other siblings have their own saved outline order. The sidebar
shows active and archived tasks regardless of the board filters. Its status
controls use the same symbols as the board columns.

Double-click a row to edit its name in place. Click within the field to position
the caret while editing. Enter saves and moves to the next row; Up/Down
move through names. Names also save on blur. Escape discards that inline draft.
Tab nests a task under its previous sibling; Shift+Tab lifts it after its parent.
When that move is unavailable, Tab or Shift+Tab moves keyboard focus normally.
Alt+Up/Down reorders siblings. Shift+Enter creates a sibling and Ctrl/Cmd+Enter
creates a subitem; **+ Add task/subitem** is the pointer equivalent. Inline drafts
and caret survive unrelated polling;
stale names require explicit review before overwriting the latest saved title.

Both the plan sidebar and each card's **Tasks** list have compact **Collapse all
tasks** and **Expand all tasks** buttons in their heading. Use the triangle on
a row to fold or unfold its own branch. Collapse all shows the current list's
top-level items; Expand all reveals every descendant. Each card and the plan
keep independent display state for the tab
session. Folding never changes task data, order, selection, or drafts, and polling
does not expand collapsed lists when agents add children. A blank left gutter
remains available for dragging rows.

The popup leaves the board visible through a dimmed backdrop. Clicking that
backdrop, pressing Escape, or choosing **Close card** exits focus mode and keeps
unsaved field/comment drafts for reopening; **Cancel** discards field changes.
Saving sends only the fields you edited. If another writer changed the board,
review and acknowledge the latest revision before retrying your field edits.

Type `@` in a card description or comment to find a workspace file. Description
references appear under **Related files**, and references in posted comments
open from the conversation. For a path with spaces, use `@"research notes.md"`.
Open a reference to read or discuss the document in its normal tab. The return
button beside the document name reopens the same card with its description and
comment drafts intact.
Clicking inside the card or dragging a text selection outside it does not dismiss
the popup. Keyboard focus stays inside while open and returns to the originating
card/control on close, including after background polling replaces board cards.
Long contents scroll inside the popup without moving the board.
The compact action buttons stay in their own row above the scrolling title and
card contents.

Sizing follows the bounded-window pattern shown in [Trello's card-back documentation](https://support.atlassian.com/trello/docs/new-card-back/).
That documentation does not publish a fixed viewport ratio, and [Trello's resize request](https://jira.atlassian.com/browse/TRELLO-1369)
does not define dimensions. Looking Glass therefore uses an explicit local design
choice: a 768px maximum width, at least 24px side and 32px top/bottom margins on
desktop. At widths up to 600px, margins shrink to 12px on all sides. The window
centers horizontally and vertically; height fits content up to that available space.
For example, at 1600px wide it occupies 48% of the screen, and at 1100px about 70%.
These are Looking Glass dimensions, not a claim about Trello's current CSS.

Drag rows vertically to reorder siblings. Drag a row right to nest under a target,
or left to lift a level; dragging a row horizontally on itself uses the previous
sibling for indentation. In the sidebar and card checklists, nearby rows slide
aside to preview the insertion point. The gap is indented to show the proposed
nesting level when it is visible in the current list.
Dropping onto a milestone assigns the task and its subtree to that milestone.
All card checklists use the same editable, draggable rows and saved hierarchy.
Ctrl/Cmd+click selects multiple rows and shares selection with Kanban cards;
right-click exposes assign/unassign, archive, restore, delete, and clear actions.
Selected descendants travel once with a selected ancestor. Archived cards must be
restored before dragging.

Search matches a case-insensitive character subsequence across title and
description. The milestone filter shows the milestone and its children. Search,
filter, and archive scope combine. Ctrl+click (Cmd+click on macOS), or Space on a
focused card, toggles selection. Selected cards expose assign/unassign, archive,
restore, delete, and clear actions. Delete asks for confirmation; archive is
reversible through **Show archive**. Deleting a card lifts surviving children to
its nearest surviving parent. Deleting or demoting a milestone keeps its tasks,
lifts direct children to the root, and unassigns the subtree. Archiving a milestone preserves its task relationships;
its tasks remain visible and the archived milestone is unavailable for new assignments.

Moving a task into Done produces a brief confetti burst and a soft synthesized
ding. Reduced-motion preferences suppress confetti. **Mute** persists in this
browser. Browser audio policy may suppress sound until audio is permitted. Polling
agent changes never plays completion effects. No audio files or external assets
are downloaded.

## Comments and activity

Each task and milestone edit view has **Comments & activity** below its fields
(and below the child checklist for milestones). People and agents share one
chronological conversation. Comments use compact rows with the author and time
above the message. Long messages wrap in full, and hovering over the timestamp
shows the full date and time. Automatic updates have an **Update** label and a
thin grey row with smaller text. Title,
description, status, parent/assignment, promotion/demotion, archive/restore, and drag order
changes record their actual before/after values in the same transaction as the edit.
Milestones also record child assignment/unassignment. Description differences expand
on demand. Saving unchanged fields does not create an update or reorder the card.

Write in the resizable comment box and click **Comment** beside it (Ctrl/Cmd+Enter
also submits). A trash icon
on each entry immediately deletes that comment or update. Deletion is permanent
and does not revert the card change. This is a collaborative activity log that can
be cleaned up, not an immutable audit trail. Deleting a card removes its timeline;
archiving keeps it. Existing cards retain their IDs and gain activity from this
version onward; past changes cannot be reconstructed.

Polling updates the open timeline without clearing unsent comments, replacing
unchanged entries, or resetting card edit fields. Comment drafts remain available
when reopening a card in the same tab session. Comments are plain text, including
literal HTML. The browser initially loads the latest 100 entries and can load up to
1,000; the CLI/API can page further back with `before`. Unchanged activity polls
return 304. Comments and activity deletion do not require a board revision; they
never overwrite card fields. Concurrent card changes still require review before
saving the editor.

## Agent CLI

The local server must be running. Commands return JSON. `--root` and optional
`--url` go before the operation, as with the existing agent interface.

```bash
looking-glass tasks --root /path/to/project list
looking-glass tasks --root /path/to/project list --archived
looking-glass tasks --root /path/to/project list --status in_progress --milestone-id 1 --query 'brd'
looking-glass tasks --root /path/to/project read 1
looking-glass tasks --root /path/to/project create 'Ship shared planning' --status backlog
looking-glass tasks --root /path/to/project update 1 --revision 1 --milestone
looking-glass tasks --root /path/to/project create 'Build board UI'
looking-glass tasks --root /path/to/project create 'Keyboard flow' --parent-id C02
looking-glass tasks --root /path/to/project outline-move C03 --revision N --parent-id C02 --before C04
looking-glass tasks --root /path/to/project update C03 --revision N --parent-id 0
looking-glass tasks --root /path/to/project update 2 --revision 3 --milestone-id 1
looking-glass tasks --root /path/to/project update 2 --revision 4 --description-file plan.md
looking-glass tasks --root /path/to/project move 2 --revision 5 --status in_progress
looking-glass tasks --root /path/to/project move 2 --revision 6 --status done --before 3
looking-glass tasks --root /path/to/project update 2 3 --revision 7 --archived
looking-glass tasks --root /path/to/project update 2 3 --revision 8 --no-archived
looking-glass tasks --root /path/to/project delete 2 3 --revision 9
```

Use the actual IDs and revision from the previous response; examples are illustrative.
Use `tasks list --query M1` to look up a current milestone number. CLI read/write
arguments use the permanent #C reference or numeric card ID so renumbering cannot
redirect an agent edit.

Card arguments also accept quoted references such as `'#C01'` or `C01`.
Use quotes with `#` to prevent shell comment syntax. New conversation commands:

```bash
looking-glass tasks --root /path/to/project activity C01 --limit 100
looking-glass tasks --root /path/to/project activity C01 --before 50
looking-glass tasks --root /path/to/project comment C01 --author Agent --body-file reply.md
looking-glass tasks --root /path/to/project comment C01 --author Agent --body-stdin
looking-glass tasks --root /path/to/project delete-activity C01 42
```

`read` returns the card and its entire subtree; `activity` returns conversation entries separately.
Card mutations also accept `--author` (default: Agent) to identify updates.
Use `--milestone` to promote a task and assign an available milestone number.

`--milestone-id 0` unassigns to the root; `--no-milestone` demotes.
`create --parent-id C02` adds a checklist subitem. `update --parent-id C02` reparents
a subtree; `--parent-id 0` lifts it to the root. Do not combine `--parent-id` and
`--milestone-id`. `outline-move` accepts multiple IDs, a parent (default: root), and
an optional `--before` sibling; it changes hierarchy/order without changing status.
`--description-file -`
reads stdin. Multi-card `update` and `delete` are atomic. `move` takes one card;
use `update ... --status` to move several cards to the end of a column.

Every mutation requires the current board revision. The CLI supplies the just-read
revision for create; update/move/delete require `--revision`. Conflicts return HTTP
409: reread and reconsider instead of blindly retrying. The browser keeps an open
edit intact, presents the latest saved card for review, and requires explicit
acknowledgement before saving over the refreshed revision. An unrelated card change
also conflicts: this deliberately conservative first version uses board-wide revisioning.

## HTTP API and persistence

`GET /api/tasks` returns `{revision, cards}` including archived cards. `GET /api/tasks?revision=N` returns 304 without reading cards when unchanged. `POST /api/tasks`
accepts one of these JSON objects with the same local API token and origin protections
as other agent routes:

```json
{"action":"create","revision":0,"title":"Plan","status":"backlog"}
{"action":"update","revision":1,"ids":[1],"changes":{"milestone":true}}
{"action":"move","revision":2,"id":1,"status":"in_progress","before":null}
{"action":"delete","revision":3,"ids":[1]}
{"action":"create","revision":4,"title":"Subitem","parent_id":2}
{"action":"outline_move","revision":5,"ids":[3],"parent_id":2,"before":null}
```

`GET /api/tasks/1/activity?limit=100&before=42` returns `{revision, entries,
has_older}`. Omit `before` for the newest page; pass `revision=N` for conditional
polls. Limits are 1–1,000. Entry fields include `id`, `card_id`, `kind` (`comment`
or `update`), `author`, `body`, structured `changes`, and UTC `created_at`.

Additional `POST /api/tasks` actions:

```json
{"action":"comment","id":1,"author":"Agent","body":"Ready for review."}
{"action":"delete_activity","id":1,"entry_id":42}
```

Deletion checks both the card and entry IDs. Card snapshots also contain a
`reference` (the displayed #M or #C label), `card_reference` (permanent #C ID),
`milestone_reference` (#M label or null), `parent_id` (immediate card parent or null),
and `outline_position` (sibling ordering key). `milestone_id` is derived from the
hierarchy and identifies the root milestone for every descendant. HTTP action IDs remain integers. `author` is optional
for mutations (defaults to User for HTTP; the browser uses its saved author).

Statuses are `backlog`, `in_progress`, `to_review`, `done`. Editable fields are
`title`, `description`, `status`, `milestone` (boolean), `milestone_id` (integer or
null; reassigns the subtree directly under that milestone), `parent_id` (integer
or null), and `archived` (boolean). Move's optional `before` identifies an active card
in the destination column. The sidebar sends `milestone_move` with the moved
milestone's `id` and an active milestone `before`, or null to move it to the end.
Creating a milestone uses `create` with `milestone: true` and the same `before`.
The Done archive action uses `archive_done` with the `ids` shown in the column.
Responses return the complete updated board.

Cards and ordering persist in the existing `.looking-glass/state.sqlite3`; ordinary
SQL dump/restore includes them. Existing databases gain additive tables without
changing discussions or review data. UI polling refreshes only on a changed revision;
this first version loads the whole board, suitable for project planning rather than
an unbounded issue tracker. No new dependencies, agent execution, GitHub issue sync,
or automatic Git commits are introduced.

## Design assumptions

- One board per workspace, shared by people and independent agents.
- Milestones are promoted root cards. Tasks and checklist subitems are full cards,
  with one immediate parent and one inherited milestone; cycles are rejected atomically.
- Milestones follow numeric order. Task sibling order is saved independently of columns.
- Milestone status is explicit. A checklist completion is a task status change.
- Archive preserves data and relationships. Delete permanently removes only selected cards.
- Ctrl/Cmd+click selection persists across search/filter changes until cleared; the count
  includes hidden selected cards. Switching archive scope clears selection.
- Comments and update entries are both deletable; deletion does not undo changes.
- Every card retains its stable `#C` identity, with two-digit minimum padding. Milestones
  display editable, saved `#M` numbers; gaps are allowed and archived numbers remain reserved.
- A completion celebration is only for a successful local task transition into Done.
- Tab pinning follows existing behavior; board search/filter state lasts while its tab
  session remains open, while card data and tab metadata survive reloads.
