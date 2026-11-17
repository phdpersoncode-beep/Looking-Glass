"""A transferred database remains usable in the editor and review UI."""
import io
import os
import threading
from contextlib import closing

import pytest
from werkzeug.serving import make_server

from looking_glass import database
from looking_glass.app import create_app
from looking_glass.workspace import Workspace
from test_requested_features import open_file


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]


@pytest.mark.parametrize('engine', ['chromium', 'firefox'])
def test_restored_discussions_original_context_and_review_are_visible_after_reload(tmp_path, browser_pool, engine):
    from playwright.sync_api import expect

    source = tmp_path / 'machine-a'
    source.mkdir()
    original = '# Notes\n\nA unique passage.\n'
    (source / 'notes.md').write_text(original)
    ws = Workspace(source)
    file = ws.read('notes.md')
    start = original.index('A unique passage.')
    thread = ws.create_thread('notes.md', start, start + len('A unique passage.'),
                               'Transferred question', 'Human', file['version'])
    draft = ws.reviews.start('notes.md', file['version'])
    ws.reviews.update(draft['id'], draft['version'],
                       [dict(start=0, end=0, insert='Proposed opening\n')], 'Codex', 'agent')
    output = io.StringIO()
    database.dump(source, output)
    destination = tmp_path / 'machine-b'
    destination.mkdir()
    (destination / 'notes.md').write_bytes((source / 'notes.md').read_bytes())
    database.restore(destination, output.getvalue())
    # Start the receiving server only after offline restoration has completed.
    app = create_app(destination)
    server = make_server('127.0.0.1', 0, app, threaded=True)
    worker = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    worker.start()
    try:
        with closing(browser_pool(engine).new_context(viewport={'width': 1440, 'height': 960})) as context:
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}')
            open_file(page, 'notes.md')
            expect(page.locator('.thread')).to_contain_text('Transferred question')
            page.locator('#work-mode').click()
            expect(page.locator('#review-status')).to_have_text('Review saved')
            expect(page.locator('.review-agent')).to_contain_text('Proposed opening')
            page.locator('.original-context').click()
            expect(page.locator('.original-reading')).to_contain_text('A unique passage.')
            expect(page.locator('.original-reading')).not_to_contain_text('Proposed opening')
            page.keyboard.press('Escape')
            expect(page.locator('#document-name')).to_have_text('notes.md')
            page.reload()
            expect(page.locator('.thread')).to_contain_text('Transferred question')
            expect(page.locator('.review-agent')).to_contain_text('Proposed opening')
            assert not errors, errors
        received = app.extensions['workspace']
        assert received.token != ws.token
        assert received.origins.read(thread['id']) == ws.origins.read(thread['id'])
        assert (destination / 'notes.md').read_bytes() == (source / 'notes.md').read_bytes()
    finally:
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()
