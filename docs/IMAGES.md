# Markdown images and annotations

Paste PNG/JPEG clipboard images (including OS screenshots) into a Markdown
editor. Each paste gets a new SHA-256 identifier, even when the bytes match a
previous paste. Looking Glass inserts `![](.looking-glass/images/<hash>_<name>)`.
The current bytes are saved under that name in `.looking-glass/images/`; SQLite
stores the current image and an immutable original for recovery. Include the
whole `.looking-glass` directory in workspace backups.

Both standard Markdown images and Obsidian-style `![[photo.png]]` embeds render
in Live Markdown and Reading preview. Relative disk images resolve from the
Markdown file's directory, inside the workspace. PNG/JPEG disk images are
registered when first rendered; annotations update that disk file as well as
the managed copy. An external disk change rejects an open annotation editor's stale save.
On reopening, the replacement gets a new identity and old disk-image comments
require reattachment; the old original remains stored. SVG supports display resizing; pixel annotation remains limited to PNG/JPEG.

The pencil above the image opens a roomy, centered annotation editor (up to
1280 × 840 pixels, with margins around the window). Its symbol
toolbar offers Red pen, Eraser, Undo, Redo, Comment, Save image, Restore original,
and Close; hover or focus a control for its label. The image fits the available
area without cropping, with room around edge markers. Comments appear beside
the canvas, or below it in narrow windows, in both themes. The eraser restores original pixels, including over
previously saved pen marks. Drawing edits stay local until Save image. Undo/redo
covers the current editing session, with bounded history to control memory.
Restore original restores the initially imported bytes and keeps discussion
threads. Drawing saves are immediate image changes in either document mode;
Markdown Review approval governs Markdown text changes, not image pixels.

Choose Comment and click an image location to enter text. Ctrl+Enter (or
Cmd+Enter) sends a comment or reply; plain Enter adds a line. Failed submissions
retain the text and show the error. Repeated shortcuts while sending create
only one comment. A small discussion symbol opens the thread and a reply box. These are ordinary Looking Glass threads:
search, replies, resolve/reopen, deletion, API access, and persistence apply.
Thread responses include `associated_with_image: true` and
`image_annotation: {thread_id, image_id, x, y}` with normalized coordinates.
The source anchor remains attached to the embed, so deleting the embed marks
its thread as needing reattachment. Multiple embeds of the same asset share its
image markers; a newly created thread anchors to the first matching embed in
the active document.

Right-click a rendered PNG/JPEG or its source Markdown embed to rename it in
a Looking Glass dialog. Enter saves the name; Escape or Cancel leaves it alone.
Invalid names and conflicts stay in the dialog so the name can be corrected.
The hash stays stable. The active document's links update as an ordinary editor
change; save the document normally (or approve its Review draft). Old managed
references continue to resolve by hash, and registered disk paths retain an
alias inside Looking Glass. Other applications need links updated after a disk
rename. Renaming refuses to replace an existing file. If a renamed image’s old
path is reused by a new disk file, that file receives its own image identity.
Percent-escaped filename characters such as `#` and `?` remain part of the name.

Rendered images are centered in the document. Drag the bottom-right resize
handle to adjust their display width while keeping their aspect ratio. A focused
handle also accepts Left/Right arrow keys in 10-pixel steps; Escape cancels an
active drag. Widths are stored per embed in Markdown using Obsidian-compatible
`![[photo.png|320]]` or `![Caption|320](photo.png)` syntax. Table cells escape the
pipe. Resizing is an ordinary undoable edit, including Review approval, and does
not change image pixels or the positions of image comments. Sizes adapt to narrow
panes and survive reopening. Images stay rendered during arrow-key navigation;
choose the small source symbol to edit an embed explicitly, then Done editing
image to return.

Ctrl+click an image's comment marker to enable drag mode. Drag it to a new
location, then release to save its position and automatically exit drag mode.
The next normal click opens the discussion. Ctrl+click again or press Escape
to exit drag mode; Escape during a drag cancels that move. This works in Live
Markdown, preview, and the annotation editor. Marker moves are immediate metadata
changes, keep the discussion and original context intact, and reject concurrent
moves instead of overwriting them. Normal clicks continue to open the thread.

Open an image marker to see its comments. Each comment has a trash symbol with
a Looking Glass confirmation; deleting one keeps the other comments and any
unsent reply. Deleting the last comment removes its marker. Threads with several
comments also have a trash symbol beside their thread heading to delete the
whole discussion. Cancellation or deletion errors leave the comment box and
reply draft available. These controls work in Live Markdown, preview, and the
annotation editor, and keep image pixels and document text intact.

The trash symbol beside the pencil removes the selected embed after a Looking
Glass confirmation. Cancellation is focused initially. Only that occurrence is
removed when an image appears multiple times. Removal is a normal document edit:
undo restores it, Edit mode saves it normally, and Review mode retains the disk
text until approval. Image bytes, originals, and discussions remain stored;
threads anchored to the removed embed need reattachment after saving/approval.
The app's rename, deletion, restore, and discard prompts use the same themed
dialogs, including attachment names and thread/comment deletion. Browser-level
leave-page protection for unsaved documents and pending attachments is retained.

Images are validated by Pillow, limited to 32 MiB and 40 megapixels. Annotation
updates must retain dimensions. Optimistic versions prevent two editors from
silently overwriting each other. Access to image bytes and mutation APIs uses
the existing local API token and origin protections.

API endpoints:

- `POST /api/images`: multipart `file`; returns ID, name, media type, version.
- `POST /api/images/import`: JSON `{path}` for a workspace PNG/JPEG.
- `GET /api/images/<id>`: metadata.
- `GET /api/images/<id>/content`: current bytes; `?original=1` for original bytes.
- `PATCH /api/images/<id>`: multipart `file` and `version`, or JSON
  `{version, name}` / `{version, restore: true}`.
- `PATCH /api/images/<id>/comments/<thread_id>`: normalized `{x, y,
  previous: {x, y}}`; updates marker position with optimistic concurrency.
- `POST /api/images/<id>/comments`: ordinary source selection fields
  (`path`, `start`, `end`, `version`, `body`, `author`, optional `review_id`),
  normalized `x`, `y`, and `reference` for disk image embeds.

The browser tests synthesize the standard clipboard image payload. Firefox
ignores the `clipboardData` constructor field on synthetic ClipboardEvents (see
[Gecko's constructor](https://github.com/mozilla/gecko-dev/blob/master/dom/events/ClipboardEvent.cpp)).
The tests therefore define the payload on the event instance, validate its file
types, and run the normal paste listener, upload, and insertion assertions.
This test-harness difference does not affect trusted OS paste events. Manual
checks with each OS's screenshot utility remain necessary to establish its
native clipboard integration.
