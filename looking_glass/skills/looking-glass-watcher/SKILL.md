---
name: looking-glass-watcher
description: Start a background watcher that answers new Looking Glass discussion activity as it happens. A subagent polls about every 30 seconds. When the user opens a thread or replies, the watcher checks the code and available data, runs a small experiment if needed, and gives an intuitive, concise answer in the thread. It also applies small requested edits. Use when the user invokes /looking-glass-watcher, asks to watch or monitor their Looking Glass threads, or asks to stop watching. Use the Looking Glass agent CLI for a one-off review of existing threads.
---

# Looking Glass watcher

The user reviews files in Looking Glass and anchors comments to passages. This skill keeps an agent on call during that review. A background **watcher subagent** blocks on `scripts/lg_watch.py`, which polls the local server cheaply. When the user posts, the script returns the new activity. The subagent grounds an answer in the project, replies, and resumes waiting.

The main session stays free for conversation. It only starts, stops, and relays.

Agent replies never wake the watcher. Only messages whose author matches a human label (default `User`) do. This rule prevents loops with other agent sessions on the same project.

## 1. Find the project

- Take a path from the arguments, or use the current directory if it sits inside a project (an ancestor contains `.looking-glass/token`).
- Otherwise run `looking-glass projects list` and pick the reachable project that matches. Ask only when several reachable projects could match.
- Never start or restart a server. Another session may be using it. If the project is unreachable, tell the user the command they can run, such as `looking-glass serve <root>`, and stop.

Optional arguments: human labels (`--human`), idle limit in minutes (default 30), and constraints such as "reply only" or "only plan.md". Pass constraints through verbatim.

## 2. Avoid a second watcher

Run `pgrep -af "lg_watch.py wait --root <root>"`. If a watcher runs for this root, say so and do not start another. Two watchers would answer the same thread twice.

## 3. Start the subagent

Spawn one `general-purpose` subagent. It runs in the background. Fill in the brackets:

```
You are the Looking Glass watcher for one project.
First read <skill-dir>/references/watcher-agent.md and follow it.
Scripts: <skill-dir>/scripts/

Project root: <absolute root>
Human labels: <e.g. User>
Idle stop: <seconds, default 1800>
Constraints from the user: <list, or "none">
Today: <YYYY-MM-DD>
```

`<skill-dir>` is the directory that contains this SKILL.md.

Then tell the user in two or three lines:

- The watcher runs for `<root>` and checks about every 30 s.
- It reacts only to new activity by `<labels>`, not to threads that already existed.
- It stops after `<N>` minutes without activity, or when the user says "stop watching".

## 4. Stop on request

When the user asks to stop, run `python3 <skill-dir>/scripts/lg_watch.py stop --root <root>`. The waiting script exits within a second during polling sleep. The subagent then writes its final report.

## 5. Relay the final report

When the subagent finishes, give the user a short summary:

- Each thread handled: ID, a one-line outcome, and changed files.
- Edits awaiting the user's approval, such as review drafts to approve in the browser.
- Threads it skipped or asked the user about, with the reason.
- Why it stopped: idle, stop request, or unreachable server.

Keep the relay shorter than the report. The replies themselves live in the threads.
