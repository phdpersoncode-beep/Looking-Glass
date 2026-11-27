"""Measure Looking Glass startup and reconnect on Linux with local Chromium."""
import argparse
from contextlib import contextmanager
import cProfile
import json
import os
from pathlib import Path
import platform
import pstats
import re
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

from startup_fixture import ACTIVE, TAB_PATHS, generate, workload_arguments

SCENARIOS = {
    'fresh': dict(),
    'file-1': dict(tabs=[ACTIVE]),
    'file-16': dict(tabs=TAB_PATHS),
    'all-threads': dict(tabs=[ACTIVE], scope='all'),
    'all-threads-collapsed': dict(tabs=[ACTIVE], scope='all', collapsed=True),
    'board': dict(tabs=['looking-glass://tasks']),
    'markers-cold': dict(tabs=[ACTIVE], markers=True),
    'markers-saved': dict(tabs=[ACTIVE], markers=True, saved=True),
    'network-reconnect': dict(tabs=[ACTIVE], scope='all', offline=True),
}
REPLY_CONTROL = 'all-threads-no-reply-forms'

READINESS = """expected => {
  const start = performance.now();
  const stamps = {};
  const longTasks = [];
  new PerformanceObserver(list => {
    for (const entry of list.getEntries()) longTasks.push([entry.startTime, entry.duration]);
  }).observe({type: 'longtask', buffered: true});
  const tests = {
    explorer: () => !!document.querySelector('#file-tree .file-entry'),
    editor: () => !!document.querySelector('#surface .cm-editor'),
    board: () => !!document.querySelector('#surface .task-lane') &&
      document.querySelectorAll('#surface .task-card').length === expected.board,
    discussions: () => document.querySelector('#threads')?.getAttribute('aria-busy') === 'false' &&
      document.querySelector('#thread-total')?.textContent.startsWith(expected.discussions + ' thread') &&
      (expected.discussions ? document.querySelector('#threads .thread') :
        document.querySelector('#threads .empty-discussions')?.textContent.startsWith('No discussions yet.')),
    markers: () => Number(document.querySelector('#marker-count')?.textContent) === expected.markers,
  };
  const pending = Object.keys(expected);
  const observer = new MutationObserver(check);
  observer.observe(document, {subtree: true, attributes: true, childList: true, characterData: true});
  function check() {
    for (const key of pending.slice()) {
      if (!tests[key]()) continue;
      pending.splice(pending.indexOf(key), 1);
      requestAnimationFrame(() => requestAnimationFrame(() => stamps[key] = performance.now()));
    }
    if (!pending.length) observer.disconnect();
  }
  window.startupProfile = {stamps, longTasks, start};
  check();
}"""

RESOURCE_TIMINGS = """() => ({
  fcp: performance.getEntriesByName('first-contentful-paint')[0]?.startTime ?? null,
  resources: performance.getEntriesByType('resource').map(e => ({
    path: new URL(e.name).pathname, query: new URL(e.name).search,
    start: e.startTime, end: e.responseEnd, ttfb: e.responseStart - e.requestStart,
    bytes: e.encodedBodySize, transfer: e.transferSize,
  })),
  ...window.startupProfile,
})"""


def linux_mem(pid):
    fields = {}
    for line in Path(f'/proc/{pid}/smaps_rollup').read_text().splitlines():
        key, _, value = line.partition(':')
        if key in ('Rss', 'Pss'):
            fields[key.lower() + '_kib'] = int(value.split()[0])
    for line in Path(f'/proc/{pid}/status').read_text().splitlines():
        if line.startswith('VmHWM:'):
            fields['peak_rss_kib'] = int(line.split()[1])
            break
    return fields


def serve(root, omit_reply_forms=False):
    from looking_glass.app import create_app
    from werkzeug.serving import WSGIRequestHandler, make_server

    class QuietHandler(WSGIRequestHandler):
        def log_request(self, *args):
            pass

    app = create_app(root)
    if omit_reply_forms:
        from jinja2 import ChoiceLoader, DictLoader

        loader = app.jinja_env.loader
        template = loader.get_source(app.jinja_env, 'threads.html')[0]
        template, removed = re.subn(r'<form class="reply-form">.*?</form>', '', template, flags=re.S)
        if removed != 1:
            raise RuntimeError('Expected one reply form in the thread template.')
        app.jinja_env.loader = ChoiceLoader([DictLoader({'threads.html': template}), loader])
    server = make_server('127.0.0.1', 0, app, threaded=True, request_handler=QuietHandler)
    print(server.server_port, flush=True)
    server.serve_forever()


@contextmanager
def server(root, app_dir, omit_reply_forms=False):
    start = time.perf_counter()
    with subprocess.Popen([sys.executable, '-c',
                           'from benchmark_startup import serve; import sys; serve(sys.argv[1], sys.argv[2]=="True")',
                           str(root), str(omit_reply_forms)], stdout=subprocess.PIPE, text=True, cwd=app_dir,
                          env={**os.environ, 'PYTHONPATH': os.pathsep.join(
                              (str(app_dir), str(Path(__file__).resolve().parent)))}) as process:
        try:
            port = int(process.stdout.readline())
            yield f'http://127.0.0.1:{port}', process.pid, (time.perf_counter() - start) * 1000
        finally:
            process.terminate()


def memory(browser_cdp, page_cdp, pid):
    info = browser_cdp.send('SystemInfo.getProcessInfo')['processInfo']
    renderer = []
    for process in info:
        if process['type'] == 'renderer':
            try:
                renderer.append(linux_mem(process['id']))
            except (FileNotFoundError, ProcessLookupError):
                pass  # Chromium can retire spare renderers between the two snapshots.
    metrics = {m['name']: m['value'] for m in page_cdp.send('Performance.getMetrics')['metrics']}
    cpu = {key: metrics[key] * 1000 for key in ('TaskDuration', 'ScriptDuration', 'LayoutDuration', 'RecalcStyleDuration')}
    return dict(server=linux_mem(pid), renderer_pss_kib=sum(p['pss_kib'] for p in renderer),
                renderer_processes=len(renderer), js_heap_bytes=metrics['JSHeapUsedSize'],
                largest_renderer_peak_rss_kib=max((p['peak_rss_kib'] for p in renderer), default=0),
                dom=page_cdp.send('Memory.getDOMCounters'), renderer_timing_ms=cpu)


def browser_run(chromium, executable, name, root, app_dir, workload, profile_path=None):
    omit_reply_forms = name == REPLY_CONTROL
    scenario = SCENARIOS['all-threads' if omit_reply_forms else name]
    cache = root / '.looking-glass/marker-tree.json'
    if name == 'markers-cold':
        cache.unlink(missing_ok=True)
    tabs = scenario.get('tabs', [])
    active = tabs[0] if tabs else None
    scope = scenario.get('scope', 'file')
    markers = scenario.get('markers', False)
    tasks = name == 'board'
    expected = dict(explorer=True, discussions=workload['threads'] if scope == 'all' else
                    workload['active_threads'] if active and not tasks else 0)
    if tasks:
        expected['board'] = workload['board_cards']
    elif active:
        expected['editor'] = True
    if markers:
        expected['markers'] = workload['markers']

    with server(root, app_dir, omit_reply_forms) as (url, pid, server_ms):
        initial_server_memory = linux_mem(pid)
        browser = chromium.launch(executable_path=executable, args=['--no-sandbox'])
        try:
            context = browser.new_context(viewport={'width': 1440, 'height': 960})
            page = context.new_page()
            responses, errors = [], []
            page.on('response', lambda response: responses.append((response.url.removeprefix(url), response.status)))
            page.on('pageerror', lambda error: errors.append(str(error)))
            if active:
                # Warm static assets and set the same preferences the app persists.
                # Start the measured navigation in a new page to release the priming document.
                page.goto(url, wait_until='load')
                page.wait_for_selector('#file-tree .file-entry', state='attached')
                page.wait_for_selector('#threads .empty-discussions', state='attached')
                page.evaluate("""({tabs, active, scope, markers, collapsed}) => {
                  const root = document.querySelector('.root-label').textContent;
                  localStorage.setItem('looking-glass-tabs:'+root, JSON.stringify({
                    active, tabs: tabs.map(path => ({path, mode: 'source'})),
                  }));
                  localStorage.setItem('looking-glass-thread-scope:'+root, scope);
                  localStorage.setItem('looking-glass-marker-tree:'+root, String(markers));
                  if (collapsed) localStorage.setItem('looking-glass-collapsed-threads:'+root,
                    JSON.stringify(Array.from({length: collapsed}, (_, i) => i + 1)));
                }""", dict(tabs=tabs, active=active, scope=scope, markers=markers,
                            collapsed=workload['threads'] if scenario.get('collapsed') else 0))
                page.close()
                page = context.new_page()
                page.on('response', lambda response: responses.append((response.url.removeprefix(url), response.status)))
                page.on('pageerror', lambda error: errors.append(str(error)))
            responses.clear()
            page.add_init_script(f'({READINESS})({json.dumps(expected)})')
            browser_cdp = browser.new_browser_cdp_session()
            page_cdp = context.new_cdp_session(page)
            page_cdp.send('Performance.enable')
            if profile_path:
                page_cdp.send('Profiler.enable')
                page_cdp.send('Profiler.start')
            page.goto(url, wait_until='commit')
            page.wait_for_function('keys => keys.every(key => key in window.startupProfile?.stamps)',
                                   arg=list(expected), timeout=120000)
            if markers:
                page.wait_for_function("""() => performance.getEntriesByType('resource').some(
                    e => new URL(e.name).pathname === '/api/marker-tree' && !e.name.includes('cached=1'))""")
            if profile_path:
                profile_path.write_text(json.dumps(page_cdp.send('Profiler.stop')['profile']), encoding='utf-8')
            ready = page.evaluate(RESOURCE_TIMINGS)
            result = dict(server_start_ms=server_ms, server_initial=initial_server_memory, ready=ready,
                          memory=memory(browser_cdp, page_cdp, pid), responses=list(responses))
            result['mounted_reply_forms'] = page.locator('#threads .reply-form').count()
            if scenario.get('collapsed') and page.locator('#threads .thread.collapsed').count() != workload['threads']:
                raise RuntimeError('Saved discussion collapse state was not restored.')
            if omit_reply_forms and result['mounted_reply_forms']:
                raise RuntimeError('Discussion reply forms were mounted in the control.')
            if name == 'all-threads':
                # Two conditional discussion polls and their browser work.
                page.wait_for_function("""() => performance.getEntriesByType('resource').filter(
                    e => new URL(e.name).pathname === '/api/discussions').length >= 3 &&
                    document.querySelector('#threads').getAttribute('aria-busy') === 'false'""", timeout=20000)
                result['after_polls'] = page.evaluate(RESOURCE_TIMINGS)
                result['after_polls_memory'] = memory(browser_cdp, page_cdp, pid)
            if scenario.get('offline'):
                with page.expect_event('requestfailed', predicate=lambda r: '/api/discussions?' in r.url, timeout=12000):
                    context.set_offline(True)
                online = page.evaluate('performance.now()')
                with page.expect_response(lambda r: '/api/discussions?' in r.url and r.status == 304,
                                          timeout=12000):
                    context.set_offline(False)
                page.wait_for_function("""start => performance.getEntriesByType('resource').some(
                    e => new URL(e.name).pathname === '/api/discussions' && e.startTime >= start) &&
                    document.querySelector('#threads').getAttribute('aria-busy') === 'false'""", arg=online)
                page.evaluate('() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)))')
                result['network'] = dict(online=online, **page.evaluate(RESOURCE_TIMINGS))
                result['network_memory'] = memory(browser_cdp, page_cdp, pid)
            result['responses'] = responses
            if errors:
                raise RuntimeError(f'{name}: {errors}')
            return result
        finally:
            browser.close()


def backend(root, app_dir, runs, marker_available):
    sys.path.insert(0, str(app_dir))
    from looking_glass.app import create_app
    from looking_glass.revisions import Revisions

    app = create_app(root)
    ws = app.extensions['workspace']
    client = app.test_client()
    headers = {'X-Looking-Glass-Token': ws.token}

    def call(route, extra=None, status=200):
        response = client.get(route, headers={**headers, **(extra or {})})
        if response.status_code != status:
            raise RuntimeError(f'{route}: expected {status}, got {response.status_code}')
        return response

    def case(route, extra=None, status=200):
        samples = []
        for _ in range(runs):
            start = time.perf_counter()
            response = call(route, extra, status)
            samples.append((time.perf_counter() - start) * 1000)
        return dict(ms=samples, bytes=len(response.data), status=status)

    def conditional(route):
        return case(route, {'If-None-Match': call(route).headers['ETag']}, 304)

    def profile(route, extra=None, status=200):
        profiler = cProfile.Profile()
        profiler.runcall(call, route, extra, status)
        functions = {}
        for (file, line, name), (_, calls, own, cumulative, _) in pstats.Stats(profiler).stats.items():
            if file.startswith(('~', '<')) or (own < .001 and cumulative < .010):
                continue
            functions[f'{Path(file).name}:{line}:{name}'] = dict(
                calls=calls, own_ms=own * 1000, cumulative_ms=cumulative * 1000)
        return dict(sorted(functions.items(), key=lambda pair: -pair[1]['cumulative_ms'])[:45])

    all_threads = f'/api/discussions?path={ACTIVE}&scope=all'
    file_threads = f'/api/discussions?path={ACTIVE}&scope=file'
    files = '/fragments/files'
    tasks = '/api/tasks'
    result = {'explorer': case(files), 'explorer_304': conditional(files),
              'discussion_index': case('/api/thread-index'), 'file_discussions': case(file_threads),
              'all_discussions': case(all_threads), 'all_discussions_304': conditional(all_threads),
              'tasks': case(tasks), 'tasks_304': case(tasks + '?revision=1', status=304)}
    with patch.object(Revisions, 'explorer_status', return_value={}):
        result['explorer_without_git'] = case(files)
    import looking_glass.app as app_module

    render = app_module.render_template
    with patch.object(app_module, 'render_template',
                      side_effect=lambda template, **data: '' if template == 'threads.html' else render(template, **data)):
        result['all_discussions_without_html'] = case(all_threads)
    result['html_bytes'] = len(call(all_threads).get_json()['html'].encode())
    if marker_available:
        # Each cold run uses a new app and starts without the saved marker index.
        # The OS page cache is left in its normal state.
        cold, restored = [], []
        marker = '/api/marker-tree'
        for _ in range(runs):
            (root / '.looking-glass/marker-tree.json').unlink(missing_ok=True)
            client = create_app(root).test_client()
            cold.append(case_once(call, marker))
            client = create_app(root).test_client()
            restored.append(case_once(call, marker + '?cached=1'))
        result['marker_cold'] = dict(ms=[ms for ms, _ in cold], bytes=len(cold[-1][1].data), status=200)
        result['marker_disk_snapshot'] = dict(ms=[ms for ms, _ in restored], bytes=len(restored[-1][1].data), status=200)
        result['marker_304'] = conditional(marker)
    result['profiles'] = dict(all_discussions=profile(all_threads),
                              all_discussions_304=profile(all_threads, {'If-None-Match': call(all_threads).headers['ETag']}, 304),
                              tasks=profile(tasks), explorer=profile(files))
    if marker_available:
        (root / '.looking-glass/marker-tree.json').unlink()
        client = create_app(root).test_client()
        result['profiles']['marker_cold'] = profile('/api/marker-tree')
    return result


def case_once(call, route):
    start = time.perf_counter()
    response = call(route)
    return (time.perf_counter() - start) * 1000, response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    workload_arguments(parser)
    parser.add_argument('--runs', type=int, default=5)
    parser.add_argument('--chromium', default='/usr/bin/chromium',
                        help='Chromium executable, or "installed" for the Playwright-managed browser.')
    parser.add_argument('--app-dir', type=Path, default=Path(__file__).resolve().parents[1],
                        help='Checkout whose server and bundled assets to measure.')
    parser.add_argument('--scenario', action='append', choices=(*SCENARIOS, REPLY_CONTROL),
                        help='Repeat to select browser runs. Explicitly select the reply-form control to run it.')
    parser.add_argument('--backend-only', action='store_true')
    parser.add_argument('--browser-only', action='store_true')
    parser.add_argument('--cpu-profile-dir', type=Path,
                        help='Write per-navigation Chromium .cpuprofile files for a separate diagnostic run.')
    args = parser.parse_args()
    if args.runs < 1 or min(args.files, args.cards, args.threads) < 1:
        parser.error('Runs and fixture counts must be positive.')
    if args.files > 2500:
        parser.error('Use at most 2,500 marker files to stay within the marker result cap.')
    if args.backend_only and args.browser_only:
        parser.error('Choose at most one of --backend-only and --browser-only.')
    if args.cpu_profile_dir:
        args.cpu_profile_dir.mkdir(parents=True, exist_ok=True)
    app_dir = args.app_dir.resolve()
    marker_available = (app_dir / 'looking_glass/marker_tree.py').is_file()
    names = args.scenario or [name for name in SCENARIOS if marker_available or not name.startswith('markers-')]
    if not marker_available and any(name.startswith('markers-') for name in names):
        parser.error('The selected checkout does not contain Marker Tree.')
    if REPLY_CONTROL in names and '<form class="reply-form">' not in (
            app_dir / 'looking_glass/templates/threads.html').read_text(encoding='utf-8'):
        parser.error('Run the reply-form control against a checkout with eager reply forms.')

    result = dict(commit=subprocess.check_output(['git', '-C', str(app_dir), 'rev-parse', 'HEAD'], text=True).strip(),
                  python=platform.python_version(), kernel=platform.release(), browser={}, backend={})
    with tempfile.TemporaryDirectory(prefix='looking-glass-profile-') as temporary:
        root = Path(temporary) / 'workspace'
        result['workload'] = workload = generate(root, args.files, args.cards, args.threads)
        if not args.backend_only:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                executable = None if args.chromium == 'installed' else args.chromium
                browser_binary = executable or playwright.chromium.executable_path
                result['chromium'] = subprocess.check_output([browser_binary, '--version'], text=True).strip()
                for name in names:
                    if SCENARIOS.get(name, {}).get('saved') and not (root / '.looking-glass/marker-tree.json').exists():
                        from urllib.request import Request, urlopen

                        with server(root, app_dir) as (url, _, _):
                            token = (root / '.looking-glass/token').read_text().strip()
                            with urlopen(Request(url + '/api/marker-tree', headers={'X-Looking-Glass-Token': token})) as response:
                                if json.load(response)['count'] != workload['markers']:
                                    raise RuntimeError('Unexpected marker fixture count.')
                    samples = result['browser'][name] = []
                    for run in range(args.runs):
                        print(f'{name} {run + 1}/{args.runs}', file=sys.stderr, flush=True)
                        profile_path = args.cpu_profile_dir / f'{name}-{run + 1}.cpuprofile' if args.cpu_profile_dir else None
                        samples.append(browser_run(playwright.chromium, executable, name, root, app_dir, workload, profile_path))
        if not args.browser_only:
            print('Backend probes', file=sys.stderr, flush=True)
            # Separate process keeps imports pinned to the checkout under test.
            raw = subprocess.check_output([
                sys.executable, '-c',
                'from benchmark_startup import backend; import json,sys; from pathlib import Path; '
                'print(json.dumps(backend(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), sys.argv[4]=="True")))',
                str(root), str(app_dir), str(args.runs), str(marker_available)],
                cwd=app_dir, env={**os.environ, 'PYTHONPATH': os.pathsep.join(
                    (str(app_dir), str(Path(__file__).resolve().parent)))}, text=True)
            result['backend'] = json.loads(raw)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
