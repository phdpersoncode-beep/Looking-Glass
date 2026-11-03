"""Reply progress settles without discarding drafts or failed attachments."""
import os

import pytest
from playwright.sync_api import expect
from test_requested_features import workspace_page, open_file

pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]


def open_reply(workspace_page):
    root, page, url, ws = workspace_page
    (root/'note.txt').write_text('Passage.')
    thread = ws.create_thread('note.txt', 0, 7, 'Review', 'Tester', ws.read('note.txt')['version'])
    page.goto(url)
    open_file(page, 'note.txt')
    page.locator('#next').click()
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
