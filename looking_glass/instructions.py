"""Portable instructions shared by the browser and terminal."""
import shlex


def agent_instructions(root, url):
    command = f'looking-glass agent --root {shlex.quote(str(root))} --url {shlex.quote(url)}'
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

For Markdown, prefer --body-file FILE or --body-stdin. With --body, use single shell quotes: double quotes execute backticks and $(...).

List and search return paginated JSON summaries. Use --offset and --limit for more results.
Read each thread and its current passage context before responding. Use IDs from list or search.
Reply in the existing thread. When an anchor needs reattachment, read its discussion and original review context.
Reattach only when the intended replacement is clear; otherwise ask for guidance. Use --occurrence N for a repeated quote.
Reattach also corrects a wrong attached passage; it preserves messages, original context, and open/resolved state.
Apply file edits only when requested. Explain your changes in the thread.
Resolve a thread when its requested work is complete.
Run looking-glass --help or append --help to any command for options and examples.
Run {command} instructions to read these instructions again.'''
