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


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_board_open_replaces_selection_and_renders_card_markdown(workspace_page):
    root, page, url, ws = workspace_page
    (root / 'plan.md').write_text('# Release plan\n')
    ws.tasks.mutate(dict(action='create', title='First', revision=0))
    source = '## Release notes\n\n- Review the plan in **@plan.md**\n- Run `pytest`'
    ws.tasks.mutate(dict(action='create', title='Second', revision=1))
    ws.tasks.mutate(dict(action='update', ids=[2], changes={'description': source}, revision=2))
    ws.tasks.mutate(dict(action='comment', id=2, author='Agent',
                         body='**Reviewed**\n\n> Looks good.\n\n<script>untrusted</script>'))
    page.goto(url)
    page.locator('#tasks-open').click()
    first = page.get_by_role('article', name='First', exact=True)
    second = page.get_by_role('article', name='Second', exact=True)
    sidebar = page.locator('#task-sidebar')
    first_row = sidebar.locator('[data-id="1"]')
    second_row = sidebar.locator('[data-id="2"]')
    first_row.locator('.task-outline-title').click()
    expect(first).to_have_attribute('aria-selected', 'true')
    second.click()
    expect(first_row).to_have_attribute('aria-selected', 'false')
    expect(second_row).to_have_attribute('aria-selected', 'true')
    expect(second).to_have_attribute('aria-selected', 'true')
    detail = page.get_by_role('dialog', name='Second')
    preview = detail.locator('.task-description-preview')
    expect(preview.get_by_role('heading', name='Release notes')).to_be_visible()
    expect(preview.get_by_role('listitem')).to_have_count(2)
    expect(preview.locator('strong')).to_have_text('@plan.md')
    expect(preview.get_by_role('link', name='@plan.md')).to_be_visible()
    expect(detail.locator('.task-related-files')).to_be_hidden()
    expect(preview.locator('code')).to_have_text('pytest')
    agent = detail.locator('.task-comment').filter(has_text='Agent')
    expect(agent.locator('.task-markdown strong')).to_have_text('Reviewed')
    expect(agent.locator('blockquote')).to_have_text('Looks good.')
    expect(agent.locator('script')).to_have_count(0)
    expect(agent).not_to_contain_text('untrusted')

    detail.get_by_role('button', name='Edit description').click()
    description = detail.get_by_role('textbox', name='Description')
    expect(description).to_have_value(source)
    expect(description).to_be_focused()
    revised = 'Updated with *emphasis*.'
    description.fill(revised)
    detail.get_by_role('button', name='Preview description').click()
    expect(preview.locator('em')).to_have_text('emphasis')
    detail.get_by_role('textbox', name='Comment', exact=True).fill('**Thanks** for the review.')
    detail.get_by_role('button', name='Comment', exact=True).click()
    expect(detail.locator('.task-comment .task-markdown strong').last).to_have_text('Thanks')
    detail.get_by_role('button', name='Close card').click()
    expect(second).to_have_attribute('aria-selected', 'false')
    expect(second_row).to_have_attribute('aria-selected', 'false')
    expect(first_row).to_have_attribute('aria-selected', 'false')
    assert ws.tasks.read()['cards'][1]['description'] == revised
    second.press('Enter')
    expect(second).to_have_attribute('aria-selected', 'true')
    expect(preview.locator('em')).to_have_text('emphasis')
    detail.get_by_role('button', name='Cancel', exact=True).click()
    expect(second).to_have_attribute('aria-selected', 'false')
