# Refactor Plan

**The main problem is distributed ownership of behavior.** Functions that appear to filter or render also change focus, reconcile anchors, and initiate navigation. This makes correctness depend on the order in which several functions happen to run.

I recommend an incremental refactor within the existing stack, starting with thread focus and navigation.

**What is creating friction**

Most coordination lives in the 1,482-line [`frontend/app.js`](https://github.com/phdpersoncode-beep/Looking-Glass/blob/5062f72/frontend/app.js). Its size matters less than how many responsibilities interact inside it.

| Friction point | Concrete evidence | Why it becomes difficult |
|---|---|---|
| Focus has several cooperating representations | `activeThread`, `spotlightPassage`, the spotlight controller’s private IDs, CodeMirror’s focus field, and the HTML preview’s `active` value | Each representation requires manual synchronization. Some are legitimate projections, but ownership is not enforced. |
| Rendering changes application state | `filterThreads()` selects a new active thread in zen mode. `renderDiscussions()` updates thread data, changes selections, reconciles highlights, and can trigger return from original context. | Calling “render” can change what the user is doing. |
| Navigation mixes decisions with execution | `jump()` chooses files, original context, presentation modes, spotlight behavior, selection, scrolling, and keyboard focus. | Every new surface or anchor type adds branches to one central procedure. |
| Async coordination is fragmented | `switching`, `queuedFile`, `refreshNumber`, `navigationQueue`, `polling`, and per-review save flags | Individual safeguards exist, but there is no common completion or stale-response contract. `openFile()` can return before a queued file actually opens. |
| Passage logic crosses rendering boundaries | `spansFor()`, `syncSpotlight()`, Markdown `visibleMap()`, and HTML `locate()` mix domain decisions, coordinate conversion, and browser objects. | Testing passage identity often requires rendering the interface. |
| Changed discussions replace the whole list | `renderDiscussions()` assigns `#threads.innerHTML`, then restores replies, focus, selection, and scroll. | Preserving interaction requires an expanding collection of repair steps. |
| Document sessions lack a uniform lifecycle | `contextVisit` carries editor instances, nodes, cleanup functions, preview state, and scroll snapshots. Other transitions destroy and remount surfaces. | Preserving undo, selections, and interactive reports becomes transition-specific. |

One additional issue deserves an early regression test: `ensureWorkMode()` saves `e.original.state`, but nothing restores that saved state; mode changes reset `e.state`. That exposes a gap around the stated requirement to preserve undo history through mode changes.

There are good foundations to retain: [`review-model.mjs`](https://github.com/phdpersoncode-beep/Looking-Glass/blob/5062f72/frontend/review-model.mjs), [`thread-search.mjs`](https://github.com/phdpersoncode-beep/Looking-Glass/blob/5062f72/frontend/thread-search.mjs), and [`anchors.py`](https://github.com/phdpersoncode-beep/Looking-Glass/blob/5062f72/looking_glass/anchors.py) already separate substantial logic from presentation.

**What “one source of truth” should mean here**

It should mean **one owner for each fact**, rather than one enormous object containing every browser detail.

| State | Authoritative owner | Other components |
|---|---|---|
| Active tab, focused thread, spotlight selection, search query and scope | Small application state store | Read projections and dispatch user intentions |
| Workspace review preference | Application preferences | Persisted to local storage |
| Actual edit/review session and synchronization status | Per-document session | Toolbar displays the effective state |
| Local document, selection, undo history | Document session owning its CodeMirror state | Previews consume versioned snapshots |
| Saved discussions, review revisions, durable anchors | Backend | Frontend holds versioned data and local edit projections |
| Scroll geometry, browser ranges, mounted editor/iframe instances | Surface adapter | Never independently decides application focus |

The distinction between review preference and actual session mode is intentional. A workspace can prefer Review while an HTML file remains in Edit. Likewise, ordinary-file anchors and review-draft anchors describe different document versions; they should remain separate.

**How transitions should work**

A sidebar card would express one intention:

```js
dispatch({
  type: "THREAD_ACTIVATED",
  threadId: 42,
  origin: "sidebar-card"
});
```

One transition handler determines the selected thread, spotlight behavior, required document, and requested navigation. Rendering consumes the resulting state; a separate effect performs loading or scrolling.

| Interaction | State decision | Reading-pane effect |
|---|---|---|
| Click a document highlight | Focus the thread and its passage group | Preserve reading position |
| Click a sidebar card | Focus the thread; preserve sidebar text focus | Reveal the passage |
| Click a sidebar comment icon | Focus and spotlight the thread | Reveal the passage |
| Receive unchanged polling data | No focus change | No navigation |
| Click the already-focused card again | Focus remains unchanged | Reveal the passage again |

That last case matters: **scrolling is an explicit action, not an automatic consequence of “focused thread changed.”**

Cross-file navigation can have requested, loaded, and failed transitions. The goal is one authoritative decision per event, not pretending asynchronous work completes in one step.

**Additional principles I would adopt**

- **Derived values stay derived.** Visible threads, overlap groups, toolbar availability, and search hints should come from pure selectors—functions that compute an answer without changing state.
- **Every asynchronous result carries context.** Include the document/session identity, revision, and request ID. Reject obsolete results consistently. Superseding a navigation request must not discard pending writes.
- **Resource lifetimes are explicit.** Reading surfaces support `mount`, `suspend`, `resume`, and `dispose`. Original-context visits should use those operations.
- **Coordinates have explicit meanings.** Python counts Unicode code points; JavaScript and CodeMirror use UTF-16 code units, with additional newline normalization. Convert through named boundary functions.
- **Unchanged data causes minimal work.** Preserve existing nodes and editor state. A focus update should update focus decorations, not reconstruct all passage highlights.

**The refactoring sequence**

Each stage should be a small, independently reviewable pull request.

| Stage | Changes | Completion criterion |
|---|---|---|
| **1. Record behavior contracts** | Document ownership and the interaction table above. Add missing regression cases for queued navigation, repeated activation, mode-switch undo, and stale completions. | Existing intended behavior is explicit; confirmed defects are distinguished from behavior to preserve. |
| **2. Centralize thread focus** | Introduce a small store, pure transitions, and selectors. Move `activeThread`, spotlight seeds, and zen-mode fallback decisions into it. Make the spotlight controller a renderer. | All focus changes go through one transition path. Filtering and rendering cannot choose a different thread. |
| **3. Give navigation a completion contract** | Extract document-session and navigation controllers from `openFile()` and `jump()`. Track requested versus displayed documents. Await actual readiness before revealing a passage. | Rapid navigation cannot scroll or select inside the wrong file. Context return preserves the existing surface. |
| **4. Extract passage logic** | Separate overlap selection, coordinate conversion, Markdown mapping, and rendered-text anchor resolution from highlighting and scrolling. Introduce explicit anchor-resolution results. | Passage decisions can be tested without mounting an editor or browser page. |
| **5. Isolate review synchronization** | Extract operation batching, save sequencing, remote updates, conflicts, and approval targeting into a per-document controller. Keep review preference separate from session state. | Review transitions are explicit; failed mode changes leave coherent sessions; approval remains bound to the confirmed revision. |
| **6. Make discussion rendering incremental** | Maintain cards by thread ID. Update changed messages/statuses without replacing unrelated cards or composers. Give reply text and attachments one composer owner. | Incoming replies and polling preserve unrelated draft text, selection, focus, and scroll without wholesale restoration. |
| **7. Tighten backend boundaries selectively** | Separate reconciliation, discussion queries, and persistence behind the existing `Workspace` interface. Consolidate repeated review-scope rules while retaining efficient specialized queries. | Existing API, database, CLI, and approval behavior remains compatible. |

For stage 4, a useful result shape is:

```js
{
  status: "attached", // or needs_reattachment / unavailable
  documentRef,
  range,
  reason
}
```

The resolver decides *which passage*. A surface adapter translates that result into CodeMirror decorations, Markdown highlights, or browser ranges.

Not every anchor operation should share one algorithm. Mapping through known edit operations and recovering anchors after unknown external edits require different evidence. Both should obey the same conservative attachment contract.

For stage 5, use a few explicit statuses—such as `clean`, `pending`, `saving`, and `conflicted`—rather than combinations of loosely related booleans. Preserve the existing server-side revision checks and interrupted-approval recovery.

**How to test the separation**

| Layer | Tests |
|---|---|
| Pure logic | Passage ambiguity, overlapping threads, scope filtering, navigation policy, Unicode/newline conversions, review operations |
| Controllers with controlled promises | Out-of-order file loads, obsolete polling responses, edits arriving during saves, approval revision changes |
| Surface adapters | Given resolved passages and focus state, produce the correct decorations without unnecessary document replacement |
| Real browsers | Scroll stability, native copying, keyboard focus, undo, interactive HTML, context return, and cross-file navigation |
| Backend | Persistence, conservative reconciliation, stale writes, approval recovery, and existing agent contracts |

Use shared fixtures to check Python and JavaScript review-operation semantics against the same examples. Keep the existing Chromium and Firefox journeys; faster logic tests should supplement their browser-specific coverage.

**My recommended first implementation is stages 1–2: thread focus as one complete slice.** It directly addresses the recurring sidebar/highlight problems and establishes the transition pattern before tackling document and review lifecycles. Merely splitting `app.js` into smaller files would leave the underlying coupling intact.

Validation for this review: **20 JavaScript tests and 108 non-browser Python tests passed**. I did not run the browser suite or modify the implementation.
