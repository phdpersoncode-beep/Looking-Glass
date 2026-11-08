# Looking Glass Companion — private installation

This optional extension pairs Looking Glass with one VS Code window that has
**exactly the same local workspace folder** open. It coordinates dirty-file
protection and forwards saved-buffer language requests to your existing VS Code
providers. It has no third-party runtime dependencies, telemetry, model calls,
Git commits, or bundled language server. No Marketplace account, publisher
registration, access token, or publication is needed.

The extension and backend must both come from this branch/version. Installing
only the extension against unmodified PR22 will not work: PR22 contains the
[design](../docs/VSCODE_BRIDGE_SPEC.md), without bridge endpoints.

## Build and install on your own machine

Use Node.js 20+ (22 LTS recommended), npm, VS Code 1.96+, and the normal
[Looking Glass Python setup](../README.md#install-and-run). Node is only needed
for building; VS Code supplies its own extension-host runtime afterwards.

From the repository root:

```bash
uv sync --locked
cd vs_code_extension
npm ci
npm test
npm run package
```

The output is `vs_code_extension/looking-glass-companion-0.1.0.vsix`.
Install it with **Extensions → … → Install from VSIX…**, or:

```bash
code --install-extension vs_code_extension/looking-glass-companion-0.1.0.vsix --force
```

Run that command from the repository root. Reload the VS Code window if asked.
The manifest is private, the npm publish script refuses publication, and no
publishing step exists in CI. Keep the VSIX locally; generated bundles, VSIXs,
node_modules, application metadata and pairing credentials are ignored by Git.
The VSIX contains the manifest, bundled JavaScript and this README, without test
fixtures or development dependencies. No extension signing certificate is needed.

Rebuild/reinstall the VSIX after source changes. `npm run build` alone bundles
JavaScript; it does not install or update the extension. A development alternative
is to open `vs_code_extension/` in VS Code and launch an Extension Development Host
using `code --extensionDevelopmentPath=/absolute/path/to/vs_code_extension /absolute/path/to/project`.

## Pair a workspace

1. Start Looking Glass on the folder you want to edit:

   ```bash
   uv run looking-glass serve /absolute/path/to/project --port 8765
   ```

2. Open that exact folder in one trusted VS Code window. Multi-root workspaces,
   virtual/untitled documents, outside-workspace files and symlink paths are not
   paired. Resolve a symlink to the actual directory before opening it.
3. If you use another port, set the **workspace** setting below. Keep the URL a
   plain HTTP loopback origin, without credentials, paths, query or fragment:

   ```json
   { "lookingGlass.serverUrl": "http://127.0.0.1:8765" }
   ```

4. Run **Looking Glass: Connect to Looking Glass** in the Command Palette, or
   click **Looking Glass** in the status bar. Connection is always explicit;
   opening an arbitrary project does not connect it automatically.
5. Open the same file in Looking Glass. Already-dirty VS Code files are included
   in the initial snapshot. A second paired window is refused.

The extension briefly reads the workspace's existing `.looking-glass/token` to
bootstrap pairing, then uses an in-memory credential scoped to this workspace
and connection epoch. It expires after eight hours. No credential belongs in
settings, source control, a README or a URL. The existing browser token and
same-origin protections remain active. The backend must run threaded (the
standard `looking-glass serve` command does), so status/result posts can answer
long-poll requests and concurrent save guards.

## Daily use

- Saving either application writes the shared disk file through that application's
  normal save path. The other clean view observes the file change. Notifications
  never call Save, revert a VS Code document, commit or checkpoint.
- A dirty VS Code file makes that file read only in Looking Glass, including its
  Review proposal. A static, keyboard-focusable lock appears beside the filename
  and inactive tab, with **Read only — unsaved changes in VS Code** as its label
  and tooltip. Save/Approve are disabled. Selection, copying, navigation and
  discussion replies remain usable. Other files remain editable.
- Existing Looking Glass drafts and undo history remain in memory. Native VS Code
  Save, Auto Save, Save All, undo-to-clean or discard can release protection after
  a fresh snapshot. If disk changed under a retained Looking Glass draft, use the
  existing explicit comparison flow; nothing automatically merges or saves it.
- Backend guards also cover API/CLI saves, Review approval and explorer operations
  on a dirty file or its containing folder. Review autosave writes the database
  and can finish persisting previously queued edits.
- A lost or expired connection blocks coordinated disk writes. Known dirty locks
  remain, including across a Looking Glass backend restart. Other paired files
  may retain local draft editing while status is unknown. Reconnect explicitly;
  after a broken connection, an old pairing can take up to 15 seconds to expire.
- To return to standalone mode, use **Disconnect VS Code** in Looking Glass or
  **Looking Glass: Disconnect (End Dirty-file Protection)** in VS Code. Confirming
  explains that protection ends; it does not save, discard or replace drafts.
  Use the Looking Glass button when the VS Code window has already closed.
  Uninstalling/disabling the extension alone deliberately does not clear a
  persisted pairing. Disconnect before switching to a different project.

Coordination is cooperative, not an OS file lock. Native VS Code writes and
unpaired applications can overlap a Looking Glass save. Existing disk-version
checks and conflict handling remain necessary; no cross-application transaction
or global save veto is claimed. Unsaved Looking Glass drafts are not hot-exit
storage: preserve them before closing the browser, as in standalone operation.

## Language assistance

Saved, synchronized **Edit** buffers can request:

- Python definitions via F12 or Ctrl/Cmd+click, with existing local Jedi fallback.
- Explicit completion via Ctrl+Space. Choose a result with the existing popup
  controls/Enter or click it; Tab retains its existing indentation behavior.
- Hover over saved source text for sanitized provider Markdown.

Install and configure your own compatible VS Code language provider in the same
window, including its interpreter/workspace settings. For Python, an open-source
provider such as BasedPyright is an option. This extension neither installs nor
extracts Pylance or another analyzer. Check your provider's license; private use
is not permission to bypass its restrictions.

Typing in Looking Glass immediately returns to local suggestions and Jedi
navigation. Review always uses local support and never dispatches bridge provider
requests. Source, disk and VS Code hashes/versions are checked around each call;
late results after edits, navigation, locks or reconnects are discarded. UTF-16
VS Code positions are adapted separately from the existing Python code-point
endpoint. UTF-8 LF/CRLF/BOM are supported; other encodings fall back.

Completions only apply bounded, validated plain-text edits in the current Looking
Glass buffer, creating an unsaved draft. Command-bearing items, snippets,
additional edits and unsupported ranges are omitted. Definitions stay inside the
workspace, exclude dirty/unsynchronized destination buffers and retain destination
disk versions. Provider absence, failures or deadlines use local fallback.

## Cloud VS Code server setup

`code-server` is provided as a **cloud validation environment**. The design's
supported target remains local Microsoft VS Code. Cloud tests establish real
public extension-host/file-watcher behavior, not desktop Microsoft VS Code or
Pylance compatibility. Remote-SSH, WSL, Dev Containers, cross-machine copies and
production code-server compatibility remain outside the supported contract.

On Linux x86-64 or arm64, from the repository root:

```bash
vs_code_extension/scripts/cloud-server.sh install
vs_code_extension/scripts/cloud-server.sh start /absolute/path/to/project
```

This installs official code-server **4.106.3 / Code 1.106.3** under the user-owned
`/workspace/.tools/looking-glass-vscode/`, listens on **127.0.0.1:8080**, disables
telemetry/update checks and creates a random password in a mode-0600
`config.yaml`. Override the install/data location with `LG_VSCODE_CLOUD_DIR`.
The password can be read locally from that config; do not commit or paste it into
chat. Open the URL in a browser running inside the cloud environment, or use the
platform's authenticated port forwarding. Keep the listener on loopback.

Install the private VSIX into the server's isolated extension directory:

```bash
base="${LG_VSCODE_CLOUD_DIR:-/workspace/.tools/looking-glass-vscode}"
"$base/code-server/bin/code-server" \
  --user-data-dir "$base/data" --extensions-dir "$base/extensions" \
  --install-extension "$PWD/vs_code_extension/looking-glass-companion-0.1.0.vsix" --force
```

Reload its window after installation and pair explicitly with a Looking Glass
server running on the same machine/folder. Ctrl+C stops a foreground server.
Start it again with the same command. The script makes setup repeatable in a new
cloud instance; it does not change or publish the managed environment's reusable
configuration. Downloads need `github.com` and `release-assets.githubusercontent.com`;
builds use `registry.npmjs.org` and the normal Python package hosts. Keep inherited
proxy/CA settings. The cloud test driver is never installed in the normal server.

## Tests and validation

From the repository root:

```bash
npm --prefix vs_code_extension ci
npm --prefix vs_code_extension test
npm --prefix vs_code_extension run package
uv run pytest tests/test_vscode_bridge.py -q
npm test
uv run pytest -m 'not browser' -q
npm run build
uv build
```

Native integration installs the **packaged VSIX** and an isolated test driver into
a disposable code-server profile, launches Chromium and executes tests inside a
real extension host. Production workspaces, profiles and providers are untouched:

```bash
LG_CODE_SERVER=/workspace/.tools/looking-glass-vscode/code-server/bin/code-server \
  uv run python vs_code_extension/test/run_host.py
```

The runner uses `/usr/bin/chromium` by default; override `LOOKING_GLASS_BROWSER`
with a Chromium executable path. To also test an installed BasedPyright provider,
set `LG_PYTHON_VSIX=/absolute/path/to/vscode-pyright.vsix` when invoking the runner.
It installs that local VSIX only in the disposable test profile.

Browser tests include both engines in the ordinary sharded browser collection:

```bash
uv run playwright install chromium firefox
LOOKING_GLASS_BROWSER=installed uv run pytest tests/test_vscode_bridge_browser.py -q
# Use the system Chromium when browser downloads are restricted:
LOOKING_GLASS_BROWSER=/usr/bin/chromium uv run pytest tests/test_vscode_bridge_browser.py -k chromium -q
```

Verified in this cloud environment: real code-server extension-host pairing and
already-dirty snapshots, second-pair refusal, native save/discard, native watcher
reload after an atomic Looking Glass save, provider forwarding and unsafe-item
filtering, zero Review requests, an installed built-in JavaScript language service,
save-participant final bytes with no echoed save, Save All, Auto Save and stale
provider rejection after a native edit. Controlled Python providers exercise the
public registration/command APIs; they do **not** establish installed Python-provider
compatibility. BasedPyright's official VSIX download repeatedly returned HTTP 504,
so that optional case remains pending. Desktop Microsoft VS Code, native failed-save
and hot-exit/restart journeys also still need verification there.

Backend tests cover scopes/origins, persistent dirty locks, unknown/expired status,
reordered/duplicate snapshots, folder guards, request budgets/timeouts, Unicode/BOM,
provider eligibility and stale results. Chromium journeys cover themed/narrow
quiet locks, editing/paste/undo blocking, retained drafts/history, other tabs,
Review, explicit disconnect, conflicts, accepted completions and sanitized hover.
Firefox downloads were attempted but cloud policy denied `cdn.playwright.dev`
and `playwright.download.prss.microsoft.com` (HTTP 403); Firefox remains pending.

## Protocol and limits

`looking_glass/vscode_bridge.py` owns the workspace session. `/api/bridge/pair`,
`status`, `disconnect` and `provider` retain normal local API authentication.
`/api/bridge/session/poll`, `snapshot` and `result` require the scoped credential
and epoch. Long polling carries state/provider requests and saved-file hints.
Snapshots contain relative paths, dirty flags, versions and hashes, never document
bodies. Every snapshot is complete for open paired documents; a sequence gap is
therefore itself resynchronized. Older/duplicate snapshots cannot overwrite state.

Limits: 512 open paired documents, 16 pending backend requests, 32 queued messages,
4 outstanding native provider calls, a 3-second backend deadline, a 2.5-second
provider response deadline, 5-second poll waits, 15-second liveness and an 8-hour
credential. Native provider commands have no public cancellation hook; timed-out
results are ignored and the four-call budget remains occupied until calls finish.
Hash caching keys include the document version and file fingerprint. The transport
caps request/response bytes at 8 MiB; application text-file limits still apply.

If paired files remain blocked, check that Looking Glass is running, both roots
and ports match, the VS Code workspace is trusted and only one window is paired.
After restarting either application, run Connect again. Use explicit Disconnect
to end stale protection; do not delete metadata or overwrite a dirty buffer to
make a status indicator disappear.
