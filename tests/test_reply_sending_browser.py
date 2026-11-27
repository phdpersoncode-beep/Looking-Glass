"""Reply progress settles without discarding drafts or failed attachments."""
import os

import pytest
from playwright.sync_api import expect
from test_requested_features import workspace_page, open_file, start_reply

pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]


def open_reply(workspace_page):
    root, page, url, ws = workspace_page
    (root/'note.txt').write_text('Passage.')
    thread = ws.create_thread('note.txt', 0, 7, 'Review', 'Tester', ws.read('note.txt')['version'])
    page.goto(url)
    open_file(page, 'note.txt')
    page.locator('#next').click()
    start_reply(page)
    return page, ws, thread['id'], page.locator('.reply-form')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('attached', [False, True])
@pytest.mark.parametrize('next_draft', ['', 'You can resolve this'])
def test_successful_reply_clears_sending_and_preserves_next_draft(workspace_page, attached, next_draft):
    page, ws, identifier, form = open_reply(workspace_page)
    if attached:
        page.locator('#theme').click()
        page.set_viewport_size({'width': 900, 'height': 960})
        form.locator('.attach-files').set_input_files([
            {'name': 'notes.txt', 'mimeType': 'text/plain', 'buffer': b'Attachment'}])
    field = form.locator('textarea')
    submit = form.locator('button[type=submit]')
    status = form.locator('.composer-status')
    held = []
    page.route(f'**/api/threads/{identifier}/replies', lambda route: held.append(route))
    field.fill('My reply')
    submit.click()
    expect(status).to_have_text('Sending…')
    expect(status).to_be_visible()
    expect(submit).to_be_disabled()
    page.wait_for_function('()=>document.querySelector(".reply-form").dataset.sending==="true"')
    assert len(held) == 1
    if next_draft:
        field.fill(next_draft)
    held.pop().continue_()
    expect(page.locator('.message').last).to_contain_text('My reply')
    expect(submit).to_be_enabled()
    expect(field).to_have_value(next_draft)
    expect(status).to_be_hidden()
    expect(status).to_have_text('')
    expect(form.locator('.pending-files')).to_be_hidden()
    assert len(ws.get_thread(identifier)['attachments']) == int(attached)
    # A later server refresh must retain the settled composer and unsent text.
    ws.reply(identifier, 'Agent follow-up', 'Agent')
    expect(page.locator('.message').last).to_contain_text('Agent follow-up', timeout=10000)
    expect(status).to_be_hidden()
    expect(field).to_have_value(next_draft)


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_failed_reply_keeps_error_draft_and_attachment_then_retries(workspace_page):
    page, ws, identifier, form = open_reply(workspace_page)
    field = form.locator('textarea')
    submit = form.locator('button[type=submit]')
    status = form.locator('.composer-status')
    field.fill('Keep this reply')
    form.locator('.attach-files').set_input_files([
        {'name': 'notes.txt', 'mimeType': 'text/plain', 'buffer': b'Attachment'}])
    pattern = f'**/api/threads/{identifier}/replies'
    page.route(pattern, lambda route: route.fulfill(
        status=503, json={'error': 'Unable to send right now'}))
    submit.click()
    expect(status).to_have_text('Unable to send right now')
    expect(status).to_be_visible()
    expect(status).to_have_class('composer-status error')
    expect(submit).to_be_enabled()
    expect(field).to_have_value('Keep this reply')
    expect(form.locator('.pending-files')).to_contain_text('notes.txt')
    assert len(ws.get_thread(identifier)['messages']) == 1
    page.unroute(pattern)
    submit.click()
    expect(page.locator('.message').last).to_contain_text('Keep this reply')
    expect(submit).to_be_enabled()
    expect(status).to_be_hidden()
    expect(status).to_have_text('')
    expect(status).not_to_have_class('composer-status error')
    expect(field).to_have_value('')
    expect(form.locator('.pending-files')).to_be_hidden()
    assert len(ws.get_thread(identifier)['messages']) == 2
    assert len(ws.get_thread(identifier)['attachments']) == 1


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_reply_mounts_only_on_request_and_can_finish_while_detached(workspace_page):
    root, page, url, ws = workspace_page
    (root / 'note.txt').write_text('First passage. Second passage.')
    version = ws.read('note.txt')['version']
    first = ws.create_thread('note.txt', 0, 5, 'First comment', 'Tester', version)['id']
    second = ws.create_thread('note.txt', 15, 21, 'Second comment', 'Tester', version)['id']
    page.goto(url)
    open_file(page, 'note.txt')
    first_card = page.get_by_role('article', name=f'Thread {first}', exact=True)
    second_card = page.get_by_role('article', name=f'Thread {second}', exact=True)
    form = page.locator('#threads .reply-form')
    expect(first_card).to_be_visible()
    expect(second_card).to_be_visible()
    expect(form).to_have_count(0)
    page.locator('#next').click()
    expect(first_card).to_have_class('thread active')
    expect(form).to_have_count(0)

    first_card.get_by_role('button', name=f'Reply to thread {first}').press('Enter')
    field = first_card.get_by_role('textbox', name=f'Reply to thread {first}')
    expect(field).to_be_focused()
    field.fill('Send this')
    form.locator('.attach-files').set_input_files({'name': 'notes.txt', 'mimeType': 'text/plain', 'buffer': b'Notes'})
    pending = []
    page.route(f'**/api/threads/{first}/replies', lambda route: pending.append(route))
    with page.expect_request(f'**/api/threads/{first}/replies'):
        field.press('Control+Enter')
    expect(form.locator('.composer-status')).to_have_text('Sending…')
    field.fill('Keep the next reply')
    first_card.get_by_role('button', name=f'Collapse thread {first}').click()
    expect(form).to_have_count(0)
    second_field = start_reply(page, second_card)
    second_field.fill('Separate draft')
    expect(form).to_have_count(1)
    pending.pop().continue_()
    expect(first_card.locator('.message').last).to_contain_text('Send this')
    expect(second_field).to_be_focused()
    expect(second_field).to_have_value('Separate draft')
    first_card.get_by_role('button', name=f'Expand thread {first}').click()
    expect(form).to_have_count(1)
    expect(field).to_have_value('Keep the next reply')
    expect(form.locator('.composer-status')).to_be_hidden()
    expect(form.locator('.pending-files')).to_be_hidden()
    expect(form.locator('button[type=submit]')).to_be_enabled()
    assert len(ws.get_thread(first)['attachments']) == 1


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_reply_to_unread_thread_stays_visible_after_marking_it_read(workspace_page):
    root, page, url, ws = workspace_page
    (root / 'note.txt').write_text('Passage.')
    identifier = ws.create_thread('note.txt', 0, 7, 'Review', 'Tester', ws.read('note.txt')['version'])['id']
    page.goto(url)
    open_file(page, 'note.txt')
    page.locator('#only-unread').check()
    card = page.get_by_role('article', name=f'Thread {identifier}', exact=True)
    field = start_reply(page, card)
    expect(field).to_be_focused()
    expect(card).to_have_class('thread active')
    expect(page.locator('#thread-unread-count')).to_have_text('0 unread')
