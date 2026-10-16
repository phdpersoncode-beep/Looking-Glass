"""Sidebar keyboard navigation and zen completion share the full scoped queue."""
import os

import pytest
from test_requested_features import workspace_page, open_file
from test_spotlight_navigation_browser import settle

pytestmark = [pytest.mark.browser, pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]


def discussions(root, ws):
    text = 'First passage.\n\n' + 'Context.\n\n'*70 + 'Middle passage.\n\n' + 'Context.\n\n'*70 + 'Last passage.\n'
    (root/'note.md').write_text(text)
    version = ws.read('note.md')['version']
    return [ws.create_thread('note.md', text.index(quote), text.index(quote)+len(quote), 'Queue discussion', 'Reviewer', version)
            for quote in ['First passage.', 'Middle passage.', 'Last passage.']]


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_spotlight_arrows_keep_sidebar_focus_drafts_and_search_position(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    threads = discussions(root, ws)
    closed = ws.create_thread('note.md', 0, 5, 'Closed discussion', 'Reviewer', ws.read('note.md')['version'])
    ws.update_thread(closed['id'], resolved=True)
    page.goto(url); open_file(page, 'note.md')
    search = page.locator('#thread-search'); before = search.bounding_box()['y']
    expect(page.locator('#thread-total')).to_have_text('4 threads total')
    card = lambda i: page.locator(f'.thread[data-thread="{threads[i]["id"]}"]')
    card(0).locator('.comment-markdown p').click()
    expect(page.locator('#passage-spotlight')).to_be_visible()
    assert abs(search.bounding_box()['y'] - before) < 1
    field = card(0).locator('textarea'); field.fill('Unsent first reply')
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
@pytest.mark.parametrize('action', ['resolve', 'delete-thread', 'delete-message'])
@pytest.mark.parametrize('spotlight', [False, True])
def test_zen_completion_advances_and_wraps_in_both_views(workspace_page, action, spotlight):
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
    if action.startswith('delete'):
        page.once('dialog', lambda dialog: dialog.accept())
    card.locator(f'[data-action="{action}"]').first.click()
    current = page.locator('.thread.active')
    expect(current).to_have_attribute('data-thread', str(threads[2]['id']))
    expect(current).to_be_focused()
    expect(page.locator('.focused-highlight')).to_have_text('Last passage.')
    expect(page.locator('.focused-highlight')).to_be_in_viewport()
    if spotlight:
        expect(page.locator('#passage-spotlight')).to_be_visible()
    else:
        expect(page.locator('#passage-spotlight')).not_to_be_visible()
    # Resolving the last passage wraps to the first open thread.
    current.locator('[data-action=resolve]').click()
    expect(current).to_have_attribute('data-thread', str(threads[0]['id']))
    expect(page.locator('.focused-highlight')).to_have_text('First passage.')
    expect(page.locator('.focused-highlight')).to_be_in_viewport()
    if action == 'delete-message':
        assert not ws.get_thread(threads[1]['id'])['resolved']
        assert len(ws.get_thread(threads[1]['id'])['messages']) == 1


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_last_zen_spotlight_thread_clears_and_resolving_does_not_override_new_focus(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    threads = discussions(root, ws)
    page.goto(url); open_file(page, 'note.md')
    page.locator(f'.thread[data-thread="{threads[0]["id"]}"]').click(position={'x':4, 'y':4})
    page.locator('#zen-toggle').click()
    held = []
    page.route('**/api/threads/*', lambda route: held.append(route) if route.request.method == 'PATCH' else route.continue_())
    page.locator('.thread.active [data-action=resolve]').click()
    assert held
    page.keyboard.press('Escape')
    page.locator(f'.thread[data-thread="{threads[2]["id"]}"] .thread-summary').click()
    expect(page.locator('.thread.active')).to_have_attribute('data-thread', str(threads[2]['id']))
    with page.expect_response(lambda response: response.request.method == 'PATCH'):
        held[0].continue_()
    page.unroute('**/api/threads/*')
    expect(page.locator('#thread-count')).to_have_text('2')
    expect(page.locator('.thread.active')).to_have_attribute('data-thread', str(threads[2]['id']))
    # Complete remaining threads; the final one clears spotlight and focus.
    for count in ['1', '0']:
        page.locator('.thread.active [data-action=resolve]').click()
        expect(page.locator('#thread-count')).to_have_text(count)
    expect(page.locator('#passage-spotlight')).not_to_be_visible()
    expect(page.locator('.thread.active')).to_have_count(0)
    page.locator('#show-resolved').check(); settle(page)
    expect(page.locator('.thread.active')).to_have_count(0)


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
    expect(page.locator('#thread-total')).to_have_text('2 threads total')
    first_card.click(position={'x':4, 'y':4}); first_card.locator('textarea').fill('Keep my reply')
    first_card.focus(); page.keyboard.press('ArrowRight')
    expect(page.locator('#document-name')).to_have_text('b.txt')
    second_card = page.locator(f'.thread[data-thread="{second["id"]}"]')
    expect(second_card).to_be_focused(); expect(page.locator('#passage-spotlight')).to_be_visible()
    page.keyboard.press('ArrowLeft')
    expect(page.locator('#document-name')).to_have_text('a.txt')
    expect(first_card).to_be_focused(); expect(first_card.locator('textarea')).to_have_value('Keep my reply')
