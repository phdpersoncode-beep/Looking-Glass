"""References, literal intervals and quiet discussion controls work together."""
import os

import pytest
from playwright.sync_api import expect
from test_requested_features import workspace_page, open_file
from test_spotlight_navigation_browser import settle

pytestmark = [pytest.mark.browser, pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('mode', ['live', 'preview', 'review'])
def test_interval_brackets_remain_literal_and_annotatable(workspace_page, mode):
    root, page, url, ws = workspace_page
    text = '# Intervals\n\nRange [0, 1] and [a,b] and [missing].\n\n' \
        '[Example](https://example.com) and [named][id].\n\n' \
        '| Interval | Value |\n| --- | --- |\n| [2, 3] | yes |\n\n[id]: https://example.com\n'
    (root/'note.md').write_text(text)
    start = text.index('[0, 1]')
    thread = ws.create_thread('note.md', start, start+6, 'Check interval', 'Reviewer', ws.read('note.md')['version'])
    page.goto(url); open_file(page, 'note.md')
    if mode == 'review':
        page.locator('#work-mode').click()
        expect(page.locator('#approve-review')).to_be_visible()
    else:
        page.locator('#mode').select_option(mode)
    if mode != 'preview':
        expect(page.locator('.md-literal-brackets')).to_have_text(['[0, 1]', '[a,b]', '[missing]'])
        assert page.locator('.md-literal-brackets').first.evaluate('el=>getComputedStyle(el).textDecorationLine') == 'none'
        expect(page.locator('.md-link')).to_have_count(2)
    else:
        expect(page.locator('.markdown-preview a')).to_have_text(['Example', 'named'])
        expect(page.locator('.markdown-preview')).to_contain_text('Range [0, 1] and [a,b] and [missing].')
    expect(page.locator('#surface table')).to_contain_text('[2, 3]')
    expect(page.locator('#surface table a')).to_have_count(0)
    expect(page.locator('#surface [data-anchor]').first).to_have_text('[0, 1]')
    page.locator('#surface [data-anchor]').first.click()
    expect(page.locator('.thread.active')).to_have_attribute('data-thread', str(thread['id']))
    assert (root/'note.md').read_text() == text


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('target_kind', ['source', 'rendered', 'unattached'])
def test_thread_references_open_target_file_and_preserve_drafts(workspace_page, target_kind):
    root, page, url, ws = workspace_page
    name = 'target.html' if target_kind == 'rendered' else 'target.txt'
    text = '<p>Target passage</p>' if target_kind == 'rendered' else 'Target passage'
    (root/name).write_text(text)
    if target_kind == 'rendered':
        target = ws.create_rendered_thread(name, {'quote': 'Target passage', 'prefix': '', 'suffix': ''}, 'Target', 'Agent', ws.read(name)['version'])
    else:
        target = ws.create_thread(name, 0, len(text), 'Target', 'Agent', ws.read(name)['version'])
    if target_kind == 'unattached':
        (root/name).write_text('Replacement text')
        ws.read(name)
    ws.update_thread(target['id'], resolved=True)
    (root/'from.md').write_text('Source passage')
    body = f'See **#{target["id"]}**. Missing #999999.\n\n`#{target["id"]}`\n\n' \
        f'[External #{target["id"]}](https://example.com)\n\n```\n#{target["id"]}\n```\n\n' \
        '<a data-thread-reference="999999" href="https://example.com">ordinary link</a>'
    source = ws.create_thread('from.md', 0, 6, body, 'Reviewer', ws.read('from.md')['version'])
    page.add_init_script('Object.defineProperty(navigator,"clipboard",{value:{writeText:async text=>window.copiedReference=text}})')
    page.goto(url); open_file(page, 'from.md')
    if target_kind == 'unattached':
        page.locator('#show-unattached').uncheck()
    card = page.locator(f'.thread[data-thread="{source["id"]}"]')
    expect(card.locator('a[data-thread-reference]')).to_have_text([f'#{target["id"]}', '#999999'])
    expect(card.locator('a[href="https://example.com"]')).to_have_count(2)
    card.locator('[data-action=copy-thread]').click()
    page.wait_for_function('text=>window.copiedReference===text', arg=f'#{source["id"]}')
    expect(page.locator('#passage-spotlight')).not_to_be_visible()
    card.locator('[data-thread-reference="999999"]').click()
    expect(page.locator('#notice')).to_have_text('Thread #999999 is unavailable.')
    expect(page.locator('#document-name')).to_have_text('from.md')
    card.locator('[data-action=jump]').first.click()
    card.locator('textarea').fill('Keep this unsent reply')
    card.locator(f'[data-thread-reference="{target["id"]}"]').focus()
    page.keyboard.press('Enter')
    expect(page.locator('#document-name')).to_have_text(name)
    target_card = page.locator(f'.thread[data-thread="{target["id"]}"]')
    expect(target_card).to_be_visible(); expect(target_card).to_be_focused()
    expect(page.locator('#show-resolved')).not_to_be_checked()
    if target_kind == 'source':
        expect(page.locator('.resolved-passage')).to_be_in_viewport()
    elif target_kind == 'rendered':
        from test_html_annotations_browser import expect_highlights
        expect_highlights(page, ['Target passage'], 'looking-glass-resolved')
    else:
        expect(target_card.locator('.anchor-warning')).to_be_visible()
        expect(page.locator('.original-reading')).to_have_count(0)
    open_file(page, 'from.md')
    card.locator('[data-action=jump]').first.click()
    expect(card.locator('textarea')).to_have_value('Keep this unsent reply')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('filter_font', ['default', 'wide'])
def test_horizontal_filters_counts_search_and_copy_keep_thread_state(workspace_page, filter_font):
    root, page, url, ws = workspace_page
    (root/'note.txt').write_text('First passage.\n\nLost passage.')
    version = ws.read('note.txt')['version']
    first = ws.create_thread('note.txt', 0, 5, 'Attached', 'Reviewer', version)
    lost = ws.create_thread('note.txt', 16, 29, 'Unattached zebra', 'Reviewer', version)
    (root/'note.txt').write_text('First passage.')
    ws.read('note.txt')
    closed = ws.create_thread('note.txt', 0, 5, 'Closed', 'Reviewer', ws.read('note.txt')['version'])
    ws.update_thread(closed['id'], resolved=True)
    page.goto(url); open_file(page, 'note.txt')
    if filter_font == 'wide':
        # Wider system-font metrics must not push a checkbox onto another row.
        page.add_style_tag(content='.thread-filters label{font-family:monospace}')
    expect(page.locator('#thread-total')).to_have_text('3 threads · 2 open · 1 closed')
    lost_card = page.locator(f'.thread[data-thread="{lost["id"]}"]')
    expect(lost_card).to_be_visible()
    page.locator('#show-unattached').uncheck(); expect(lost_card).not_to_be_visible()
    page.locator('#thread-search').fill('zebra')
    expect(page.locator('#thread-search-status')).to_contain_text('0 matches')
    page.get_by_role('button', name='1 match in unattached threads', exact=True).click()
    expect(lost_card).to_be_visible()
    expect(page.locator('#thread-search-status')).to_contain_text('1 match')
    page.locator('#thread-search-clear').click()
    page.locator('#show-resolved').check()
    page.locator(f'.thread[data-thread="{closed["id"]}"] [data-action=resolve]').click()
    expect(page.locator('#thread-total')).to_have_text('3 threads · 3 open · 0 closed')
    for width in [1440, 900]:
        page.set_viewport_size({'width': width, 'height': 850})
        for theme in ['light', 'dark']:
            if page.locator('html').get_attribute('data-theme') != theme:
                page.locator('#theme').click()
            settle(page)
            boxes = page.locator('.thread-filters label').evaluate_all('els=>els.map(el=>({y:el.getBoundingClientRect().y,right:el.getBoundingClientRect().right}))')
            assert max(box['y'] for box in boxes)-min(box['y'] for box in boxes) < 2
            assert max(box['right'] for box in boxes) <= page.locator('#discussion-sidebar').bounding_box()['x']+page.locator('#discussion-sidebar').bounding_box()['width']
            inputs = page.locator('.thread-filters input').evaluate_all('els=>els.map(el=>el.getBoundingClientRect().y+el.getBoundingClientRect().height/2)')
            assert max(inputs)-min(inputs) < 2
        # Exercise the smallest supported sidebar through its keyboard control.
        page.locator('#discussion-resize').focus(); page.keyboard.press('Home')
        boxes = page.locator('.thread-filters input').evaluate_all('els=>els.map(el=>({y:el.getBoundingClientRect().y,right:el.getBoundingClientRect().right}))')
        assert max(box['y'] for box in boxes)-min(box['y'] for box in boxes) < 2
        sidebar = page.locator('#discussion-sidebar').bounding_box()
        assert max(box['right'] for box in boxes) <= sidebar['x']+sidebar['width']
    assert not ws.get_thread(first['id'])['resolved']


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_new_reference_or_file_navigation_supersedes_pending_reference(workspace_page):
    root, page, url, ws = workspace_page
    targets = []
    for name in ['a.txt', 'b.txt']:
        (root/name).write_text('Target')
        targets.append(ws.create_thread(name, 0, 6, 'Target', 'Agent', ws.read(name)['version']))
    (root/'from.md').write_text('Source')
    ws.create_thread('from.md', 0, 6, f'Compare #{targets[0]["id"]} and #{targets[1]["id"]}', 'Reviewer', ws.read('from.md')['version'])
    page.goto(url); open_file(page, 'from.md')
    held = []
    page.route(f'**/api/threads/{targets[0]["id"]}', lambda route: held.append(route))
    for navigate_file in [False, True]:
        page.locator(f'a[data-thread-reference="{targets[0]["id"]}"]').click()
        assert held
        if navigate_file:
            open_file(page, 'b.txt')
        else:
            page.locator(f'a[data-thread-reference="{targets[1]["id"]}"]').click()
            expect(page.locator('#document-name')).to_have_text('b.txt')
        with page.expect_response(lambda response: response.url.endswith(f'/api/threads/{targets[0]["id"]}')):
            held.pop().continue_()
        settle(page)
        expect(page.locator('#document-name')).to_have_text('b.txt')
        open_file(page, 'from.md')
