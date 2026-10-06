# Local discussion interface

Base URL: `http://127.0.0.1:8765/api`. The server must already be running on
the same machine and opened on the selected project. Restart servers started
before a CLI upgrade so their API supports the new commands.

## Installed CLI

```bash
uv tool install --editable /absolute/path/to/Looking-Glass
looking-glass projects list
looking-glass projects show /absolute/path/to/project
looking-glass agent --root /absolute/path/to/project list --status open
looking-glass agent search 'shebang' --status open --author Altay
looking-glass agent read 2 --context-lines 10
looking-glass agent reply 2 --author OpenCode --body 'My explanation.'
looking-glass agent instructions
looking-glass agent --help
looking-glass agent search --help
```

Every command provides `--help` with options and an example. Put `--root` and
`--url` before the agent operation. Without `--root`, the CLI searches current-directory
ancestors for project metadata or a registered root. Without `--url`, it uses the
registered address, falling back to `http://127.0.0.1:8765`.

`serve` registers its root and address. Browser directory switches register the
new root. The registry defaults to `~/.config/looking-glass/projects.sqlite3`.
`XDG_CONFIG_HOME` changes the configuration base. `LOOKING_GLASS_CONFIG_DIR`
overrides the configuration directory. The registry stores roots and URLs, never tokens.
Projects remain listed when stopped; reachability requires an authenticated root match.
`projects show` returns file paths and all/open/resolved thread counts.

`list` and `search` share `--status`, `--path`, `--author`, `--anchor-status`,
`--limit`, `--offset`, and `--full`. Search matches literal, case-insensitive text
in anchored quotes and all comment bodies. Author matching uses an exact,
case-insensitive label on any message. Filters combine.

Results contain `threads`, `total`, `limit`, `offset`, and `next_offset`.
Threads are ordered by ID. The default page size is 50; the maximum is 1000.
Summaries include IDs, paths, quotes, state, message count, and the last message
with its body limited to 240 characters. Use `--full` for complete messages.
`read` includes current passage context with 10 surrounding lines by default.
Commands print JSON; `instructions` prints text. Errors use stderr and a nonzero exit code.

## Markdown bodies and shell quoting

`create` and `reply` accept exactly one of `--body`, `--body-file FILE`, or
`--body-stdin`. `--body-file -` also reads standard input. Files use UTF-8.
Bash executes backticks and `$(...)` inside double quotes before the CLI sees
anything. Use single quotes for short literal text, or a file/quoted here-document:

````bash
looking-glass agent reply 2 --body-file explanation.md
looking-glass agent reply 2 --body-stdin <<'MARKDOWN'
Use `width` as the named parameter.
```python
width = 12
```
MARKDOWN
````

## HTTP API

Each request needs the `X-Looking-Glass-Token` header. Its value is the contents
of `<project>/.looking-glass/token`. This file is created with owner-only access
on Unix. The CLI reads it automatically. The server rejects cross-origin calls
and accepts only loopback hostnames. HTML report previews never receive this token.
There are no built-in model calls or automatic editing passes.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/threads?path=welcome.md` | List threads; omit `path` for all files |
| GET | `/threads/1/original` | Exact saved review source and anchor metadata |
| GET | `/threads/1/messages/2/original` | Saved source when that comment was added |
| GET | `/threads/1` | Read one thread and all messages |
| POST | `/threads` | Create an anchored thread |
| POST | `/threads/1/replies` | Append a reply |
| PATCH | `/threads/1` | Resolve/reopen or reattach |
| DELETE | `/threads/1` | Delete a thread and all its comments |
| DELETE | `/threads/1/messages/2` | Delete one comment; remove an empty thread |
| POST | `/threads/1/attachments` | Upload a multipart `file` field (up to 64 MiB) |
| GET | `/attachments/1` | Download the original attachment bytes |
| PATCH | `/attachments/1` | Rename with `{"name":"feedback.json"}` |
| DELETE | `/attachments/1` | Remove an attachment |
| GET | `/file?path=welcome.md` | Read current disk text and version |
| PUT | `/file` | Save with a required current version hash |
| GET | `/workspace` | Workspace root and available file paths |
| GET | `/project` | Workspace root only, for inexpensive identity checks |
| GET | `/agent-instructions` | Copyable instructions for this workspace and server |
| GET | `/git/history?limit=100` | Paged branch graph metadata and commit messages |
| GET | `/git/baseline?path=welcome.md` | Last committed text for editor gutter markers |

Paths above are relative to `/api`. Full thread responses include `attachments`
with `id`, `thread_id`, `name`, `size`, and `media_type`. Display names can change;
download bytes remain unchanged. Attachments belong to the thread, survive server
restarts, and are removed when the thread or its last message is deleted. All four
attachment endpoints require the same token as other API requests.

### Thread queries and context

`GET /threads` without query options retains its full-array response for existing callers.
An optional `path` alone also retains that response. Supply any option below
to request a paginated response:

| Parameter | Meaning |
| --- | --- |
| `status` | `all` (default), `open`, or `resolved` |
| `q` | Literal, case-insensitive substring in quotes or message bodies |
| `author` | Exact, case-insensitive author label on any message |
| `anchor_status` | `attached` or `needs_reattachment` |
| `limit` | Page size, 1–1000; default 50 |
| `offset` | Nonnegative matching-thread count to skip; default 0 |
| `summary` | `true` (default) for compact summaries; `false` for complete threads |

```json
{"threads": [], "total": 0, "limit": 50, "offset": 0, "next_offset": null}
```

`GET /threads/1?context_lines=10` adds a `context` object. The allowed range is 0–100.
Source context contains the current `version`, one-based `start_line` and `end_line`,
one-based `first_line` and `last_line`, and unmodified `content` for those lines.
Rendered context contains `kind: "rendered"`, `quote`, `prefix`, and `suffix`.
Unreliable source anchors return `kind: "unavailable"` with a `reason`.
Without `context_lines`, the original thread response remains unchanged.

### Creating and updating discussions

Create body:

```json
{
  "path": "welcome.md",
  "start": 0,
  "end": 10,
  "version": "<version returned by GET /file>",
  "author": "Codex",
  "body": "Explain this passage."
}
```

Offsets are zero-based **Unicode code points**, with an exclusive `end`, in the
actual disk text (including CRLF when present). Do not count UTF-8 bytes or
JavaScript UTF-16 code units. For `🪞 Hello`, `Hello` starts at offset 2. Use the
CLI's exact `--quote` option to avoid manual offsets.

Reply body: `{"author":"Codex","body":"A proposed explanation."}`.
Resolve body: `{"resolved":true}`. Reopen: `{"resolved":false}`.
Reattach body: `{"start":12,"end":30,"version":"<current file version>"}`.

Deletion returns `{"deleted":true}`. Message IDs come from a thread's `messages` array.
The CLI supports `delete THREAD_ID` and `delete THREAD_ID --message MESSAGE_ID`.
Deleting the last message removes the thread and its anchor. Deletion is permanent.

A response thread includes `id`, `path`, `start`, `end`, `quote`, `anchor_status`,
`resolved`, timestamps, and a `messages` array. `anchor_status` is either
`attached` or `needs_reattachment`. Treat an orphan as a question for a human,
not permission to guess another passage.

Threads also include `anchor_kind`: `source` or `rendered`. A rendered thread has
`render_anchor` containing `quote`, `prefix`, and `suffix`. Its `start` and `end`
are placeholders, not HTML-source positions. Agents can list, read, reply, resolve,
reopen, and delete rendered threads through the existing CLI.

To create a rendered thread through the API, replace `start` and `end` with:

```json
{"render_anchor":{"quote":"Visible report text","prefix":"","suffix":""}}
```

The quote must match rendered text. Prefix and suffix each allow up to 48 characters.
The browser checks attachment while the report is open. Reattach with a PATCH body
containing `render_anchor` and the current file `version`. Source-offset reattachment
is rejected for rendered threads.

```bash
token="$(cat ./demo_dir/.looking-glass/token)"
curl -H "X-Looking-Glass-Token: $token" \
  'http://127.0.0.1:8765/api/threads?path=welcome.md'
curl -X POST -H "X-Looking-Glass-Token: $token" \
  -H 'Content-Type: application/json' \
  -d '{"author":"Codex","body":"I can clarify the example."}' \
  http://127.0.0.1:8765/api/threads/1/replies
```

Errors are JSON objects with an `error` string. `409` means the disk file or
selection became stale; read the file again and reconcile deliberately. `401`
means the token is missing or invalid. `403` means an origin/path is forbidden.
`404` means a file/thread is missing. Invalid input returns `400`.


### Commit anchors and original context

Thread and message objects include `commit_hash` and small `origin` metadata.
The hash records HEAD when the discussion/comment was captured. An immutable,
compressed source snapshot preserves the exact reviewed content, including
uncommitted changes and untracked files. Reattachment changes the live anchor;
it never overwrites the original. File deletion keeps discussions and replies.
The two `/original` routes return `{path,content,origin}`, with original quote,
positions, rendered quote context, commit hash, and snapshot hash. They require
the local token and do not read or restore the working file.

Legacy discussions are marked `recovered` (last observed source) or
`recovered_quote` (only the quote survived). Their hash is captured at migration,
not an invented historical commit. Without Git or a first commit, the hash is
null and the review snapshot still survives. A reply on a missing passage uses
`inherited` context and records the current HEAD. Runtime-generated HTML text is
retained as quote/prefix/suffix; the snapshot preserves the HTML source.

### Comments with files

`POST /threads` and `POST /threads/1/replies` also accept multipart form data:
a `data` field containing the existing JSON request, and repeated `files` fields.
A comment may have an empty body when it includes a file. Maximum: 16 files and
64 MiB combined, with multipart framing allowed by the request limit. On a file
failure, the new comment and its partial uploads are removed so a retry is safe.
Attachment metadata includes nullable `message_id`: legacy/thread-level files
have null; files sent with a comment belong to that comment. Deleting a comment
removes its own files. The standalone attachment endpoint accepts an optional
`message_id` form field, verified to belong to the target thread.

### Git graph pagination

`GET /git/history` returns local and fetched remote `branches`, `commits`, `tips`,
and `next_offset`. Commits include parents, author/committer identities, date,
short subject, and full message. Use repeated `branch=refs/heads/name` parameters
to select branches. The default includes all branches and detached HEAD.
For the next page, repeat the returned `tip` hashes and send `offset=next_offset`;
this freezes the traversal while new commits are made. The limit is 1–200
(default 100). History is newest first with ancestry order preserved. No fetch,
checkout, index mutation, or automatic commit occurs.
