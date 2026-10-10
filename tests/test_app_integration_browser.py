"""Whole-app journeys that cross tabs, modes, saves, comments and reloads."""
import os
import pytest
from test_requested_features import workspace_page, open_file

pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_edit_draft_survives_other_file_review_and_active_file_approval(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    (root / 'notes.md').write_text('# Notes\n\nOrdinary original.\n')
    (root / 'code.py').write_text('value = 1\n')
    page.goto(url)
    open_file(page, 'notes.md')
    page.locator('#mode').select_option('source')
    page.locator('.cm-content').click()
    page.keyboard.press('Control+End')
    page.keyboard.insert_text('Unsaved human work\n')
    expect(page.locator('#dirty')).to_contain_text('Unsaved')
    open_file(page, 'code.py')
    page.locator('#work-mode').select_option('review')
    expect(page.locator('#review-status')).to_have_text('Review saved')
    page.locator('.cm-content').click()
    page.keyboard.press('Control+End')
    page.keyboard.insert_text('extra = 2\n')
    expect(page.locator('.review-human')).to_contain_text('extra = 2')
    expect(page.locator('#review-status')).to_have_text('Review saved')
    draft = ws.reviews.read(ws.reviews.list()[0]['id'])
    ws.reviews.create_thread(draft['id'], draft['version'], 0, 5, 'Inspect value', 'Codex')
    expect(page.locator('.thread')).to_have_count(1)
    page.locator('#thread-search').fill('inspect')
    expect(page.locator('#thread-search-status')).to_contain_text('1 match')
    page.locator('#approve-review').click()
    expect(page.locator('#work-mode')).to_have_value('edit')
    expect(page.locator('.thread')).to_have_count(1)
    assert (root / 'code.py').read_text() == 'value = 1\nextra = 2\n'
    assert (root / 'notes.md').read_text() == '# Notes\n\nOrdinary original.\n'
    open_file(page, 'notes.md')
    expect(page.locator('.cm-content')).to_contain_text('Unsaved human work')
    expect(page.locator('#dirty')).to_contain_text('Unsaved')
    # Undo remains per document, even after another file's approval.
    page.locator('.cm-content').click()
    page.keyboard.press('Control+z')
    expect(page.locator('.cm-content')).not_to_contain_text('Unsaved human work')
    page.keyboard.press('Control+Shift+z')
    expect(page.locator('.cm-content')).to_contain_text('Unsaved human work')
    page.keyboard.press('Control+s')
    expect(page.locator('#dirty')).to_have_text('')
    page.reload()
    expect(page.locator('.cm-content')).to_contain_text('Unsaved human work')
    open_file(page, 'code.py')
    expect(page.locator('.cm-content')).to_contain_text('extra = 2')
    assert ws.reviews.list() == []


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('work', ['edit', 'review'])
def test_edited_comments_search_resolve_reopen_and_context_survive_reload(workspace_page, work):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    text = '# Report\n\nA unique passage.\n\n7. First\n8. Second\n\n| Item | Value |\n| --- | --- |\n| width | 12 |\n'
    (root / 'report.md').write_text(text)
    file = ws.read('report.md')
    start = text.index('A unique passage.')
    thread = ws.create_thread('report.md', start, start + len('A unique passage.'), 'Initial finding', 'Altay', file['version'])
    page.goto(url)
    open_file(page, 'report.md')
    if work == 'review':
        page.locator('#work-mode').select_option('review')
        expect(page.locator('#review-status')).to_have_text('Review saved')
    page.locator('.edit-comment').click()
    page.locator('#edit-comment-body').fill('Revised verifier finding')
    page.get_by_role('button', name='Save comment', exact=True).click()
    expect(page.locator('#edit-comment-dialog')).not_to_be_visible()
    page.locator('#thread-search').fill('verifer')
    expect(page.locator('#thread-search-status')).to_contain_text('1 match')
    expect(page.locator('.thread-search-match:visible mark')).to_have_text('verifier')
    page.locator('.thread-search-match:visible').click()
    expect(page.locator('#passage-spotlight')).to_be_visible()
    page.locator('.original-context').click()
    expect(page.locator('.original-reading table')).to_be_visible()
    expect(page.locator('.original-reading ol')).to_have_attribute('start', '7')
    page.keyboard.press('Escape')
    expect(page.locator('#document-name')).to_have_text('report.md')
    page.get_by_role('button', name='Resolve thread', exact=True).click()
    # Search scope follows resolution; faint marks remain in all text views.
    expect(page.locator('#thread-search-empty')).to_be_visible()
    for mode, host in [('source', '.cm-content'), ('live', '.cm-content'), ('preview', '.markdown-preview')]:
        page.locator('#mode').select_option(mode)
        mark = page.locator(host + ' .resolved-passage')
        expect(mark).to_have_text('A unique passage.')
        assert mark.evaluate('el=>getComputedStyle(el).backgroundColor') == 'rgba(0, 0, 0, 0)'
    page.locator('#show-resolved').check()
    expect(page.locator('#thread-search-status')).to_contain_text('1 match')
    page.get_by_role('button', name='Reopen thread', exact=True).click()
    expect(page.locator('.resolved-passage')).to_have_count(0)
    page.reload()
    expect(page.locator('.thread .comment-markdown')).to_contain_text('Revised verifier finding')
    assert not ws.get_thread(thread['id'])['resolved']
    assert ws.origins.read(thread['id'])['content'] == text
    assert (root / 'report.md').read_text() == text


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_reused_browser_keeps_storage_and_extra_pages_isolated(workspace_page, browser_pool):
    root, page, url, _ = workspace_page
    (root / 'note.txt').write_text('Isolation check.\n')
    page.goto(url)
    page.evaluate('localStorage.setItem("test-context-marker", "private")')
    page.context.add_cookies([dict(name='test-cookie', value='private', url=url)])
    engine = page.context.browser.browser_type.name
    browser = browser_pool(engine)
    other = browser.new_context()
    try:
        extra = other.new_page()
        extra.goto(url)
        assert extra.evaluate('localStorage.getItem("test-context-marker")') is None
        assert other.cookies() == []
        assert page.evaluate('localStorage.getItem("test-context-marker")') == 'private'
    finally:
        other.close()
    assert browser.contexts == [page.context]


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('hidden', [False, True])
@pytest.mark.parametrize('motion', ['instant', 'smooth'])
def test_html_highlight_keeps_position_before_mouse_focus(workspace_page, hidden, motion):
    from playwright.sync_api import expect
    from test_discussion_reading_browser import endpoint
    from test_spotlight_navigation_browser import settle
    root, page, url, ws = workspace_page
    text = '<div style="height:1800px"></div><p><strong>Target passage</strong></p><div style="height:1000px"></div>'
    (root / 'report.html').write_text(text)
    at = text.index('Target passage')
    ws.create_thread('report.html', at, at + len('Target passage'), 'Review', 'Altay', ws.read('report.html')['version'])
    page.goto(url)
    open_file(page, 'report.html')
    if hidden:
        page.locator('#discussions-toggle').click()
    target = page.frame_locator('#html-preview').locator('strong')
    target.scroll_into_view_if_needed()
    settle(page)
    target.evaluate('''(el,motion)=>{
      const r=el.getBoundingClientRect();window.scrollBy(0,r.top-120);
      // Native focus can nudge the passage; reports can also request smooth scrolling.
      el.addEventListener('mousedown',()=>{
        if(motion==='smooth')document.documentElement.style.scrollBehavior='smooth';
        window.scrollBy({top:motion==='smooth'?200:4,behavior:motion});
      },{once:true});
    }''',motion)
    point = endpoint(target, 2)
    bounds = page.locator('#html-preview').bounding_box()
    page.mouse.click(bounds['x'] + point['x'], bounds['y'] + point['y'])
    expect(page.locator('#passage-spotlight')).to_be_visible()
    settle(page)
    assert abs(endpoint(target, 2)['y'] - point['y']) < 2
    # The short position hold must release for ordinary wheel navigation.
    scroll = target.evaluate('()=>window.scrollY')
    page.mouse.wheel(0, -200)
    frame = next(frame for frame in page.frames if frame.url.startswith(url + '/preview/'))
    frame.wait_for_function('before=>window.scrollY<before', arg=scroll)
    assert (root / 'report.html').read_text() == text


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_jsonl_comparison_position_remains_stable_after_entry_changes(workspace_page):
    import json
    from playwright.sync_api import expect
    root, page, url, _ = workspace_page
    rows = [{f'field_{i:03}': f'{name} value {i}' for i in range(140)}
            for name in ['first', 'second', 'third']]
    text = '\n'.join(json.dumps(row) for row in rows) + '\n'
    (root / 'rows.jsonl').write_text(text)
    page.goto(url)
    open_file(page, 'rows.jsonl')
    scroller = page.locator('.jsonl-detail .cm-scroller')
    scroller.evaluate('el=>el.scrollTop=700')
    page.wait_for_function('()=>document.querySelector(".jsonl-detail .cm-scroller").scrollTop>=690')
    for index in (1, 2, 0):
        page.locator(f'.jsonl-row[data-row="{index}"]').click()
        expect(page.locator('.jsonl-detail .viewer-heading')).to_contain_text(f'ROW {index + 1} / 3')
        page.wait_for_function('()=>Math.abs(document.querySelector(".jsonl-detail .cm-scroller").scrollTop-700)<10')
        # A one-frame restoration must survive subsequent editor measurement.
        positions = scroller.evaluate('''el=>new Promise(resolve=>{
          const positions=[];let remaining=8;
          function frame(){positions.push(el.scrollTop);if(--remaining)requestAnimationFrame(frame);else resolve(positions)}
          requestAnimationFrame(frame);
        })''')
        assert all(abs(top - 700) < 10 for top in positions), positions
    scroller.hover()
    page.mouse.wheel(0, 250)
    page.wait_for_function('()=>document.querySelector(".jsonl-detail .cm-scroller").scrollTop>800')
    assert (root / 'rows.jsonl').read_text() == text
