import os
import pytest


@pytest.fixture(autouse=True)
def isolated_project_registry(tmp_path, monkeypatch):
    """Tests and their child servers must never change the user's registry."""
    monkeypatch.setenv('LOOKING_GLASS_CONFIG_DIR', str(tmp_path/'user-config'))


@pytest.fixture(scope='session')
def browser_pool():
    """Reuse processes only; each test still gets its own context and workspace."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browsers = {}

        def get_browser(engine, *, args=None):
            args = args if args is not None else ['--no-sandbox'] if engine == 'chromium' else []
            key = (engine, tuple(args))
            if key not in browsers:
                executable = os.environ['LOOKING_GLASS_BROWSER']
                browsers[key] = getattr(playwright, engine).launch(
                    executable_path=None if engine != 'chromium' or executable == 'installed' else executable,
                    headless=not bool(os.environ.get('LOOKING_GLASS_HEADED')),
                    args=args,
                )
            return browsers[key]

        yield get_browser
        for browser in browsers.values():
            browser.close()


def pytest_addoption(parser):
    parser.addoption('--browser-shard', metavar='INDEX/TOTAL',
                     help='Run one zero-based shard of browser tests (all cases remain covered).')


def pytest_collection_modifyitems(config, items):
    shard = config.getoption('--browser-shard')
    if shard is None:
        return
    try:
        index, total = map(int, shard.split('/'))
        if not 0 <= index < total:
            raise ValueError
    except ValueError:
        raise pytest.UsageError('--browser-shard must be INDEX/TOTAL with 0 <= INDEX < TOTAL')
    # Sort IDs, independent of collection order and pytest's other deselections.
    browser_items = sorted((item for item in items if item.get_closest_marker('browser')),
                           key=lambda item: item.nodeid)
    chosen = set(browser_items[index::total])
    deselected = [item for item in items if item.get_closest_marker('browser') and item not in chosen]
    items[:] = [item for item in items if item not in deselected]
    config.hook.pytest_deselected(items=deselected)
