"""Quiet author settings and shared sidebar controls in both browser engines."""
import os

import pytest
from playwright.sync_api import expect
from test_requested_features import workspace_page, open_file
from test_review_mode_browser import wait_saved

pytestmark = [pytest.mark.browser, pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]


def edit_author(page, name):
    page.get_by_role('button', name='Edit author name', exact=True).click()
    page.get_by_role('textbox', name='Author name', exact=True).fill(name)
    page.locator('#author-form').get_by_role('button', name='Save', exact=True).click()
    expect(page.locator('#author-popover')).not_to_be_visible()


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_author_popover_defaults_cancel_and_comment_reply_review_attribution(workspace_page):
    root, page, url, ws = workspace_page
    (root/'note.txt').write_text('First passage.\n\nSecond passage.')
    thread = ws.create_thread('note.txt', 0, 5, 'Initial feedback', 'Reviewer', ws.read('note.txt')['version'])
    page.add_init_script("localStorage.setItem('looking-glass-author','Old global name')")
    page.goto(url); open_file(page, 'note.txt')
    pen = page.get_by_role('button', name='Edit author name', exact=True)
    name = page.get_by_role('textbox', name='Author name', exact=True)
    expect(page.locator('#discussion-sidebar input[type=text]')).to_have_count(0)
    expect(page.locator('#author-popover')).not_to_be_visible()
    pen.click(); expect(name).to_have_value('User'); expect(name).to_be_focused()
    name.fill('Discard this name'); name.press('Escape')
    expect(page.locator('#author-popover')).not_to_be_visible(); expect(pen).to_be_focused()
    card = page.locator(f'.thread[data-thread="{thread["id"]}"]')
    card.locator('[data-action=jump]').first.click()
    card.locator('textarea').fill('Default author reply')
    card.locator('button[type=submit]').click()
    expect(card).to_contain_text('Default author reply')
    assert ws.get_thread(thread['id'])['messages'][-1]['author'] == 'User'
    # The editor also works in spotlight; Escape dismisses only the popover.
    expect(page.locator('#passage-spotlight')).to_be_visible()
    pen.click(); name.fill('Cancelled'); name.press('Escape')
    expect(page.locator('#passage-spotlight')).to_be_visible()
    edit_author(page, '  Zoë 王  ')
    pen.click(); expect(name).to_have_value('Zoë 王')
    name.fill('Not saved'); page.locator('#author-form').get_by_role('button', name='Cancel').click()
    page.locator('.cm-content').click(); page.keyboard.press('Control+Home'); page.keyboard.press('Control+Shift+ArrowRight')
    page.locator('#annotate').click()
    page.locator('#comment-body').fill('Named comment'); page.locator('#comment-submit').click()
    expect(page.get_by_text('Named comment', exact=True)).to_be_visible()
    assert next(t for t in ws.threads() if t['messages'][0]['body'] == 'Named comment')['messages'][0]['author'] == 'Zoë 王'
    page.locator('#work-mode').click()
    expect(page.locator('#approve-review')).to_be_visible()
    page.locator('.cm-content').click(); page.keyboard.press('Control+End'); page.keyboard.insert_text(' Human revision')
    wait_saved(page)
    page.locator('#review-history').click()
    expect(page.locator('#review-events')).to_contain_text('Zoë 王')
    page.locator('#review-history-dialog [data-close]').click()
    page.reload()
    pen.click(); expect(name).to_have_value('Zoë 王')
    name.fill('Outside cancellation'); page.locator('#document-name').click()
    expect(page.locator('#author-popover')).not_to_be_visible()
    pen.click(); expect(name).to_have_value('Zoë 王')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_author_name_is_remembered_separately_for_each_project(workspace_page):
    root, page, url, _ = workspace_page
    other = root/'second-project'; other.mkdir()
    page.goto(url)
    edit_author(page, 'Project one')
    current = root
    for path, expected, replacement in [(other, 'User', 'Project two'), (root, 'Project one', '   '), (other, 'Project two', None), (root, 'User', None)]:
        page.locator('#directory-open').click()
        expect(page.locator('#directory-path')).to_have_value(str(current))
        page.locator('#directory-path').fill(str(path))
        with page.expect_navigation(wait_until='load'):
            page.locator('#directory-choose').click()
        expect(page.locator('.root-label')).to_have_text(str(path))
        current = path
        page.locator('#author-edit').click()
        expect(page.locator('#author')).to_have_value(expected)
        if replacement is not None:
            page.locator('#author').fill(replacement)
            page.locator('#author').press('Enter')
        else:
            page.locator('#author').press('Escape')
    page.reload(); page.locator('#author-edit').click()
    expect(page.locator('#author')).to_have_value('User')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_sidebar_controls_and_author_popover_fit_both_themes_and_narrow_panes(workspace_page):
    root, page, url, ws = workspace_page
    (root/'folder').mkdir(); (root/'folder'/'note.txt').write_text('A passage')
    ws.create_thread('folder/note.txt', 0, 1, 'First', 'Reviewer', ws.read('folder/note.txt')['version'])
    ws.create_thread('folder/note.txt', 2, 9, 'Second', 'Reviewer', ws.read('folder/note.txt')['version'])
    page.goto(url)
    page.get_by_role('button', name='Expand all folders', exact=True).click()
    open_file(page, 'folder/note.txt')
    for width in [1440, 900]:
        page.set_viewport_size({'width': width, 'height': 850})
        if width == 900:
            for separator in ['#file-resize', '#discussion-resize']:
                page.locator(separator).focus(); page.keyboard.press('Home')
        for theme in ['light', 'dark']:
            if page.locator('html').get_attribute('data-theme') != theme: page.locator('#theme').click()
            for sidebar in ['#file-sidebar', '#discussion-sidebar']:
                bounds = page.locator(sidebar).bounding_box()
                boxes = page.locator(sidebar+' .panel-heading button').evaluate_all('els=>els.map(el=>{const r=el.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom}})')
                assert all(box['left'] >= bounds['x'] and box['right'] <= bounds['x']+bounds['width'] for box in boxes)
                assert all(first['right'] <= second['left'] for first, second in zip(boxes, boxes[1:]))
            page.locator('#author-edit').click()
            expect(page.locator('#author')).to_be_focused()
            box = page.locator('#author-popover').bounding_box()
            assert box['x'] >= 0 and box['x']+box['width'] <= width
            assert box['y'] >= 0 and box['y']+box['height'] <= 850
            page.locator('#author').press('Escape')
            page.get_by_role('button', name='Collapse all threads', exact=True).click()
            expect(page.locator('#threads>.thread.collapsed')).to_have_count(2)
            page.get_by_role('button', name='Expand all threads', exact=True).click()
            expect(page.locator('#threads>.thread.collapsed')).to_have_count(0)
            page.get_by_role('button', name='Collapse all folders', exact=True).click()
            expect(page.locator('.file-entry[data-path="folder/note.txt"]')).not_to_be_visible()
            page.get_by_role('button', name='Expand all folders', exact=True).click()
            expect(page.locator('.file-entry[data-path="folder/note.txt"]')).to_be_visible()
