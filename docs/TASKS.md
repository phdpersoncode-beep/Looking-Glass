# Shared Tasks board

Open **Tasks** beside **Commit history**. It opens a normal tab that can be pinned,
closed, and restored after a browser refresh. The board belongs to the open
workspace, including when agents use the CLI from another directory.

The four columns are **◌ Backlog**, **◐ In progress**, **◎ To review**, and **✓ Done**.
Drag a card onto another card to insert before it, or onto a column to append.
Click a card (or press Enter while focused) to edit its title, description,
status, and milestone. Changing status in the editor is the keyboard alternative
to dragging. All titles and descriptions are treated as plain text.

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

Statuses are `backlog`, `in_progress`, `to_review`, `done`. Editable fields are
`title`, `description`, `status`, `milestone` (boolean), `milestone_id` (integer or
null), and `archived` (boolean). Move's optional `before` identifies an active card
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
- A completion celebration is only for a successful local task transition into Done.
- Tab pinning follows existing behavior; board search/filter state lasts while its tab
  session remains open, while card data and tab metadata survive reloads.
