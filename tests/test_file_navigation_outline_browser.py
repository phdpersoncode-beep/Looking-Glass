"""File visits and the Python outline preserve the active document's state."""
import os
import re

import pytest
from test_requested_features import workspace_page, open_file
from test_spotlight_navigation_browser import settle

pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_file_arrows_dropdown_and_clear_preserve_drafts_and_scroll(workspace_page):
    from playwright.sync_api import expect
    root, page, url, _ = workspace_page
    original = '\n'.join(f'Reading line {i}' for i in range(250))
    (root/'a.txt').write_text(original)
    for name in ['b.txt', 'c.txt']:
        (root/name).write_text(name)
    page.goto(url); open_file(page, 'a.txt')
    back = page.get_by_role('button', name='Back to previous file')
    forward = page.get_by_role('button', name='Forward to next file')
    expect(back).to_be_disabled(); expect(forward).to_be_disabled()
    page.locator('.cm-content').click(); page.keyboard.press('Control+End'); page.keyboard.insert_text('\nDraft tail')
    page.keyboard.press('Control+Home'); settle(page)
    page.locator('.cm-scroller').evaluate('el=>el.scrollTop=700'); settle(page)
    before = page.locator('.cm-scroller').evaluate('el=>el.scrollTop')
    open_file(page, 'b.txt'); page.keyboard.press('Alt+ArrowLeft')
    expect(page.locator('#document-name')).to_have_text('a.txt'); settle(page)
    assert abs(page.locator('.cm-scroller').evaluate('el=>el.scrollTop')-before) < 2
    expect(page.locator('#dirty')).to_contain_text('Unsaved')
    page.keyboard.press('Alt+ArrowRight'); expect(page.locator('#document-name')).to_have_text('b.txt')
    back.click(); expect(page.locator('#document-name')).to_have_text('a.txt')
    open_file(page, 'c.txt'); expect(forward).to_be_disabled()
    page.locator('#file-history summary').click()
    expect(page.locator('#file-history nav button')).to_have_text(['c.txt', 'a.txt'])
    page.locator('#file-history nav button').filter(has_text='a.txt').click()
    expect(page.locator('#document-name')).to_have_text('a.txt')
    page.locator('.cm-content').click(); page.keyboard.press('Control+End')
    expect(page.locator('.cm-content')).to_contain_text('Draft tail')
    page.locator('#file-history summary').click()
    page.get_by_role('button', name='Clear history', exact=True).click()
    expect(page.locator('#file-history nav')).to_have_text('No recent files')
    expect(back).to_be_disabled(); expect(forward).to_be_disabled()
    expect(page.locator('#tabs .tab')).to_have_count(3)
    expect(page.locator('#dirty')).to_contain_text('Unsaved')
    assert (root/'a.txt').read_text() == original


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_history_handles_failed_and_rapid_navigation_context_and_reload(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    for name in ['a.txt', 'b.txt', 'c.txt', 'bad.txt']:
        (root/name).write_text('Reviewed passage in '+name)
    thread = ws.create_thread('c.txt', 0, 8, 'Comment', 'Reviewer', ws.read('c.txt')['version'])
    page.goto(url)
    for name in ['a.txt', 'b.txt', 'c.txt']:
        open_file(page, name)
    page.route('**/api/file?path=bad.txt', lambda route: route.fulfill(status=404, content_type='application/json', body='{"error":"Unavailable file"}'))
    page.locator('.file-entry[data-path="bad.txt"]').click()
    expect(page.locator('#notice')).to_contain_text('Unavailable file')
    expect(page.locator('#document-name')).to_have_text('c.txt')
    page.locator('#file-history summary').click()
    expect(page.locator('#file-history nav button')).to_have_text(['c.txt', 'b.txt', 'a.txt'])
    page.keyboard.press('Escape')
    page.locator('[data-history=back]').evaluate('el=>{el.click();el.click();}')
    expect(page.locator('#document-name')).to_have_text('a.txt')
    for name in ['b.txt', 'c.txt']:
        page.locator('[data-history=forward]').click(); expect(page.locator('#document-name')).to_have_text(name)
    page.locator(f'.thread[data-thread="{thread["id"]}"] [data-action=original]').click()
    expect(page.locator('.original-banner')).to_be_visible()
    page.locator('#file-history summary').click()
    expect(page.locator('#file-history nav button')).to_have_text(['c.txt', 'b.txt', 'a.txt'])
    page.keyboard.press('Escape')
    expect(page.locator('.original-banner')).to_be_visible()
    page.locator('#context-return').click()
    expect(page.locator('#document-name')).to_have_text('c.txt')
    page.reload(); expect(page.locator('#document-name')).to_have_text('c.txt')
    page.locator('#file-history summary').click()
    expect(page.locator('#file-history nav button')).to_have_text(['c.txt', 'b.txt', 'a.txt'])
    (root/'report.html').write_text('<p>Rendered report</p>')
    page.reload(); expect(page.locator('#document-name')).to_have_text('c.txt')
    open_file(page, 'report.html')
    page.frame_locator('#html-preview').locator('p').click()
    page.keyboard.press('Alt+ArrowLeft')
    expect(page.locator('#document-name')).to_have_text('c.txt')
    page.keyboard.press('Alt+ArrowRight')
    expect(page.locator('#document-name')).to_have_text('report.html')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_python_outline_jumps_tracks_edits_and_follows_review_mode(workspace_page):
    from playwright.sync_api import expect
    root, page, url, _ = workspace_page
    source = 'LIMIT = 5\nclass Part:\n    attribute = 2\n    def build(self):\n        local = 1\n        return local\n\n' + '# padding\n'*120 + 'def tail():\n    pass\n'
    (root/'part.py').write_text(source)
    page.goto(url); open_file(page, 'part.py')
    outline = page.locator('#code-outline')
    expect(outline).to_be_visible(); expect(outline).not_to_have_attribute('open', '')
    outline.locator('summary').click()
    expect(outline.locator('.outline-name')).to_have_text(['LIMIT', 'Part', 'build', 'tail'])
    outline.get_by_role('button', name=re.compile('^method build,')).click()
    expect(page.locator('.cm-activeLine')).to_contain_text('def build')
    expect(page.locator('.cm-activeLine')).to_be_in_viewport()
    outline.get_by_role('button', name=re.compile('^function tail,')).click()
    expect(page.locator('.cm-activeLine')).to_contain_text('def tail')
    assert page.locator('.cm-scroller').evaluate('el=>el.scrollTop') > 1000
    page.keyboard.press('Control+Home'); page.keyboard.insert_text('ADDED = 9\n')
    expect(outline.get_by_role('button', name=re.compile('^variable ADDED,'))).to_have_count(1)
    outline.get_by_role('button', name=re.compile('^function tail,')).click()
    expect(page.locator('.cm-activeLine')).to_contain_text('def tail')
    page.keyboard.press('Control+s'); expect(page.locator('#dirty')).to_have_text('')
    page.locator('#work-mode').click()
    expect(page.locator('#work-mode')).to_have_attribute('aria-checked', 'true')
    page.locator('.cm-content').click(); page.keyboard.press('Control+Home'); page.keyboard.insert_text('REVIEW_ONLY = 1\n')
    expect(outline.get_by_role('button', name=re.compile('^variable REVIEW_ONLY,'))).to_have_count(1)
    assert 'REVIEW_ONLY' not in (root/'part.py').read_text()
    page.locator('#work-mode').click()
    expect(outline.get_by_role('button', name=re.compile('^variable REVIEW_ONLY,'))).to_have_count(0)
    page.locator('#work-mode').click()
    expect(outline.get_by_role('button', name=re.compile('^variable REVIEW_ONLY,'))).to_have_count(1)


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_python_cursor_highlights_outline_and_pins_scrolled_definition(workspace_page):
    from playwright.sync_api import expect
    root, page, url, _ = workspace_page
    source = (
        'MODULE = 1\nclass Box:\n    volume = 0\n'
        '    async def pack(\n        self,\n        size: int,\n    ) -> None:\n'
        + ''.join(f'        volume_{i:02d} = size\n' for i in range(95))
        + '    def unpack(self): pass\n\nOUTSIDE = 2'
    )
    (root / 'box.py').write_text(source)
    (root / 'note.md').write_text('A note.')
    page.goto(url)
    page.set_viewport_size({'width': 1050, 'height': 720})
    open_file(page, 'box.py')
    outline = page.locator('#code-outline')
    outline.locator('summary').click()
    current = outline.locator('button[aria-current=location]')
    pin = page.locator('.python-definition-pin')
    method = outline.get_by_role('button', name=re.compile('^method pack,'))
    expect(current).to_have_count(0)
    expect(pin).to_be_hidden()
    outline.get_by_role('button', name=re.compile('^class Box,')).click()
    expect(current).to_have_attribute('data-kind', 'class')
    expect(pin).to_be_hidden()
    method.click()
    expect(current).to_have_attribute('data-kind', 'method')
    expect(current).to_have_text('ƒpack')
    expect(pin).to_be_hidden()
    row_color = current.evaluate('el => getComputedStyle(el.parentElement).backgroundColor')
    assert row_color != 'rgba(0, 0, 0, 0)'

    scroller = page.locator('.cm-scroller')
    page.keyboard.press('Control+Home')
    expect(current).to_have_count(0)
    scroller.evaluate('el => el.scrollTop = 620')
    expect(pin).to_be_hidden()
    body = page.locator('.cm-line').filter(has_text='volume_31')
    expect(body).to_be_in_viewport()
    body.click(position={'x': 120, 'y': 10})
    expect(current).to_have_text('ƒpack')
    expect(pin).to_have_text('async def pack( self, size: int, ) -> None:')
    expect(pin).to_be_visible()
    assert abs(pin.bounding_box()['y'] - scroller.bounding_box()['y']) <= 1
    assert pin.evaluate('el => getComputedStyle(el).whiteSpace') == 'nowrap'

    # Keep the caret in the method while scrolling the editor independently.
    top = pin.bounding_box()['y']
    scroller.evaluate('el => el.scrollTop += 280')
    assert abs(pin.bounding_box()['y'] - top) <= 1
    expect(current).to_have_text('ƒpack')
    assert page.locator('.cm-content').evaluate('el => !el.contains(document.querySelector(".python-definition-pin"))')

    page.locator('#theme').click()
    expect(pin).to_be_visible()
    assert current.evaluate('el => getComputedStyle(el.parentElement).backgroundColor') != row_color
    fold = outline.get_by_role('button', name='Toggle Box outline')
    fold.click()
    expect(current).to_have_attribute('data-kind', 'class')
    expect(pin).to_be_visible()
    fold.click()
    expect(current).to_have_attribute('data-kind', 'method')
    pin.click()
    expect(page.locator('.cm-activeLine')).to_contain_text('async def pack(')
    expect(page.locator('.cm-content')).to_be_focused()
    expect(pin).to_be_hidden()

    page.keyboard.press('Control+Shift+ArrowRight')
    page.keyboard.insert_text('assemble')
    expect(current).to_have_text('ƒassemble')
    scroller.evaluate('el => el.scrollTop = 620')
    expect(pin).to_contain_text('async def assemble(')
    page.keyboard.press('Control+End')
    expect(page.locator('.cm-activeLine')).to_contain_text('OUTSIDE')
    expect(current).to_have_count(0)
    expect(pin).to_be_hidden()
    open_file(page, 'note.md')
    expect(outline).to_be_hidden()
    expect(pin).to_have_count(0)


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_outline_layout_keyboard_themes_and_file_scope(workspace_page):
    from playwright.sync_api import expect
    root, page, url, _ = workspace_page
    (root/'part.py').write_text('class Part:\n    def build(self): pass\n' +
                               ''.join(f'\ndef step_{i:02d}(): pass\n' for i in range(50)))
    (root/'note.md').write_text('# A note\n\nProse.')
    page.goto(url); open_file(page, 'part.py')
    outline = page.locator('#code-outline'); summary = outline.locator('summary')
    for theme, width in [('light', 1440), ('dark', 900)]:
        if page.locator('html').get_attribute('data-theme') != theme:
            page.locator('#theme').click()
        page.set_viewport_size({'width': width, 'height': 620})
        summary.focus(); page.keyboard.press('Enter')
        expect(outline.locator('nav')).to_be_visible(); settle(page)
        pane_box = page.locator('.reading-pane').bounding_box(); outline_box = outline.bounding_box()
        assert outline_box['x'] > pane_box['x']
        assert outline_box['x'] + outline_box['width'] <= pane_box['x'] + pane_box['width'] + 1
        scroll = outline.locator('nav')
        # Overlay and headless scrollbars may occupy no layout space.
        assert scroll.evaluate('el => el.offsetWidth - el.clientWidth') <= 12
        assert scroll.bounding_box()['y'] + scroll.bounding_box()['height'] <= outline_box['y'] + outline_box['height'] + 1
        scroll.hover()
        # Wheel input is asynchronous and browsers can cap the distance per event.
        for _ in range(10):
            top, remaining = scroll.evaluate('el => [el.scrollTop, el.scrollHeight - el.clientHeight - el.scrollTop]')
            if remaining <= 2:
                break
            page.mouse.wheel(0, 400)
            page.wait_for_function('([el, top]) => el.scrollTop > top',
                                   arg=[scroll.element_handle(), top], timeout=5000)
        last = outline.get_by_role('button', name=re.compile('^function step_49,'))
        expect(last).to_be_in_viewport()
        last.click()
        expect(page.locator('.cm-activeLine')).to_contain_text('def step_49')
        outline.get_by_role('button', name=re.compile('^class Part,')).focus()
        page.keyboard.press('Escape')
        expect(summary).to_be_focused()
        assert outline.bounding_box()['width'] <= 30
    summary.click(); open_file(page, 'note.md'); expect(outline).not_to_be_visible()
    expect(page.locator('#markdown-contents')).to_be_visible()
    open_file(page, 'part.py'); expect(outline.locator('nav')).to_be_visible()
    page.reload(); expect(page.locator('#document-name')).to_have_text('part.py')
    expect(outline.locator('nav')).to_be_visible()
