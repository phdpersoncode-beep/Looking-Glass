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
require reattachment; the old original remains stored. SVG continues to render, but does not support these editing tools.

The top-right pencil opens Red pen, Eraser, Undo, Redo, Comment, Save image,
and Restore original. The eraser restores original pixels, including over
previously saved pen marks. Drawing edits stay local until Save image. Undo/redo
covers the current editing session, with bounded history to control memory.
Restore original restores the initially imported bytes and keeps discussion
threads. Drawing saves are immediate image changes in either document mode;
Markdown Review approval governs Markdown text changes, not image pixels.

Choose Comment and click an image location to enter text. A small square marker
opens the thread and a reply box. These are ordinary Looking Glass threads:
search, replies, resolve/reopen, deletion, API access, and persistence apply.
Thread responses include `associated_with_image: true` and
`image_annotation: {thread_id, image_id, x, y}` with normalized coordinates.
The source anchor remains attached to the embed, so deleting the embed marks
its thread as needing reattachment. Multiple embeds of the same asset share its
image markers; a newly created thread anchors to the first matching embed in
the active document.

Right-click a rendered PNG/JPEG or its source Markdown embed to rename it.
The hash stays stable. The active document's links update as an ordinary editor
change; save the document normally (or approve its Review draft). Old managed
references continue to resolve by hash, and registered disk paths retain an
alias inside Looking Glass. Other applications need links updated after a disk
rename. Renaming refuses to replace an existing file.

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
- `POST /api/images/<id>/comments`: ordinary source selection fields
  (`path`, `start`, `end`, `version`, `body`, `author`, optional `review_id`),
  normalized `x`, `y`, and `reference` for disk image embeds.

The browser tests synthesize the standard clipboard image payload. Manual
checks with each OS's screenshot utility remain necessary to establish its
native clipboard integration.
