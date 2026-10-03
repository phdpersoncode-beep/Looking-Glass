# Local discussion interface

Base URL: `http://127.0.0.1:8765/api`. The server must already be running on
the same machine and opened on the same directory as `--root`.

Each request needs the `X-Looking-Glass-Token` header. Its value is the contents
of `<project>/.looking-glass/token`. This file is created with owner-only access
on Unix. The CLI reads it automatically. The server rejects cross-origin calls
and accepts only loopback hostnames. HTML report previews never receive this token.
There are no built-in model calls or automatic editing passes.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/threads?path=welcome.md` | List threads; omit `path` for all files |
| GET | `/threads/1` | Read one thread and all messages |
| POST | `/threads` | Create an anchored thread |
| POST | `/threads/1/replies` | Append a reply |
| PATCH | `/threads/1` | Resolve/reopen or reattach |
| DELETE | `/threads/1` | Delete a thread and all its comments |
| DELETE | `/threads/1/messages/2` | Delete one comment; remove an empty thread |
| GET | `/file?path=welcome.md` | Read current disk text and version |
| PUT | `/file` | Save with a required current version hash |
| GET | `/workspace` | Workspace root and available file paths |
| GET | `/agent-instructions` | Copyable instructions for this workspace and server |
| GET | `/git/baseline?path=welcome.md` | Last committed text for editor gutter markers |

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
