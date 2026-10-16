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
- [x] Run full regressions, assets, packaging and shard checks; publish final changes.

## Verification
- Starting commit: `582c3b6`; baseline 20 JavaScript and 108 Python tests.
- Final gates: 47 JavaScript, 112 Python and all 423 Chromium/Firefox browser cases passed.
- Assets rebuild cleanly; wheel/source distributions and shared fixture contents verified.
- Browser shards `[106, 106, 106, 105]` cover the complete collection without duplication or retries.
- Light/dark/narrow layouts inspected; dense projection benchmark verifies identical ranges.
- Protected instructions, `REFACTOR_PLAN.md`, and `AGENTS.md` remain byte-for-byte unchanged.
- See `docs/VERIFICATION.md`, `docs/STATE_CONTRACTS.md`, and PR #15 for implementation and evidence.
