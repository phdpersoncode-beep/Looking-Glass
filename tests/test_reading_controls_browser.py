"""Quiet document controls operate on the displayed surface and retain drafts."""
import os
from pathlib import Path

import pytest
from test_requested_features import workspace_page, open_file
from test_spotlight_navigation_browser import settle

pytestmark = [pytest.mark.browser, pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('suffix', ['html', 'htm', 'jsonl'])
def test_oversized_html_download_does_not_open_or_render(workspace_page, suffix):
    from playwright.sync_api import expect
    from looking_glass.workspace import MAX_TEXT
    root, page, url, _ = workspace_page
    name = f'large report.{suffix}'
    raw = b'<p>\xc3\xbc</p>\r\n' + b' ' * MAX_TEXT
    (root/name).write_bytes(raw)
    requests = []
    page.on('request', lambda request: requests.append(request.url))
    page.goto(url); open_file(page, name)
    expect(page.locator('.file-size-warning')).to_be_visible()
    expect(page.locator('#download-file')).to_be_visible()
    # A native download must work even when renderer-side buffering is disabled.
    page.evaluate('''()=>{
      Response.prototype.blob=()=>{throw new Error('Do not buffer oversized downloads');};
      URL.createObjectURL=()=>{throw new Error('Do not retain oversized downloads');};
    }''')
    with page.expect_download() as downloaded:
        page.locator('#download-file').click()
    assert downloaded.value.suggested_filename == name
    assert Path(downloaded.value.path()).read_bytes() == raw
    assert '/download/' in downloaded.value.url and not downloaded.value.url.startswith('blob:')
    assert not any('/api/file?' in request or '/api/preview' in request for request in requests)
    expect(page.locator('#html-preview')).to_have_count(0)


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('mode', ['live', 'source', 'preview', 'review', 'html', 'jsonl', 'original'])
def test_go_to_top_preserves_document_and_other_panes(workspace_page, mode):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    text = '# Long document\n\n' + ''.join(f'Paragraph {i:03}.\n\n' for i in range(180))
    name = 'note.md'
    if mode == 'html':
        name = 'report.html'; text = '<p>Top</p><div style="height:5000px"></div><p>Bottom</p>'
    elif mode == 'jsonl':
        name = 'rows.jsonl'; text = '\n'.join('{"row":' + str(i) + '}' for i in range(180))
    (root/name).write_text(text)
    thread = ws.create_thread(name, 0, min(8, len(text)), 'Review the start', 'Reviewer', ws.read(name)['version'])
    page.goto(url); open_file(page, name)
    if mode in ['live', 'source', 'preview']:
        page.locator('#mode').select_option(mode)
    if mode == 'review':
        page.locator('#work-mode').click()
        expect(page.locator('#approve-review')).to_be_visible()
        page.locator('.cm-content').click(); page.keyboard.press('Control+End'); page.keyboard.insert_text('Draft tail')
    if mode == 'original':
        page.locator(f'.thread[data-thread="{thread["id"]}"] [data-action=original]').click()
        expect(page.locator('.original-reading')).to_be_visible()
    if mode == 'html':
        scroller = page.frame_locator('#html-preview').locator('body')
        expect(scroller).to_be_visible()
        scroller.evaluate('()=>window.scrollTo({top:4000,behavior:"instant"})')
        assert scroller.evaluate('()=>window.scrollY') > 1000
    else:
        selector = '.original-reading' if mode == 'original' else '.jsonl-raw' if mode == 'jsonl' else '#surface' if mode == 'preview' else '.cm-scroller'
        scroller = page.locator(selector)
        expect(scroller).to_be_visible(); settle(page)
        scroller.evaluate('el=>el.scrollTop=el.scrollHeight')
        assert scroller.evaluate('el=>el.scrollTop') > 1000
    sidebar = page.locator('.discussion-content')
    before = sidebar.evaluate('el=>el.scrollTop')
    page.locator('#go-to-top').click()
    if mode == 'html':
        frame = next(frame for frame in page.frames if '/preview/' in frame.url)
        frame.wait_for_function('window.scrollY<2')
        assert scroller.evaluate('()=>window.scrollY') < 2
    else:
        page.wait_for_function('(selector)=>document.querySelector(selector).scrollTop<2', arg=selector)
    assert abs(sidebar.evaluate('el=>el.scrollTop') - before) < 2
    assert (root/name).read_text() == text
    if mode == 'review':
        page.locator('.cm-content').click(); page.keyboard.press('Control+End')
        expect(page.locator('.cm-content')).to_contain_text('Draft tail')
        page.locator('#go-to-top').click(); settle(page)
        page.locator('#approve-review').click()
        expect(page.locator('#review-approve-dialog')).to_be_visible()
        page.locator('#review-approve-dialog [data-close]').click()
        assert (root/name).read_text() == text


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_copy_path_tracks_current_file_and_layout_controls_do_not_overlap(workspace_page):
    from playwright.sync_api import expect
    root, page, url, _ = workspace_page
    (root/'first file.md').write_text('First document')
    (root/'second.html').write_text('<p>Second document</p>')
    page.add_init_script('Object.defineProperty(navigator, "clipboard", {value: {writeText: async text=>{window.copiedPath=text;}}})')
    page.goto(url)
    expect(page.locator('#copy-filepath')).not_to_be_visible()
    for name in ['first file.md', 'second.html', 'first file.md']:
        open_file(page, name); page.locator('#copy-filepath').click()
        page.wait_for_function('name=>window.copiedPath===name', arg=name)
    page.locator('#work-mode').click()
    for width in [1440, 900]:
        page.set_viewport_size({'width': width, 'height': 800})
        for _ in range(2):
            page.locator('#theme').click(); settle(page)
            top = page.locator('#go-to-top').bounding_box()
            approve = page.locator('#approve-review').bounding_box()
            pane = page.locator('.reading-pane').bounding_box()
            assert approve['x'] + approve['width'] + 4 <= top['x']
            assert top['x'] + top['width'] <= pane['x'] + pane['width']
            assert top['y'] + top['height'] < pane['y'] + pane['height']
