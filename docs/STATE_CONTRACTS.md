# Application behavior contracts

Each fact has one owner. Rendering reads state; user events and accepted remote
results dispatch transitions. Scrolling is an explicit effect and can repeat
even when the focused thread does not change.

| Fact | Owner | Consumers |
| --- | --- | --- |
| Requested/displayed document, requested/focused thread, spotlight seeds, search/scope, zen fallback | Application store | Sidebar, toolbar and surface projections |
| Workspace review preference | Application store/preferences | Per-document mode controller |
| Local content, selection, undo and per-mode editor state | Document session | Mounted editor and previews |
| Draft operations, saved revision and synchronization status | Per-document review controller | Toolbar and review surface |
| Durable threads, anchors, draft revisions and origins | Backend | Versioned frontend snapshots |
| Nodes, browser ranges, scroll geometry and mounted resources | Surface lifecycle/adapter | Navigation effects |
| Reply body, pending attachments and send state | Composer controller | Existing reply form |

| Event | Decision | Reading effect |
| --- | --- | --- |
| Document highlight | Focus thread and overlapping passage group | Preserve reading position |
| Sidebar card | Focus and spotlight thread; retain native sidebar focus/selection | Reveal passage |
| Sidebar comment icon | Focus and spotlight thread | Reveal passage |
| Unanchored/unavailable thread | Focus sidebar only; preserve the current surface | No automatic context tab or scroll |
| Original context button | Explicit context visit | Open immutable passage; return restores the suspended surface |
| Repeat activation | Same focus | Reveal passage again |
| Unchanged poll | Same state | No navigation or node replacement |
| Search/scope/zen change | Pure visible-thread selector and explicit fallback transition | No incidental navigation |
| Spotlight arrows | Advance the requested-thread cursor; coalesce each frame and supersede unfinished reveals | Keep the current spotlight until the destination is ready; reveal the latest passage |
| Zen resolve/delete | Advance to next open thread in the pre-mutation queue; retain spotlight if active | Reveal next passage; final completion stays put |
| Go to top | Preserve selection and document state | Scroll the displayed document surface to its beginning |
| Original context visit/return | Suspend/resume existing surface | Restore selection, undo, report state and scroll |
| Mode switch | Save pending writes; switch compatible session | Restore that mode's selection and undo |

Navigation promises resolve only after the requested surface is ready, or report
supersession/failure. Superseding a read never cancels a write. Async completions
must match their request, document/session identity and revision before applying.
Failed mode preparation must leave the previous mode and preference coherent.
Thread-driven document changes prepare destination discussions while retaining the
current document and cards, then commit the document, snapshot and focus together.
Cancellation before that commit leaves the previous pair intact. Intent updates do not redraw
the sidebar. Sidebar numbers/quotes/cards use the same activation, and source
selection/focus decorations update in one transaction. Focusing search/reply,
changing filters, Escape, or another explicit navigation cancels pending arrows.
Hiding a review discussion in Edit must retain its reply, attachment previews
and composer nodes. Only a newer authoritative index for the same visibility
universe can retire a cached discussion; displaying older cached data cannot.
Approval remains bound to the document, draft ID and revision confirmed by the
user; later edits invalidate that target.

Python anchor offsets count Unicode code points. Raw browser offsets count
UTF-16 code units; CodeMirror offsets additionally normalize CRLF. Named boundary
conversions must distinguish these coordinates. Resolution returns `attached`,
`needs_reattachment`, or `unavailable`, with a document reference, range and reason.
Known edit mapping and recovery after unknown edits remain distinct algorithms.

The existing Chromium and Firefox journeys remain required. Controlled-promise
tests cover queued/stale completions and writes during saves; pure tests cover
scope, overlap, ambiguity and Unicode. Browser tests establish scroll, selection,
undo, copying and interactive-report behavior.
