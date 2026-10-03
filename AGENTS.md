# Looking Glass

Below is the project description and what we want to build for the first iteration:
```
We’re going to build a **Code review and editing tool with support for viewing 3D STL files, JSONL files, and HTMLs.** The project is called **Looking Glass**.

First get the bones up. Python, HTMX for interactions, SQLite backend, Tailwind frontend, use a local build not the CDN.

Really excellent prose and code editor, Notion-style. Very basic Python and Bash syntax highlighting, bare-bones code editor. Support for Ctrl+A, Ctrl+F, and Ctrl+H. Light and dark mode support, neon purple highlights. Minimalist style. Mono font for code and JSON and Times New Roman for text (Markdown and txt). Markdown dynamic rendering like Obsidian.

Support highlighting (we’re going to do editing passes). Do Genius-style sidebar commentary to match highlighted things for Markdown and code. Comment support for rendered HTML can come later. Make sure we can tick forward and back through suggestions.

Use Git as the version tracking and revision system.

HTML files should be rendered. The main goal of HTML files is to use them for viewing coding-agent-generated reports and explainers. HTML files should be commentable and switchable between the raw HTML and the rendered HTML.

Bare-bones JSONL viewer, split screen: on the left the full JSONL and on the right the currently selected row as indented and nicely formatted JSON with basic syntax highlighting.

File selector sidebar on the left to see all files in the current directory. Support for tabs like VS Code -- pinning tabs, closing tabs other than the other one.

Get me this far then I’ll tell you what I really want.

**Clarifications for this first implementation:**

- **Main workflow:** I open a local project directory, read and edit files, highlight passages, and have persistent discussion threads with my coding agents about those passages. Anchored comment threads are the highest priority.&#x20;

- **Local files:** Run as a local web application. The project’s files on disk remain the source of truth, so Codex and other local tools can work on the same files. Use SQLite for annotations and application metadata. Detect external file changes; reload clean files and warn about conflicts with unsaved edits before overwriting anything.

- **Editing:** “Notion-style” means a clean, direct editing experience. “Obsidian-style” means Markdown renders inline while I edit, with syntax exposed around the active passage; provide a raw-source mode too. Preserve Markdown as ordinary Markdown files and keep `.txt` files plain text. Use an established editor component and whatever client-side JavaScript it needs alongside HTMX. Include undo/redo, saving, an unsaved-change indicator, and selection-aware keyboard shortcuts. Ctrl+F and Ctrl+H should search and replace within the active document.

- **Annotations and discussions:** Selecting text or code should let me create a highlight and open a thread in a right-hand sidebar. Support replies, author labels, resolving/reopening threads, and previous/next navigation that scrolls to the corresponding passage. Comments are feedback; they do not automatically replace the highlighted text. Persist threads across restarts. Keep anchors attached through ordinary edits; if an anchor becomes ambiguous or its passage disappears, mark it as needing reattachment instead of silently attaching it elsewhere.

- **Agent access:** Provide a small, documented local interface that lets a coding agent list/read threads, create comments, reply, and resolve/reopen threads. Choose the simplest practical interface and include example commands. For now, agents run separately in my terminal; built-in model calls and automatic editing-pass orchestration can come later.

- **Git:** Saving writes files; creating a revision is an explicit Git checkpoint. Let me inspect changes and create a named checkpoint for the files I select. Reuse an existing repository, and never automatically commit unrelated changes or discard work.

- **Viewers:** STL needs basic 3D viewing with orbit, pan, zoom, and fit-to-view, supporting binary and text STL files. JSONL means one JSON value per line; show malformed lines without breaking the viewer. Render HTML in an isolated preview that supports interactive reports without giving their scripts access to the editor’s application state. No need to annotate JSONL and STL viewers. Annotating HTML files from the rendering would be good.

- **First milestone:** Deliver a working end-to-end version, not just a visual mockup. Verify by opening a scratch directory under the repo root demo_dir/ you fill up with placeholder files, editing and saving Markdown/code, creating and replying to an anchored thread from both the interface an d a local command, restarting without losing comments, handling an external file change, and opening representative STL, JSONL, and HTML files.

Plan the repository first. Briefly explain your implementation choices, then build it. Keep the architecture small, document how to install and run it locally, and record limitations and deferred features. Make reasonable decisions for unspecified details; ask only when a decision would materially change the scope or workflow.

```
