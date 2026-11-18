import os
import pytest
from test_requested_features import workspace_page
pytestmark = [pytest.mark.browser, pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_reopening_clean_card_and_saving_only_edited_fields(workspace_page):
    from playwright.sync_api import expect
    _, page, url, ws = workspace_page
    ws.tasks.mutate(dict(action='create', title='Review plan', revision=0))
    page.goto(url)
    page.locator('#tasks-open').click()
    card = page.get_by_role('article', name='Review plan')
    card.click()
    page.get_by_role('button', name='Close card').click()
    ws.tasks.mutate(dict(action='update', ids=[1], changes={'description':'Agent notes'}, revision=1))
    expect(card).to_be_visible()
    with page.expect_response(lambda response: '/api/tasks?revision=1' in response.url and response.ok):
        pass
    card.click()
    description = page.get_by_label('Description', exact=True)
    expect(description).to_have_value('Agent notes')
    description.fill('My review notes')
    ws.tasks.mutate(dict(action='update', ids=[1], changes={'status':'to_review'}, revision=2))
    save = page.get_by_role('button', name='Save', exact=True)
    save.click()
    page.get_by_text('Review latest saved card', exact=True).click()
    page.get_by_role('button', name='Use this revision and keep my edits').click()
    save.click()
    expect(page.locator('.task-dialog')).to_have_count(0)
    updated = ws.tasks.read()['cards'][0]
    assert updated['description'] == 'My review notes' and updated['status'] == 'to_review'


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_delayed_save_does_not_replace_newer_poll(workspace_page):
    from playwright.sync_api import expect
    _, page, url, ws = workspace_page
    ws.tasks.mutate(dict(action='create', title='Plan', revision=0))
    polls, saves = [], []

    def hold(route):
        if route.request.method == 'POST':
            saves.append((route, route.fetch()))
        elif '?' in route.request.url:
            polls.append(route)
        else:
            route.continue_()

    page.route('**/api/tasks*', hold)
    page.goto(url)
    page.locator('#tasks-open').click()
    with page.expect_request(lambda request: '/api/tasks?revision=1' in request.url):
        page.get_by_role('article', name='Plan').click()
        page.get_by_label('Description', exact=True).fill('Saved from the UI')
    with page.expect_request(lambda request: request.method == 'POST' and request.url.endswith('/api/tasks')):
        page.get_by_role('button', name='Save', exact=True).click()
    # Drain the route callback so the server's response is held before the agent write.
    page.wait_for_function('() => document.querySelector(".task-save").disabled')
    assert saves and polls
    latest = ws.tasks.mutate(dict(action='create', title='New agent card', revision=2))
    polls[0].fulfill(json=latest)
    agent_card = page.get_by_role('article', name='New agent card')
    expect(agent_card).to_have_count(1)
    route, response = saves[0]
    route.fulfill(response=response)
    expect(page.locator('.task-dialog')).to_have_count(0)
    expect(agent_card).to_be_visible()


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_shared_planning_board(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    (root/'notes.md').write_text('# Notes\n')
    page.goto(url)
    page.locator('#tasks-open').click()
    expect(page.locator('.task-lane')).to_have_count(4)
    def create(title):
        page.get_by_role('button', name='Create task', exact=True).click()
        page.get_by_label('Title', exact=True).fill(title)
        page.get_by_role('button', name='Create', exact=True).click()
        expect(page.locator('.task-dialog')).to_have_count(0)
    create('Release')
    create('Implement board')
    release = page.get_by_role('article', name='Release', exact=True)
    release.get_by_role('button', name='Promote to milestone').click()
    expect(release.get_by_role('button', name='Convert to task')).to_be_visible()
    task = page.locator('.task-card', has_text='Implement board')
    task.click(modifiers=['Control'])
    page.get_by_label('Assign selected cards to milestone').select_option('1')
    page.get_by_role('button', name='Assign', exact=True).click()
    expect(task).to_contain_text('◇ #M1 Release')
    page.get_by_role('button', name='Clear', exact=True).click()
    task.drag_to(page.locator('.task-lane[data-status=done]'))
    expect(page.locator('.task-lane[data-status=done] .task-card')).to_have_count(1)
    release.click()
    expect(page.locator('.task-checklist').get_by_role('checkbox', name='Complete Implement board')).to_be_checked()
    page.get_by_label('Description', exact=True).fill('Milestone description')
    page.locator('.task-checklist').get_by_role('checkbox', name='Complete Implement board').uncheck()
    expect(page.locator('.task-checklist').get_by_role('checkbox', name='Complete Implement board')).to_be_enabled()
    expect(page.get_by_label('Description', exact=True)).to_have_value('Milestone description')
    page.locator('.task-checklist').get_by_role('checkbox', name='Complete Implement board').check()
    expect(page.locator('.task-checklist').get_by_role('checkbox', name='Complete Implement board')).to_be_enabled()
    page.locator('.task-checklist').get_by_role('button', name='Open #C02', exact=True).click()
    page.get_by_role('button', name='Cancel', exact=True).click()
    release.click()
    expect(page.get_by_label('Description', exact=True)).to_have_value('Milestone description')
    page.get_by_role('button', name='Save', exact=True).click()
    expect(page.locator('.task-dialog')).to_have_count(0)
    page.get_by_label('Search cards', exact=True).fill('ipb')
    expect(page.locator('.task-card')).to_have_count(1)
    page.get_by_label('Search cards', exact=True).fill('')
    page.locator('.tab', has_text='Tasks').get_by_role('button', name='Pin tab').click()
    page.locator('.file-entry[data-path="notes.md"]').click()
    page.locator('.tab-name', has_text='Tasks').click()
    expect(page.locator('.task-card')).to_have_count(2)
    page.reload()
    expect(page.locator('.task-card')).to_have_count(2)
    expect(page.get_by_role('button', name='Unpin tab')).to_be_visible()
    # Agent writes appear without remounting the board or losing the search field.
    page.get_by_label('Search cards', exact=True).fill('agt')
    ws.tasks.mutate(dict(action='create',title='Agent task',revision=ws.tasks.read()['revision']))
    expect(page.locator('.task-card')).to_have_count(1)
    expect(page.get_by_label('Search cards', exact=True)).to_have_value('agt')
    page.get_by_label('Search cards', exact=True).fill('')
    page.locator('.task-card', has_text='Agent task').click()
    page.get_by_label('Description', exact=True).fill('Unsent text')
    ws.tasks.mutate(dict(action='create', title='Concurrent', revision=ws.tasks.read()['revision']))
    page.get_by_role('button', name='Save', exact=True).click()
    expect(page.locator('.task-dialog [role=alert]')).to_contain_text('board changed')
    expect(page.get_by_label('Description', exact=True)).to_have_value('Unsent text')
    page.get_by_text('Review latest saved card', exact=True).click()
    page.get_by_role('button', name='Use this revision and keep my edits', exact=True).click()
    page.get_by_role('button', name='Save', exact=True).click()
    expect(page.locator('.task-dialog')).to_have_count(0)
    assert next(c for c in ws.tasks.read()['cards'] if c['title']=='Agent task')['description']=='Unsent text'
    page.screenshot(path='/tmp/lg-task-board-wide.png')
    for theme in ('dark','light'):
        page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
        page.set_viewport_size({'width':800,'height':800})
        expect(page.locator('.task-tools')).to_be_visible()
        assert page.locator('.task-lanes').evaluate('e=>e.scrollWidth>e.clientWidth')
        page.screenshot(path=f'/tmp/lg-task-board-{theme}.png')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_board_bulk_archive_delete_keyboard_and_order(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    for title in ['Epic', 'One', 'Two', '<script>safe</script>']:
        ws.tasks.mutate(dict(action='create', title=title, revision=ws.tasks.read()['revision']))
    ws.tasks.mutate(dict(action='update',ids=[1],changes={'milestone':True},revision=4))
    ws.tasks.mutate(dict(action='update',ids=[2,3],changes={'milestone_id':1},revision=5))
    page.goto(url)
    page.locator('#tasks-open').click()
    expect(page.locator('.task-card')).to_have_count(4)
    page.get_by_role('article', name='Two', exact=True).drag_to(page.get_by_role('article', name='One', exact=True))
    expect(page.locator('.task-card-title')).to_have_text(['M1: Epic','Two','One','<script>safe</script>'])
    # Select via keyboard and Ctrl+click, then bulk archive and restore.
    page.get_by_role('article', name='One', exact=True).focus()
    page.keyboard.press('Space')
    page.get_by_role('article', name='Two', exact=True).click(modifiers=['Control'])
    expect(page.locator('.task-bulk')).to_contain_text('2 selected')
    page.get_by_role('button', name='Archive', exact=True).click()
    expect(page.locator('.task-card')).to_have_count(2)
    page.get_by_label('Show archive').check()
    expect(page.locator('.task-card')).to_have_count(2)
    for title in ['One','Two']:
        page.get_by_role('article', name=title, exact=True).click(modifiers=['Control'])
    page.get_by_role('button', name='Restore', exact=True).click()
    expect(page.locator('.task-card')).to_have_count(0)
    page.get_by_label('Show archive').uncheck()
    page.get_by_label('Filter by milestone', exact=True).select_option('1')
    expect(page.locator('.task-card')).to_have_count(3)
    page.get_by_role('article', name='Epic', exact=True).click()
    page.get_by_role('button', name='Delete', exact=True).click()
    page.get_by_role('button', name='Delete permanently', exact=True).click()
    expect(page.locator('.task-dialog')).to_have_count(0)
    expect(page.locator('.task-card')).to_have_count(3)
    assert all(c['milestone_id'] is None for c in ws.tasks.read()['cards'])
    # The status editor is also the keyboard-accessible way to move cards.
    card = page.get_by_role('article', name='One', exact=True)
    card.focus()
    expect(card).to_be_focused()
    card.press('Enter')
    expect(page.locator('.task-dialog')).to_have_count(1)
    page.get_by_label('Status', exact=True).select_option('in_progress')
    page.get_by_role('button', name='Save', exact=True).click()
    expect(page.locator('.task-lane[data-status=in_progress] .task-card')).to_have_count(1)
    page.locator('#explorer-toggle').click()
    expect(page.locator('#tasks-open')).to_be_hidden()
    page.locator('#explorer-toggle').click()
    expect(page.locator('#tasks-open')).to_be_visible()


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_archived_milestone_and_completion_preferences(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    for title in ['Epic','Task']:
        ws.tasks.mutate(dict(action='create',title=title,revision=ws.tasks.read()['revision']))
    ws.tasks.mutate(dict(action='update',ids=[1],changes={'milestone':True},revision=2))
    ws.tasks.mutate(dict(action='update',ids=[2],changes={'milestone_id':1},revision=3))
    ws.tasks.mutate(dict(action='update',ids=[1],changes={'archived':True},revision=4))
    page.add_init_script('''const Original=window.AudioContext;window.AudioContext=class extends Original{constructor(...args){super(...args);window.taskDings=(window.taskDings||0)+1;}};''')
    page.emulate_media(reduced_motion='reduce')
    page.goto(url)
    page.locator('#tasks-open').click()
    page.get_by_role('article',name='Task',exact=True).click()
    expect(page.get_by_label('Milestone',exact=True)).to_have_value('1')
    page.get_by_label('Status',exact=True).select_option('done')
    page.get_by_role('button',name='Save',exact=True).click()
    expect(page.locator('.task-lane[data-status=done] .task-card')).to_have_count(1)
    assert page.evaluate('window.taskDings') == 1
    assert ws.tasks.read()['cards'][1]['milestone_id'] == 1
    expect(page.locator('.task-confetti')).to_have_count(0)
    page.get_by_label('Mute',exact=True).check()
    page.get_by_role('article',name='Task',exact=True).click()
    page.get_by_label('Status',exact=True).select_option('backlog')
    page.get_by_role('button',name='Save',exact=True).click()
    expect(page.locator('.task-lane[data-status=backlog] .task-card')).to_have_count(1)
    page.get_by_role('article',name='Task',exact=True).click()
    page.get_by_label('Status',exact=True).select_option('done')
    page.get_by_role('button',name='Save',exact=True).click()
    expect(page.locator('.task-lane[data-status=done] .task-card')).to_have_count(1)
    assert page.evaluate('window.taskDings') == 1
    page.reload()
    expect(page.get_by_label('Mute',exact=True)).to_be_checked()


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_card_comments_updates_references_and_milestone_style(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    def change(**data):
        return ws.tasks.mutate(dict(revision=ws.tasks.read()['revision'],author='Agent',**data))
    change(action='create',title='Epic')
    change(action='update',ids=[1],changes={'milestone':True})
    change(action='create',title='Implement')
    change(action='update',ids=[2],changes={'milestone_id':1})
    page.goto(url);page.locator('#tasks-open').click()
    epic=page.get_by_role('article',name='Epic',exact=True)
    task=page.get_by_role('article',name='Implement',exact=True)
    expect(epic.locator('.task-card-title')).to_have_text('M1: Epic')
    expect(task.locator('.task-reference')).to_have_text('#C02')
    for theme in ('light','dark'):
        page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
        assert epic.evaluate("e=>getComputedStyle(e).borderLeftWidth==='3px' && getComputedStyle(e).borderLeftColor!==getComputedStyle(e).borderRightColor")
        assert task.locator('.task-assignment').evaluate("e=>parseFloat(getComputedStyle(e).fontSize)<parseFloat(getComputedStyle(e.parentElement.querySelector('.task-card-title')).fontSize)")
    page.get_by_label('Search cards',exact=True).fill('#C02')
    expect(page.locator('.task-card')).to_have_count(1)
    task.click()
    expect(page.locator('.task-dialog h2')).to_have_attribute('aria-label','Implement')
    expect(page.locator('.task-permanent-reference')).to_have_text('Card #C02')
    expect(page.locator('.task-update')).to_have_count(2)
    page.get_by_label('Title',exact=True).fill('Renamed')
    comment=page.locator('.task-comment-form').get_by_label('Comment',exact=True)
    comment.fill('Human comment <script>literal</script>')
    page.get_by_role('button',name='Comment',exact=True).click()
    own=page.locator('.task-comment',has_text='Human comment')
    expect(own).to_be_visible()
    expect(page.get_by_label('Title',exact=True)).to_have_value('Renamed')
    expect(comment).to_have_value('')
    page.get_by_role('button',name='Save',exact=True).click()
    expect(page.locator('.task-dialog')).to_have_count(0)
    task=page.get_by_role('article',name='Renamed',exact=True)
    task.click()
    page.get_by_label('Title',exact=True).fill('Pending title')
    comment.fill('Unsent reply')
    change(action='comment',id=2,body='Agent response')
    expect(page.locator('.task-comment',has_text='Agent response')).to_be_visible()
    expect(comment).to_have_value('Unsent reply')
    expect(page.get_by_label('Title',exact=True)).to_have_value('Pending title')
    own.get_by_role('button',name='Delete comment').click()
    expect(own).to_have_count(0)
    page.locator('.task-update',has_text='Created card.').get_by_role('button',name='Delete update').click()
    expect(page.locator('.task-update',has_text='Created card.')).to_have_count(0)
    page.get_by_role('button',name='Cancel',exact=True).click()
    task.click()
    expect(comment).to_have_value('Unsent reply')
    expect(page.locator('.task-comment',has_text='Agent response')).to_be_visible()
    expect(page.locator('.task-comment',has_text='Human comment')).to_have_count(0)
    page.get_by_label('Title',exact=True).fill('Renamed')
    page.get_by_role('button',name='Save',exact=True).click()
    expect(page.locator('.task-dialog')).to_have_count(0)
    page.get_by_role('article',name='Renamed',exact=True).click()
    expect(page.locator('.task-update',has_text='Title: Implement → Renamed')).to_be_visible()
    page.reload()
    expect(page.locator('.task-card .task-reference')).to_have_text(['#C02'])


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_milestone_aliases_update_without_losing_card_identity_or_drafts(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    def change(**data):
        return ws.tasks.mutate(dict(revision=ws.tasks.read()['revision'],**data))
    for title in ('First milestone','Second milestone','Child task'):
        change(action='create',title=title)
    change(action='update',ids=[1,2],changes={'milestone':True})
    change(action='update',ids=[3],changes={'milestone_id':2})
    page.goto(url);page.locator('#tasks-open').click()
    first=page.locator('.task-card[data-id="1"]')
    second=page.locator('.task-card[data-id="2"]')
    child=page.get_by_role('article',name='Child task',exact=True)
    expect(first.locator('.task-card-title')).to_have_text('M1: First milestone')
    expect(second.locator('.task-card-title')).to_have_text('M2: Second milestone')
    change(action='update',ids=[1],changes={'archived':True})
    expect(first).to_have_count(0)
    expect(second.locator('.task-card-title')).to_have_text('M2: Second milestone')
    page.get_by_label('Show archive').check()
    expect(first.locator('.task-card-title')).to_have_text('M1: First milestone')
    page.get_by_label('Show archive').uncheck()
    change(action='update',ids=[1],changes={'archived':False})
    expect(first.locator('.task-card-title')).to_have_text('M1: First milestone')
    second.click()
    expect(page.locator('.task-dialog h2')).to_have_attribute('aria-label','M2: Second milestone')
    expect(page.locator('.task-permanent-reference')).to_have_text('Card #C02')
    page.get_by_role('button',name='Cancel',exact=True).click()
    child.click()
    page.get_by_label('Title',exact=True).fill('Unsent title')
    change(action='update',ids=[2],changes={'milestone_number':7})
    expect(page.get_by_label('Milestone',exact=True).locator('option:checked')).to_have_text('◇ #M7 Second milestone')
    expect(page.get_by_label('Title',exact=True)).to_have_value('Unsent title')
    expect(second.locator('.task-card-title')).to_have_text('M7: Second milestone')
    page.get_by_role('button',name='Cancel',exact=True).click()
    change(action='update',ids=[1],changes={'milestone':False})
    expect(first.locator('.task-reference')).to_have_text('#C01')
    first.get_by_role('button',name='Promote to milestone').click()
    expect(second.locator('.task-card-title')).to_have_text('M7: Second milestone')
    page.get_by_label('Search cards',exact=True).fill('#M7')
    expect(page.locator('.task-card')).to_have_count(1)
    second.click()
    page.locator('.task-dialog').get_by_role('button',name='Convert to task',exact=True).click()
    expect(page.locator('.task-dialog')).to_have_count(0)
    page.get_by_label('Search cards',exact=True).fill('#C02')
    expect(second.locator('.task-reference')).to_have_text('#C02')
    page.reload()
    expect(second.locator('.task-reference')).to_have_text('#C02')
    second.get_by_role('button',name='Promote to milestone').click()
    expect(second.locator('.task-card-title')).to_have_text('M7: Second milestone')
    # Explicit external renumbering updates the heading without clearing a draft.
    second.click();page.get_by_label('Description',exact=True).fill('Draft description')
    change(action='delete',ids=[1])
    expect(page.locator('.task-dialog h2')).to_have_attribute('aria-label','M7: Second milestone')
    change(action='update',ids=[2],changes={'milestone_number':8})
    expect(page.locator('.task-dialog h2')).to_have_attribute('aria-label','M8: Second milestone')
    expect(page.locator('.task-permanent-reference')).to_have_text('Card #C02')
    expect(page.get_by_label('Description',exact=True)).to_have_value('Draft description')


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_compact_activity_rows_and_larger_tasks_symbol(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    ws.tasks.mutate(dict(action='create',revision=0,title='Compact activity'))
    ws.tasks.mutate(dict(action='update',revision=1,ids=[1],changes={'status':'in_progress'},author='Agent'))
    ws.tasks.mutate(dict(action='comment',id=1,body='A readable comment.',author='Reviewer'))
    multiline = 'First line.\n' + 'Long comments should wrap and remain readable. ' * 6 + 'Last line.'
    ws.tasks.mutate(dict(action='comment', id=1, body=multiline, author='Coding Agent'))
    page.goto(url)
    symbol=page.locator('#tasks-open svg')
    expect(symbol).to_be_visible()
    assert symbol.bounding_box()['width']>=20 and symbol.bounding_box()['height']>=20
    assert symbol.bounding_box()['width']>page.locator('#history-open svg').bounding_box()['width']
    page.locator('#tasks-open').click()
    page.get_by_role('article',name='Compact activity',exact=True).click()
    update=page.locator('.task-update',has_text='Status: Backlog → In progress')
    comment=page.locator('.task-comment',has_text='A readable comment.')
    expect(update).to_be_visible();expect(comment).to_be_visible()
    for theme in ('light','dark'):
        page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
        assert update.bounding_box()['height']<=36
        assert update.bounding_box()['height']<comment.bounding_box()['height']
        assert update.evaluate('e=>parseFloat(getComputedStyle(e).fontSize)')<comment.evaluate('e=>parseFloat(getComputedStyle(e).fontSize)')
        assert comment.bounding_box()['height'] <= 52
    page.set_viewport_size({'width':800,'height':800})
    expect(update.get_by_role('button',name='Delete update')).to_be_visible()
    assert update.get_by_role('button',name='Delete update').bounding_box()['width']>=22
    update.get_by_role('button',name='Delete update').click()
    expect(update).to_have_count(0)
    expect(comment).to_contain_text('A readable comment.')
    page.set_viewport_size({'width':390,'height':844})
    long_comment = page.locator('.task-comment', has_text='First line.')
    body = long_comment.locator('p')
    expect(body).to_contain_text('Last line.')
    assert body.text_content() == multiline
    assert body.bounding_box()['height'] > 36
    assert long_comment.evaluate('row => row.scrollWidth <= row.clientWidth')
    remove = long_comment.get_by_role('button', name='Delete comment')
    assert remove.bounding_box()['width'] >= 24
    composer = page.locator('.task-comment-form')
    field = composer.get_by_role('textbox', name='Comment', exact=True)
    send = composer.get_by_role('button', name='Comment', exact=True)
    field_box, send_box = field.bounding_box(), send.bounding_box()
    assert field_box['height'] <= 54
    assert send_box['x'] >= field_box['x'] + field_box['width']
    assert abs((send_box['y'] + send_box['height']) - (field_box['y'] + field_box['height'])) <= 1


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_edit_milestone_number_validation_persistence_and_conflicts(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    def change(**data):return ws.tasks.mutate(dict(revision=ws.tasks.read()['revision'],author='Agent',**data))
    for title in ('Epic','Other epic','Child'):change(action='create',title=title)
    change(action='update',ids=[1,2],changes={'milestone':True})
    change(action='update',ids=[3],changes={'milestone_id':1})
    page.goto(url);page.locator('#tasks-open').click()
    epic=page.get_by_role('article',name='Epic',exact=True)
    epic.click()
    number=page.get_by_label('Milestone number (#M)',exact=True)
    expect(number).to_have_value('1')
    number.fill('12')
    page.get_by_role('button',name='Save',exact=True).click()
    expect(page.locator('.task-dialog')).to_have_count(0)
    expect(epic.locator('.task-card-title')).to_have_text('M12: Epic')
    expect(page.get_by_role('article',name='Child',exact=True)).to_contain_text('◇ #M12 Epic')
    page.get_by_label('Search cards',exact=True).fill('M12')
    expect(page.locator('.task-card')).to_have_count(1)
    epic.click()
    expect(page.locator('.task-update',has_text='Milestone number: #M1 → #M12')).to_be_visible()
    expect(page.locator('.task-permanent-reference')).to_have_text('Card #C01')
    number.fill('2')
    page.get_by_role('button',name='Save',exact=True).click()
    expect(page.locator('.task-dialog [role=alert]')).to_contain_text('#M2 is already in use')
    expect(number).to_have_value('2')
    page.get_by_label('Title',exact=True).fill('Unsent title')
    number.fill('20')
    change(action='update',ids=[1],changes={'milestone_number':14})
    expect(page.locator('.task-dialog h2')).to_have_attribute('aria-label','M14: Unsent title')
    expect(number).to_have_value('20')
    page.get_by_role('button',name='Save',exact=True).click()
    expect(page.locator('.task-dialog [role=alert]')).to_contain_text('board changed')
    expect(page.get_by_label('Title',exact=True)).to_have_value('Unsent title')
    page.get_by_role('button',name='Cancel',exact=True).click()
    page.get_by_label('Search cards',exact=True).fill('C01')
    epic.click()
    expect(number).to_have_value('14')
    number.fill('0')
    page.get_by_role('button',name='Save',exact=True).click()
    assert not number.evaluate('(e)=>e.checkValidity()')
    number.fill('12')
    page.get_by_role('button',name='Save',exact=True).click()
    expect(page.locator('.task-dialog')).to_have_count(0)
    page.reload()
    expect(epic.locator('.task-card-title')).to_have_text('M12: Epic')
    epic.click()
    page.locator('.task-dialog').get_by_role('button',name='Convert to task',exact=True).click()
    expect(epic.locator('.task-reference')).to_have_text('#C01')
    epic.get_by_role('button',name='Promote to milestone').click()
    expect(epic.locator('.task-card-title')).to_have_text('M12: Epic')
