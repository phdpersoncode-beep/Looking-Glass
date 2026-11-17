"""Portable instructions shared by the browser and terminal."""
import shlex


def agent_instructions(root, url):
    command = f'looking-glass agent --root {shlex.quote(str(root))} --url {shlex.quote(url)}'
    task_command = f'looking-glass tasks --root {shlex.quote(str(root))} --url {shlex.quote(url)}'
    return f'''Review this workspace through Looking Glass: {root}
The local server must be running. Use these commands from any directory:

looking-glass projects list
{command} list --status open
{command} search "search text" --status open
{command} read THREAD_ID --context-lines 10
{command} reply THREAD_ID --author "Agent" --body-file reply.md
{command} create "relative/path.md" --quote "Exact unique passage" --author "Agent" --body-file comment.md
{command} reattach THREAD_ID --quote "Exact replacement passage"
{command} resolve THREAD_ID
{command} reopen THREAD_ID

{command} review list
{command} review read REVIEW_ID
{command} review history REVIEW_ID --after 0
{command} review edit REVIEW_ID --version 'review:ID:REVISION' --author "Agent" --operations-file edits.json

Plan with the shared Tasks board:
{task_command} list
{task_command} read CARD_ID
{task_command} create 'Task title'
{task_command} activity C01
{task_command} comment C01 --author "Agent" --body-file reply.md
{task_command} delete-activity C01 ENTRY_ID
{task_command} update CARD_ID --revision BOARD_REVISION --status in_progress
{task_command} update CARD_ID --revision BOARD_REVISION --milestone
{task_command} update CARD_ID --revision BOARD_REVISION --milestone-number 12
{task_command} update CARD_ID --revision BOARD_REVISION --milestone-id MILESTONE_ID
{task_command} update CARD_ID --revision BOARD_REVISION --description-file plan.md
{task_command} move CARD_ID --revision BOARD_REVISION --status done
Use list/read's revision for every update, move, or delete. On conflict, reread and
reconsider; never blindly retry over human changes. Use --archived/--no-archived to
archive/restore. Deleting a milestone keeps its tasks and unassigns them. Milestones
are one level deep; completing children does not automatically complete the milestone.
Every card keeps a stable #C01 identity (quote shell arguments containing #).
Milestones have saved, editable #M1 numbers; use tasks list --query M1 to look one up,
then use its permanent card_reference for read/write commands. Change the number
with update --milestone-number N (1–999999). Numbers must be unique, including
archived milestones, and remain fixed until explicitly edited.
Field changes generate named updates in each card conversation. Comments and updates
can be deleted without reverting card changes; activity can be paged with --before.
Board writes plan work; they never execute tasks or change project files.

In review mode, never edit the source file on disk. Read the review draft, then send
a JSON array of sequential edits: [{{"start":0,"end":0,"insert":"new text"}}].
Offsets count Unicode code points in accepted draft text; removed ghosts do not count.
Supply the exact version you read. A stale edit is rejected; reread and reconsider it.
History includes inserted/removed text, author, role, and UTC edit times, including human edits.
Use list/search/read/create/reply --review REVIEW_ID for draft discussions and reply context.
Only the human approves a reviewed version in the browser; approval writes the accepted text.
Saving and approval do not commit. Changes & checkpoints inspects disk changes and creates
an explicit local Git commit for selected saved files; it does not push. Do not create a
checkpoint or commit unless requested. Preserve unrelated staged and unstaged work.

For Markdown, prefer --body-file FILE or --body-stdin. With --body, use single shell quotes: double quotes execute backticks and $(...).

List and search return paginated JSON summaries. Use --offset and --limit for more results.
The sidebar's Only unattached, Show resolved, and Across files filters only affect the browser;
use CLI list/search status, path, and review options to choose the intended scope.
In messages, reference workspace files as @src/part.py or @"notes/design sketch.md".
The browser renders clickable file references; code spans and email addresses stay literal.
In Markdown, preserve formula delimiters/LaTeX and table source when editing prose.
HTML reports run sandboxed; edit their source files rather than transient report DOM state.
Read each thread and its current passage context before responding. Use IDs from list or search.
Reply in the existing thread. When an anchor needs reattachment, read its discussion and original review context.
Reattach only when the intended replacement is clear; otherwise ask for guidance. Use --occurrence N for a repeated quote.
Reattach also corrects a wrong attached passage; it preserves messages, original context, and open/resolved state.
Apply file edits only when requested. Explain your changes in the thread.
Resolve a thread when its requested work is complete.
Run looking-glass --help or append --help to any command for options and examples.
Run {command} instructions to read these instructions again.'''
