import os

import pytest
from playwright.sync_api import expect

from test_requested_features import workspace_page

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER'),
]


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_task_document_round_trip_preserves_drafts_and_passage_discussion(workspace_page):
    root, page, url, ws = workspace_page
    path = 'research notes.md'
    text = '# Research notes\n\nA passage with open questions.\n'
    (root / path).write_text(text)
    ws.create_thread(path, text.index('A passage'), text.index('questions') + len('questions'),
                     'Which assumption drives the result?', 'Reviewer', ws.read(path)['version'])
    ws.tasks.mutate(dict(action='create', title='Check assumptions', revision=0))
    ws.tasks.mutate(dict(action='comment', id=1, body=f'Read @"{path}" before updating the plan.'))
    page.goto(url)
    page.locator('#tasks-open').click()
    page.get_by_role('article', name='Check assumptions').click()
    card = page.locator('dialog.task-detail')
    description = card.get_by_role('textbox', name='Description')
    comment = card.get_by_role('textbox', name='Comment', exact=True)
    description.fill('Compare these results with @research')
    suggestion = page.get_by_role('option', name=path)
    expect(suggestion).to_be_visible()
    description.press('Enter')
    expect(description).to_have_value(f'Compare these results with @"{path}" ')
    comment.fill('Question for the next agent session')
    related = card.locator('.task-related-files').get_by_role('link', name=path)
    related.click()
    expect(page.locator('#document-name')).to_have_text(path)
    expect(page.locator('#threads')).to_contain_text('Which assumption drives the result?')
    page.get_by_role('button', name='Return to task card').click()
    expect(description).to_have_value(f'Compare these results with @"{path}" ')
    expect(comment).to_have_value('Question for the next agent session')
    card.locator('.task-comment').get_by_role('link', name=f'@"{path}"').click()
    expect(page.locator('#document-name')).to_have_text(path)
    page.get_by_role('button', name='Return to task card').click()
    expect(card).to_be_visible()
    assert ws.tasks.read()['cards'][0]['description'] == ''
