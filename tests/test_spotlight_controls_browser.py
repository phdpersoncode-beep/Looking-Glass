"""Sidebar keyboard navigation and zen deletion use the full scoped queue."""
import os

import pytest
from test_requested_features import workspace_page, open_file, start_reply
from test_spotlight_navigation_browser import settle

pytestmark = [pytest.mark.browser, pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]


def discussions(root, ws):
    text = 'First passage.\n\n' + 'Context.\n\n'*70 + 'Middle passage.\n\n' + 'Context.\n\n'*70 + 'Last passage.\n'
    (root/'note.md').write_text(text)
    version = ws.read('note.md')['version']
    return [ws.create_thread('note.md', text.index(quote), text.index(quote)+len(quote), 'Queue discussion', 'Reviewer', version)
            for quote in ['First passage.', 'Middle passage.', 'Last passage.']]


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('modifier', ['Control', 'Meta'])
def test_resolve_shortcut_keeps_replies_and_passage_navigation(workspace_page, modifier):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    threads = discussions(root, ws)
    page.goto(url); open_file(page, 'note.md')
    first = page.locator(f'.thread[data-thread="{threads[0]["id"]}"]')
    first.locator('blockquote').click()
    expect(first).to_be_focused()
    resolve = first.get_by_role('button', name='Resolve thread', exact=True)
    expect(resolve).to_have_attribute('aria-keyshortcuts', 'Control+Enter Meta+Enter')
    shortcut = f'{modifier}+Enter'

    reply = start_reply(page, first)
    reply.fill('Confirmed in the latest draft.')
    reply.press(shortcut)
    expect(first.locator('.message').last).to_contain_text('Confirmed in the latest draft.')
    expect(first).to_have_attribute('data-resolved', 'false')
    expect(reply).to_be_focused()
    page.keyboard.press('Escape')
    expect(first).to_be_focused()

    patches = []
    page.on('request', lambda request: patches.append(request.url)
            if request.method == 'PATCH' and '/api/threads/' in request.url else None)
    pane = page.locator('.cm-scroller')
    before = pane.evaluate('el => el.scrollTop')
    page.keyboard.press(shortcut)
    expect(first).to_have_attribute('data-resolved', 'true')
    expect(first).to_be_focused()
    page.keyboard.press(shortcut)
    settle(page)
    assert patches == [f'{url}/api/threads/{threads[0]["id"]}']
    assert abs(pane.evaluate('el => el.scrollTop') - before) < 2
    expect(page.locator('#comment-dialog')).to_be_hidden()

    page.keyboard.press('ArrowRight')
    next_card = page.locator(f'.thread[data-thread="{threads[1]["id"]}"]')
    expect(next_card).to_be_focused()
    expect(page.locator('.focused-highlight')).to_have_text('Middle passage.')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_spotlight_arrows_keep_sidebar_focus_drafts_and_search_position(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    threads = discussions(root, ws)
    closed = ws.create_thread('note.md', 0, 5, 'Closed discussion', 'Reviewer', ws.read('note.md')['version'])
    ws.update_thread(closed['id'], resolved=True)
    page.goto(url); open_file(page, 'note.md')
    search = page.locator('#thread-search'); before = search.bounding_box()['y']
    expect(page.locator('#thread-total')).to_have_text('4 threads · 3 open · 1 closed')
    card = lambda i: page.locator(f'.thread[data-thread="{threads[i]["id"]}"]')
    card(0).locator('.comment-markdown p').click()
    expect(page.locator('#passage-spotlight')).to_be_visible()
    assert abs(search.bounding_box()['y'] - before) < 1
    field = start_reply(page, card(0)); field.fill('Unsent first reply')
    card(0).focus(); page.keyboard.press('ArrowRight')
    expect(card(1)).to_be_focused(); expect(card(1)).to_have_class('thread active')
    expect(page.locator('.focused-highlight')).to_have_text('Middle passage.')
    expect(page.locator('.focused-highlight')).to_be_in_viewport()
    page.keyboard.press('ArrowRight'); expect(card(2)).to_be_focused()
    page.keyboard.press('ArrowRight'); expect(card(0)).to_be_focused()
    expect(field).to_have_value('Unsent first reply')
    page.keyboard.press('ArrowLeft'); expect(card(2)).to_be_focused()
    page.keyboard.press('ArrowUp'); expect(search).to_be_focused()
    page.keyboard.press('ArrowLeft'); expect(search).to_be_focused()
    expect(card(2)).to_have_class('thread active')
    page.locator('#discussion-sidebar').focus(); page.keyboard.press('ArrowDown')
    last_field = card(2).locator('textarea'); expect(last_field).to_be_focused()
    last_field.fill('Two\nlines'); last_field.evaluate('el=>el.setSelectionRange(0,0)')
    page.keyboard.press('ArrowRight'); page.keyboard.press('ArrowDown')
    expect(last_field).to_be_focused(); expect(last_field).to_have_value('Two\nlines')
    expect(card(2)).to_have_class('thread active')
    # Sidebar resizing retains its own arrow-key contract.
    resize = page.locator('#discussion-resize'); resize.focus()
    width = int(resize.get_attribute('aria-valuenow'))
    page.keyboard.press('ArrowLeft'); expect(resize).to_have_attribute('aria-valuenow', str(width+10))
    expect(card(2)).to_have_class('thread active')
    page.keyboard.press('Escape'); expect(page.locator('#passage-spotlight')).not_to_be_visible()
    assert abs(search.bounding_box()['y'] - before) < 1
    # Search filters are the queue even after their result opens in spotlight.
    search.fill('#' + str(threads[1]['id'])); search.press('Enter')
    expect(card(1)).to_have_class('thread active')
    card(1).focus(); page.keyboard.press('ArrowRight')
    expect(card(1)).to_be_focused(); expect(page.locator('#passage-spotlight')).to_be_visible()
    assert abs(search.bounding_box()['y'] - before) < 1


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_discussion_search_stays_fixed_when_heading_reflows(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    discussions(root, ws)
    page.goto(url); open_file(page, 'note.md')
    expect(page.locator('#thread-total')).to_have_text('3 threads · 3 open · 0 closed')
    heading = page.locator('#discussion-sidebar>.panel-heading')
    # Font metrics differ across platforms. Place the label just beyond the
    # wrapping threshold so a 10px resize exercises both heading layouts.
    heading.evaluate("""header => {
        const label = header.firstElementChild, actions = header.lastElementChild;
        const style = getComputedStyle(header);
        const inner = header.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
        const labelWidth = inner - actions.getBoundingClientRect().width - parseFloat(style.columnGap) + 5;
        label.style.flex = `0 0 ${labelWidth}px`;
    }""")
    def rows():
        return heading.evaluate("""header => {
            const label = header.firstElementChild.getBoundingClientRect();
            const actions = header.lastElementChild.getBoundingClientRect();
            return {wrapped: label.top >= actions.bottom, inside: actions.right <= header.getBoundingClientRect().right};
        }""")
    assert rows()['wrapped'] and rows()['inside']
    search = page.locator('#thread-search'); before = search.bounding_box()['y']
    resize = page.locator('#discussion-resize'); width = int(resize.get_attribute('aria-valuenow'))
    resize.press('ArrowLeft')
    expect(resize).to_have_attribute('aria-valuenow', str(width + 10))
    assert not rows()['wrapped'] and rows()['inside']
    assert abs(search.bounding_box()['y'] - before) < 1
    resize.press('ArrowRight')
    expect(resize).to_have_attribute('aria-valuenow', str(width))
    assert rows()['wrapped'] and rows()['inside']
    assert abs(search.bounding_box()['y'] - before) < 1


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('control', ['reply', 'search', 'filtered-search'])
def test_escape_from_spotlight_fields_returns_to_current_thread_shortcuts(workspace_page, control):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    threads = discussions(root, ws)
    page.goto(url); open_file(page, 'note.md')
    search = page.locator('#thread-search')
    if control == 'filtered-search':
        page.locator('#theme').click()
        page.set_viewport_size({'width': 900, 'height': 960})
        search.fill('Queue')
        expect(page.locator('#thread-search-status')).to_contain_text('3 matches')
        page.locator(f'.thread[data-thread="{threads[1]["id"]}"] .thread-search-match').click()
    else:
        page.locator(f'.thread[data-thread="{threads[1]["id"]}"] .thread-heading [data-action=jump]').click()
    card = page.locator(f'.thread[data-thread="{threads[1]["id"]}"]')
    field = start_reply(page, card)
    field.fill('Unsent café reply')
    card.locator('.attach-files').set_input_files([
        {'name': 'notes.txt', 'mimeType': 'text/plain', 'buffer': b'Keep attachment'}])
    target = field if control == 'reply' else search
    target.focus()
    # Escape only changes keyboard focus: keep the same nodes and reading position.
    field.evaluate('el=>window.escapeReply=el')
    settle(page)
    pane = page.locator('.cm-scroller')
    scroll = pane.evaluate('el=>el.scrollTop')
    sidebar = page.locator('.discussion-content')
    side_scroll = sidebar.evaluate('el=>el.scrollTop')
    query = search.input_value()
    target.press('Escape')
    expect(card).to_be_focused()
    expect(card).to_have_class('thread active')
    expect(page.locator('#passage-spotlight')).to_be_visible()
    expect(field).to_have_value('Unsent café reply')
    expect(card.locator('.pending-files')).to_contain_text('notes.txt')
    expect(search).to_have_value(query)
    assert field.evaluate('el=>el===window.escapeReply')
    assert abs(pane.evaluate('el=>el.scrollTop') - scroll) < 2
    assert abs(sidebar.evaluate('el=>el.scrollTop') - side_scroll) < 2
    # All four shortcuts work immediately, with no click or manual card focus.
    page.keyboard.press('ArrowUp'); expect(search).to_be_focused()
    search.press('Escape'); expect(card).to_be_focused()
    page.keyboard.press('ArrowDown'); expect(field).to_be_focused()
    field.press('Escape'); expect(card).to_be_focused()
    page.keyboard.press('ArrowRight')
    expect(page.locator('.thread.active')).to_have_attribute('data-thread', str(threads[2]['id']))
    expect(page.locator('.thread.active')).to_be_focused()
    page.keyboard.press('ArrowLeft'); expect(card).to_be_focused()
    expect(field).to_have_value('Unsent café reply')
    expect(search).to_have_value(query)
    # Once the card itself has focus, Escape still returns to the full list.
    page.keyboard.press('Escape')
    expect(page.locator('#passage-spotlight')).to_be_hidden()
    expect(field).to_have_value('Unsent café reply')
    expect(search).to_have_value(query)


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('action', ['resolve', 'delete-thread', 'delete-message'])
@pytest.mark.parametrize('spotlight', [False, True])
def test_zen_resolution_and_deletion_with_and_without_spotlight(workspace_page, action, spotlight):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    threads = discussions(root, ws)
    if action == 'delete-message':
        ws.reply(threads[1]['id'], 'Keep this thread after deleting one comment', 'Agent')
    page.goto(url); open_file(page, 'note.md')
    card = page.locator(f'.thread[data-thread="{threads[1]["id"]}"]')
    card.click(position={'x': 4, 'y': 4})
    if not spotlight:
        page.keyboard.press('Escape')
    page.locator('#zen-toggle').click()
    card.locator(f'[data-action="{action}"]').first.click()
    if action.startswith('delete'):
        page.locator('.lg-dialog button[type=submit]').click()
    else:
        expect(card).to_have_attribute('data-resolved', 'true')
        expect(page.locator('.thread.active')).to_have_attribute('data-thread', str(threads[1]['id']))
        if spotlight:
            expect(card).to_be_focused()
        else:
            expect(page.locator('#discussion-sidebar')).to_be_focused()
        page.keyboard.press('ArrowRight')
    current = page.locator('.thread.active')
    expect(current).to_have_attribute('data-thread', str(threads[2]['id']))
    expect(current).to_be_focused()
    expect(page.locator('.focused-highlight')).to_have_text('Last passage.')
    expect(page.locator('.focused-highlight')).to_be_in_viewport()
    if spotlight or action == 'resolve':
        expect(page.locator('#passage-spotlight')).to_be_visible()
    else:
        expect(page.locator('#passage-spotlight')).not_to_be_visible()
    # Right Arrow wraps to the first open thread after the last is resolved.
    current.locator('[data-action=resolve]').click()
    expect(current).to_have_attribute('data-thread', str(threads[2]['id']))
    expect(current).to_have_attribute('data-resolved', 'true')
    page.keyboard.press('ArrowRight')
    expect(current).to_have_attribute('data-thread', str(threads[0]['id']))
    expect(page.locator('.focused-highlight')).to_have_text('First passage.')
    expect(page.locator('.focused-highlight')).to_be_in_viewport()
    if action == 'delete-message':
        assert not ws.get_thread(threads[1]['id'])['resolved']
        assert len(ws.get_thread(threads[1]['id'])['messages']) == 1


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_resolving_preserves_manual_focus_and_the_final_spotlight(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    threads = discussions(root, ws)
    page.goto(url); open_file(page, 'note.md')
    page.locator(f'.thread[data-thread="{threads[0]["id"]}"]').click(position={'x':4, 'y':4})
    page.locator('#zen-toggle').click()
    held = []
    resolve_url = f'{url}/api/threads/{threads[0]["id"]}'

    def hold_resolve(route):
        if route.request.method == 'PATCH':
            held.append(route)
            page.evaluate('() => { window.resolveRequestHeld = true; }')
        else:
            route.continue_()

    page.route(resolve_url, hold_resolve)
    page.locator('.thread.active [data-action=resolve]').click()
    page.wait_for_function('() => window.resolveRequestHeld === true')
    page.keyboard.press('Escape')
    page.locator(f'.thread[data-thread="{threads[2]["id"]}"] .thread-summary').click()
    expect(page.locator('.thread.active')).to_have_attribute('data-thread', str(threads[2]['id']))
    with page.expect_response(lambda response: response.url == resolve_url and response.request.method == 'PATCH'):
        held[0].continue_()
    page.unroute(resolve_url)
    expect(page.locator('#thread-count')).to_have_text('2')
    expect(page.locator('.thread.active')).to_have_attribute('data-thread', str(threads[2]['id']))
    active = page.locator('.thread.active')
    # Resolve the remaining threads, moving between them explicitly.
    for index, count in [(2, '1'), (1, '0')]:
        expect(active).to_have_attribute('data-thread', str(threads[index]['id']))
        expect(active).to_be_focused()
        active.locator('[data-action=resolve]').click()
        expect(page.locator('#thread-count')).to_have_text(count)
        expect(active).to_have_attribute('data-thread', str(threads[index]['id']))
        expect(active).to_have_attribute('data-resolved', 'true')
        expect(active).to_be_focused()
        page.keyboard.press('ArrowRight')
    expect(page.locator('#passage-spotlight')).to_be_visible()
    expect(active).to_have_attribute('data-thread', str(threads[1]['id']))
    expect(active).to_be_focused()


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_spotlight_cross_file_arrows_follow_scope_and_keep_drafts(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    (root/'a.txt').write_text('Alpha passage')
    (root/'b.txt').write_text('Beta passage')
    first = ws.create_thread('a.txt', 0, 5, 'First', 'Reviewer', ws.read('a.txt')['version'])
    second = ws.create_thread('b.txt', 0, 4, 'Second', 'Reviewer', ws.read('b.txt')['version'])
    page.goto(url); open_file(page, 'a.txt')
    first_card = page.locator(f'.thread[data-thread="{first["id"]}"]')
    first_card.click(position={'x':4, 'y':4}); first_card.focus(); page.keyboard.press('ArrowRight')
    expect(page.locator('#document-name')).to_have_text('a.txt')
    page.keyboard.press('Escape'); page.locator('#thread-scope').check()
    expect(page.locator('#thread-total')).to_have_text('2 threads · 2 open · 0 closed')
    first_card.click(position={'x':4, 'y':4}); start_reply(page, first_card).fill('Keep my reply')
    first_card.focus(); page.keyboard.press('ArrowRight')
    expect(page.locator('#document-name')).to_have_text('b.txt')
    second_card = page.locator(f'.thread[data-thread="{second["id"]}"]')
    expect(second_card).to_be_focused(); expect(page.locator('#passage-spotlight')).to_be_visible()
    page.keyboard.press('ArrowLeft')
    expect(page.locator('#document-name')).to_have_text('a.txt')
    expect(first_card).to_be_focused(); expect(first_card.locator('textarea')).to_have_value('Keep my reply')
