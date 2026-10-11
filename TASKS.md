# Tasks

## Instructions (do not change unless you get explicit approval from the user) 
We are on a refactoring branch to improve the architecture of our Looking-Glass app, make it cleaner, more maintainable, more robust, and if possible faster.

See REFACTOR_PLAN.md to see what needs to be done. 

Use this TASKS.md file as your scratchpad and use it to keep track of tasks. Clean up or shorten completed tasks. Preserve these instructions here and the REFACTOR_PLAN.md.

Change the REFACTOR_PLAN.md only if you hit blockers or contradictions, a change to these instructions and REFACTOR_PLAN.md is only allowed if you get explicit approval from the user.


## Task list (you can change here)
- [x] 1. Record ownership/interaction contracts and regression cases.
- [x] 2. Centralize focus, spotlight, and scope in pure application transitions.
- [x] 3. Extract document sessions/navigation with awaited readiness and stale-result guards.
- [x] 4. Extract passage resolution, overlap selection, and coordinate/Markdown mapping.
- [x] 5. Isolate review synchronization, mode sessions, conflicts, and approval targeting.
- [x] 6. Update discussion cards incrementally; give composers one draft owner.
- [x] 7. Separate backend reconciliation/queries/persistence behind Workspace.
- [ ] Run full JavaScript/Python/browser regressions, assets, packaging, and shard checks; push final changes.

## Baseline and constraints
- Starting commit: `582c3b6` (main implementation at `5062f72`).
- Preserve the Instructions section above and `REFACTOR_PLAN.md` verbatim.
- Confirmed gaps: queued `openFile()` returns early; mode switches discard saved editor states; rendering/filtering currently changes focus.

## Verification in progress
- Baseline: 20 JavaScript and 108 non-browser Python tests passed.
- New controller/passage tests and shared Python/JavaScript operation fixtures added.
- Latest fast gates: 47 JavaScript and 112 Python tests passed.
- Chromium architecture/review/interaction journeys passed (26 cases); spotlight scroll regressions fixed and checked.
- Full Chromium/Firefox gate passed 421 cases; final hidden-review-scope retention regression added (423 total).
- Review-only reply/attachment retention and actual-deletion cleanup passed locally; final CI pending.
- Wheel/source builds, packaged shared fixtures, and complete/disjoint browser shards verified.
- Protected instruction and plan bytes verified unchanged before publication.
