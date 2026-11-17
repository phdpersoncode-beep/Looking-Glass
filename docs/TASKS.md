# Shared Tasks board

Open **Tasks** beside **Commit history**. It opens a normal tab that can be pinned,
closed, and restored after a browser refresh. The board belongs to the open
workspace, including when agents use the CLI from another directory.

The four columns are **◌ Backlog**, **◐ In progress**, **◎ To review**, and **✓ Done**.
Drag a card onto another card to insert before it, or onto a column to append.
Click a card (or press Enter while focused) to edit its title, description,
status, and milestone. Changing status in the editor is the keyboard alternative
to dragging. All titles and descriptions are treated as plain text.

Milestone cards have a purple left bar; task assignment labels stay small and muted.
Every card keeps a permanent reference such as **#C01**, including while promoted.
Milestones display **#M1**, **#M2**, and so on. Open a milestone, edit
**Milestone number (#M)**, then Save to change its number as the plan evolves.
Numbers are unique positive integers from 1 to 999999, including archived
milestones. A duplicate number keeps the editor open with a clear error.

Saved numbers stay fixed until explicitly edited; promoting, demoting, deleting,
archiving, or moving another card never shifts them. New promotions take the
lowest unused number. Demotion restores the original #C identity and remembers
the previous milestone number; re-promotion reuses it when free, otherwise assigns
an unused number. The milestone editor also shows its permanent #C identity.
Existing boards retain the numbers displayed before this upgrade.

Search `#M1` or `M1` for a current milestone, or `#C01` / `C01` for a permanent card.
Both searches work while the card is promoted. Stable #C numbers survive restarts,
are never reused after deletion, and remain the references stored in activity history.
Assignments and edit headings follow milestone renumbering without changing the
underlying relationships or clearing unsent fields.

Use the **◇** button, with its hover tooltip, to promote a task to a milestone.
Milestones remain movable cards with their own status and description. Opening a
milestone shows its child tasks as a checklist with completion counts. Click a
child title to edit it; check a child to finish it. Unchecking returns it to
backlog. Tasks can belong to one milestone; milestones cannot be nested. Completing
all children does not move the milestone automatically.

Search matches a case-insensitive character subsequence across title and
description. The milestone filter shows the milestone and its children. Search,
filter, and archive scope combine. Ctrl+click (Cmd+click on macOS), or Space on a
focused card, toggles selection. Selected cards expose assign/unassign, archive,
restore, delete, and clear actions. Delete asks for confirmation; archive is
reversible through **Show archive**. Deleting or demoting a milestone keeps its
tasks and unassigns them. Archiving a milestone preserves its task relationships;
its tasks remain visible and the archived milestone is unavailable for new assignments.

Moving a task into Done produces a brief confetti burst and a soft synthesized
ding. Reduced-motion preferences suppress confetti. **Mute** persists in this
browser. Browser audio policy may suppress sound until audio is permitted. Polling
agent changes never plays completion effects. No audio files or external assets
are downloaded.

## Comments and activity

Each task and milestone edit view has **Comments & activity** below its fields
(and below the child checklist for milestones). People and agents share one
chronological conversation. Comments show their author and time; automatic updates
have an **Update** label and a thin grey row with smaller text, compact timestamps,
and the same delete control. Comments retain their larger reading space. Title,
description, status, assignment, promotion/demotion, archive/restore, and drag order
changes record their actual before/after values in the same transaction as the edit.
Milestones also record child assignment/unassignment. Description differences expand
on demand. Saving unchanged fields does not create an update or reorder the card.

Write a comment and click **Comment** (Ctrl/Cmd+Enter also submits). A trash icon
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

`read` returns card fields; `activity` returns conversation entries separately.
Card mutations also accept `--author` (default: Agent) to identify updates.
Use `tasks update C01 --revision N --milestone-number 12` to assign #M12 to a
milestone. Set `--milestone` in the same command to promote a task with a chosen
number. Only one milestone can receive an explicit number per update; duplicate
numbers, including archived owners, are rejected atomically.

`--milestone-id 0` unassigns; `--no-milestone` demotes. `--description-file -`
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
and `milestone_reference` (#M label or null). HTTP action IDs remain integers. `author` is optional
for mutations (defaults to User for HTTP; the browser uses its saved author).

Statuses are `backlog`, `in_progress`, `to_review`, `done`. Editable fields are
`title`, `description`, `status`, `milestone` (boolean), `milestone_id` (integer or
null), `milestone_number` (integer from 1 to 999999, for a single milestone), and
`archived` (boolean). Move's optional `before` identifies an active card
in the destination column. Responses return the complete updated board.

Cards and ordering persist in the existing `.looking-glass/state.sqlite3`; ordinary
SQL dump/restore includes them. Existing databases gain additive tables without
changing discussions or review data. UI polling refreshes only on a changed revision;
this first version loads the whole board, suitable for project planning rather than
an unbounded issue tracker. No new dependencies, agent execution, GitHub issue sync,
or automatic Git commits are introduced.

## Design assumptions

- One board per workspace, shared by people and independent agents.
- One milestone level and one optional milestone per task; milestones are promoted cards.
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
