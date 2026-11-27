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
    expect(page.locator('.task-description-preview')).to_have_text('Agent notes')
    page.get_by_role('button', name='Edit description').click()
    expect(description).to_have_value('Agent notes')
    description.fill('My review notes')
    ws.tasks.mutate(dict(action='update', ids=[1], changes={'status':'to_review'}, revision=2))
    save = page.get_by_role('button', name='Close card', exact=True)
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
        page.get_by_role('button', name='Close card', exact=True).click()
    # Drain the route callback so the server's response is held before the agent write.
    page.wait_for_function('() => document.querySelector(".task-detail-close").disabled')
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
        page.get_by_role('button', name='Add task to Backlog', exact=True).click()
        page.get_by_label('Title', exact=True).fill(title)
        page.get_by_role('button', name='Create', exact=True).click()
        expect(page.locator('.task-dialog')).to_have_count(0)
    create('Release')
    create('Implement board')
    release = page.get_by_role('article', name='Release', exact=True)
    release.click()
    page.get_by_role('dialog').get_by_role('button', name='Promote to milestone').click()
    expect(release).to_have_count(0)
    release = page.locator('#task-sidebar .task-outline-row[data-id="1"] .task-outline-reference')
    expect(release).to_be_visible()
    task = page.locator('.task-card', has_text='Implement board')
    task.click(modifiers=['Control'])
    page.get_by_label('Assign selected cards to milestone').select_option('1')
    page.get_by_role('button', name='Assign', exact=True).click()
    expect(task).to_contain_text('◇ #M1 Release')
    page.get_by_role('button', name='Clear', exact=True).click()
    task.drag_to(page.locator('.task-lane[data-status=done]'))
    expect(page.locator('.task-lane[data-status=done] .task-card')).to_have_count(1)
    release.locator('..').get_by_role('button', name='Open card details').click()
    expect(page.locator('.task-checklist').get_by_role('checkbox', name='Complete Implement board')).to_be_checked()
    page.get_by_label('Description', exact=True).fill('Milestone description')
    page.locator('.task-checklist').get_by_role('checkbox', name='Complete Implement board').uncheck()
    expect(page.locator('.task-checklist').get_by_role('checkbox', name='Complete Implement board')).to_be_enabled()
    expect(page.get_by_label('Description', exact=True)).to_have_value('Milestone description')
    page.locator('.task-checklist').get_by_role('checkbox', name='Complete Implement board').check()
    expect(page.locator('.task-checklist').get_by_role('checkbox', name='Complete Implement board')).to_be_enabled()
    page.locator('.task-checklist').get_by_role('button', name='Open #C02', exact=True).click()
    page.get_by_role('button', name='Cancel', exact=True).click()
    release.locator('..').get_by_role('button', name='Open card details').click()
    expect(page.locator('.task-description-preview')).to_have_text('Milestone description')
    assert next(card for card in ws.tasks.read()['cards'] if card['id'] == 1)['description'] == 'Milestone description'
    page.get_by_role('button', name='Close card', exact=True).click()
    expect(page.locator('.task-dialog')).to_have_count(0)
    page.get_by_label('Search cards', exact=True).fill('ipb')
    expect(page.locator('.task-card')).to_have_count(1)
    page.get_by_label('Search cards', exact=True).fill('')
    page.locator('.tab', has_text='Tasks').get_by_role('button', name='Pin tab').click()
    page.locator('.file-entry[data-path="notes.md"]').click()
    page.locator('.tab-name', has_text='Tasks').click()
    expect(page.locator('.task-card')).to_have_count(1)
    page.reload()
    expect(page.locator('.task-card')).to_have_count(1)
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
    page.get_by_role('button', name='Close card', exact=True).click()
    expect(page.locator('.task-dialog [role=alert]')).to_contain_text('board changed')
    expect(page.get_by_label('Description', exact=True)).to_have_value('Unsent text')
    page.get_by_text('Review latest saved card', exact=True).click()
    page.get_by_role('button', name='Use this revision and keep my edits', exact=True).click()
    page.get_by_role('button', name='Close card', exact=True).click()
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
    expect(page.locator('.task-card')).to_have_count(3)
    page.get_by_role('article', name='Two', exact=True).drag_to(page.get_by_role('article', name='One', exact=True))
    expect(page.locator('.task-card-title')).to_have_text(['Two','One','<script>safe</script>'])
    # Select via keyboard and Ctrl+click, then bulk archive and restore.
    page.get_by_role('article', name='One', exact=True).focus()
    page.keyboard.press('Space')
    page.get_by_role('article', name='Two', exact=True).click(modifiers=['Control'])
    expect(page.locator('.task-bulk')).to_contain_text('2 selected')
    page.get_by_role('button', name='Archive', exact=True).click()
    expect(page.locator('.task-card')).to_have_count(1)
    page.get_by_label('Show archive').check()
    expect(page.locator('.task-card')).to_have_count(2)
    for title in ['One','Two']:
        page.get_by_role('article', name=title, exact=True).click(modifiers=['Control'])
    page.get_by_role('button', name='Restore', exact=True).click()
    expect(page.locator('.task-card')).to_have_count(0)
    page.get_by_label('Show archive').uncheck()
    page.get_by_role('button', name='Filter by milestone', exact=True).click()
    page.get_by_role('button', name='M1: Epic', exact=True).click()
    expect(page.locator('.task-card')).to_have_count(2)
    page.locator('#task-sidebar .task-outline-row[data-id="1"]').get_by_role('button', name='Open card details').click()
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
    page.get_by_role('button', name='Close card', exact=True).click()
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
    page.get_by_role('button',name='Close card',exact=True).click()
    expect(page.locator('.task-detail')).to_have_count(0)
    expect(page.locator('.task-lane[data-status=done] .task-card')).to_have_count(1)
    assert page.evaluate('window.taskDings') == 1
    assert ws.tasks.read()['cards'][1]['milestone_id'] == 1
    confetti = page.locator('.task-board > .task-confetti')
    first_bit = confetti.locator('i').first
    expect(first_bit).to_have_css('animation-name', 'task-celebrate')
    assert first_bit.evaluate('bit => bit.getAnimations().some(animation => animation.playState === "running")')
    expect(confetti).to_have_count(0)
    page.get_by_label('Mute',exact=True).check()
    page.get_by_role('article',name='Task',exact=True).click()
    page.get_by_label('Status',exact=True).select_option('backlog')
    page.get_by_role('button',name='Close card',exact=True).click()
    expect(page.locator('.task-lane[data-status=backlog] .task-card')).to_have_count(1)
    page.get_by_role('article',name='Task',exact=True).click()
    page.get_by_label('Status',exact=True).select_option('done')
    page.get_by_role('button',name='Close card',exact=True).click()
    expect(page.locator('.task-lane[data-status=done] .task-card')).to_have_count(1)
    expect(first_bit).to_have_css('animation-name', 'task-celebrate')
    assert page.evaluate('window.taskDings') == 1
    page.reload()
    expect(page.get_by_label('Mute',exact=True)).to_be_checked()


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_board_columns_fit_one_card_and_grow_with_more(workspace_page):
    from playwright.sync_api import expect
    _, page, url, ws = workspace_page
    for title, status in [('Queued', 'backlog'), ('Writing', 'in_progress'), ('Reviewing', 'in_progress')]:
        ws.tasks.mutate(dict(action='create', title=title, status=status, revision=ws.tasks.read()['revision']))
    page.goto(url)
    page.locator('#tasks-open').click()
    single = page.get_by_role('region', name='Backlog', exact=True)
    empty = page.get_by_role('region', name='Done', exact=True)
    multiple = page.get_by_role('region', name='In progress', exact=True)
    card = single.get_by_role('article')
    add = single.get_by_role('button', name='Add task to Backlog', exact=True)
    expect(card).to_have_count(1)
    expect(empty.get_by_role('button', name='Add task to Done', exact=True)).to_be_visible()
    for width in (1440, 900):
        page.set_viewport_size({'width': width, 'height': 780})
        lane_box, card_box, add_box = single.bounding_box(), card.bounding_box(), add.bounding_box()
        assert 0 <= add_box['y'] - (card_box['y'] + card_box['height']) <= 4
        assert 5 <= (lane_box['y'] + lane_box['height']) - (add_box['y'] + add_box['height']) <= 14
        assert abs(empty.bounding_box()['height'] - lane_box['height']) <= 2
        assert multiple.bounding_box()['height'] >= lane_box['height'] + card_box['height']


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
    epic=page.locator('#task-sidebar .task-outline-row[data-id="1"]')
    task=page.get_by_role('article',name='Implement',exact=True)
    expect(epic.locator('.task-outline-prefix')).to_have_text('M1:')
    expect(task.locator('.task-reference')).to_have_text('#C02')
    for theme in ('light','dark'):
        page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
        assert epic.evaluate("e=>getComputedStyle(e).borderLeftWidth==='2px' && getComputedStyle(e).borderLeftColor!==getComputedStyle(e).borderRightColor")
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
    page.get_by_role('button',name='Close card',exact=True).click()
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
    page.get_by_role('button',name='Close card',exact=True).click()
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
    sidebar=page.locator('#task-sidebar')
    first=sidebar.locator('.task-outline-row[data-id="1"]')
    second=sidebar.locator('.task-outline-row[data-id="2"]')
    first_card=page.locator('.task-card[data-id="1"]')
    second_card=page.locator('.task-card[data-id="2"]')
    child=page.get_by_role('article',name='Child task',exact=True)
    expect(first.locator('.task-outline-prefix')).to_have_text('M1:')
    expect(second.locator('.task-outline-prefix')).to_have_text('M2:')
    expect(first_card).to_have_count(0)
    change(action='update',ids=[1],changes={'archived':True})
    expect(first).to_have_count(0)
    expect(second.locator('.task-outline-prefix')).to_have_text('M2:')
    sidebar.get_by_role('button', name='Archived tasks in sidebar', exact=True).click()
    expect(first).to_have_attribute('data-archived','true')
    page.get_by_label('Show archive').check()
    expect(first.locator('.task-outline-prefix')).to_have_text('M1:')
    expect(first_card).to_have_count(0)
    page.get_by_label('Show archive').uncheck()
    change(action='update',ids=[1],changes={'archived':False})
    expect(first).to_have_attribute('data-archived','false')
    second.get_by_role('button', name='Open card details').click()
    expect(page.locator('.task-dialog h2')).to_have_attribute('aria-label','M2: Second milestone')
    expect(page.locator('.task-permanent-reference')).to_have_text('Card #C02')
    page.get_by_role('button',name='Cancel',exact=True).click()
    child.click()
    page.get_by_label('Title',exact=True).fill('Unsent title')
    change(action='milestone_move',id=2,before=1)
    expect(page.get_by_label('Milestone',exact=True).locator('option:checked')).to_have_text('◇ #M1 Second milestone')
    expect(page.get_by_label('Title',exact=True)).to_have_value('Unsent title')
    expect(second.locator('.task-outline-prefix')).to_have_text('M1:')
    page.get_by_role('button',name='Cancel',exact=True).click()
    change(action='update',ids=[1],changes={'milestone':False})
    expect(first_card.locator('.task-reference')).to_have_text('#C01')
    first_card.click()
    page.get_by_role('dialog').get_by_role('button', name='Promote to milestone').click()
    expect(second.locator('.task-outline-prefix')).to_have_text('M1:')
    page.get_by_label('Search cards',exact=True).fill('#M1')
    expect(page.locator('.task-card')).to_have_count(1)
    second.get_by_role('button', name='Open card details').click()
    page.locator('.task-dialog').get_by_role('button',name='Convert to task',exact=True).click()
    expect(page.locator('.task-dialog')).to_have_count(0)
    page.get_by_label('Search cards',exact=True).fill('#C02')
    expect(second_card.locator('.task-reference')).to_have_text('#C02')
    page.reload()
    expect(second_card.locator('.task-reference')).to_have_text('#C02')
    second_card.click()
    page.get_by_role('dialog').get_by_role('button', name='Promote to milestone').click()
    expect(second.locator('.task-outline-prefix')).to_have_text('M1:')
    # A reorder from another session updates the heading without clearing a draft.
    second.get_by_role('button', name='Open card details').click();page.get_by_label('Description',exact=True).fill('Draft description')
    change(action='move',id=1,status='done')
    expect(page.locator('.task-dialog h2')).to_have_attribute('aria-label','M1: Second milestone')
    change(action='milestone_move',id=1,before=2)
    expect(page.locator('.task-dialog h2')).to_have_attribute('aria-label','M2: Second milestone')
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
def test_sidebar_milestone_drag_and_keyboard_reorder_change_numbers(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    def change(**data):return ws.tasks.mutate(dict(revision=ws.tasks.read()['revision'],author='Agent',**data))
    for title in ('Epic','Other epic','Child','Other child','Nested child','Tail'):
        change(action='create',title=title)
    change(action='update',ids=[1,2],changes={'milestone':True})
    change(action='update',ids=[3],changes={'milestone_id':1})
    change(action='update',ids=[4],changes={'milestone_id':2})
    change(action='update',ids=[5],changes={'parent_id':4})
    page.goto(url);page.locator('#tasks-open').click()
    child=page.get_by_role('article',name='Child',exact=True)
    sidebar=page.locator('#task-sidebar')
    rows=sidebar.locator('.task-outline-row')
    epic=sidebar.locator('.task-outline-row[data-id="1"]')
    number=epic.locator('.task-outline-prefix')
    expect(page.locator('.task-card[data-id="1"],.task-card[data-id="2"]')).to_have_count(0)
    # Kanban order is independent of the milestone sequence.
    page.get_by_role('article',name='Other child',exact=True).drag_to(child)
    expect(page.locator('.task-card').first).to_have_attribute('data-id','4')
    expect(number).to_have_text('M1:')
    sidebar.locator('.task-outline-row[data-id="2"] .task-outline-title').drag_to(
        rows.first, target_position={'x':8,'y':6})
    expect(rows.first).to_have_attribute('data-id','2')
    assert rows.evaluate_all('rows => rows.map(row => Number(row.dataset.id))') == [2,4,5,1,3,6]
    expect(number).to_have_text('M2:')
    expect(child).to_contain_text('◇ #M2 Epic')
    expect(page.get_by_role('article',name='Nested child',exact=True)).to_contain_text('◇ #M1 Other epic')
    epic.get_by_role('button', name='Open card details').click()
    expect(page.locator('.task-update',has_text='Milestone number: #M1 → #M2')).to_be_visible()
    expect(page.locator('.task-permanent-reference')).to_have_text('Card #C01')
    expect(page.get_by_label('Milestone number (#M)',exact=True)).to_have_count(0)
    page.get_by_role('button',name='Close card',exact=True).click()
    sidebar.get_by_label('Task name 1',exact=True).press('Alt+ArrowUp')
    expect(rows.first).to_have_attribute('data-id','1')
    expect(child).to_contain_text('◇ #M1 Epic')
    page.reload()
    expect(number).to_have_text('M1:')
    assert page.locator('.task-card').evaluate_all('cards => cards.map(card => Number(card.dataset.id))') == [4,3,5,6]


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_sidebar_milestone_creation_filter_and_done_archive(workspace_page):
    from playwright.sync_api import expect
    _, page, url, ws = workspace_page
    long_title = 'A long milestone name for the shared project plan and a second phase'

    def change(**data):
        return ws.tasks.mutate({'revision': ws.tasks.read()['revision'], **data})

    change(action='create', title=long_title, milestone=True)
    change(action='create', title='Second milestone', milestone=True)
    change(action='create', title='Shipped', status='done', parent_id=1)
    change(action='create', title='Accepted', status='done', parent_id=1)
    change(action='create', title='Outside this filter', status='done', parent_id=2)
    change(action='create', title='Implementation', status='in_progress', parent_id=3)
    change(action='create', title='Review', status='to_review', parent_id=1)
    page.goto(url)
    page.locator('#tasks-open').click()
    sidebar = page.locator('#task-sidebar')
    def row(id):
        return sidebar.locator(f'.task-outline-row[data-id="{id}"]')

    expect(page.locator('.task-card')).to_have_count(5)
    expect(row(6).locator('.task-outline-symbol')).to_have_text('◐')
    expect(row(7).locator('.task-outline-symbol')).to_have_text('◎')
    expect(row(6).locator('.task-outline-symbol')).to_have_attribute('title', 'In progress → To review')
    expect(row(7).locator('.task-outline-symbol')).to_have_attribute('title', 'To review → Done')
    row(2).hover(position={'x': 110, 'y': 5})
    add = sidebar.get_by_role('button', name='Add milestone', exact=True)
    expect(add.locator('svg')).to_be_visible()
    assert add.inner_text() == ''
    add.click()
    create = page.get_by_role('dialog', name='New milestone')
    create.get_by_label('Title', exact=True).fill('Inserted from sidebar')
    create.get_by_role('button', name='Create', exact=True).click()
    expect(row(8).locator('.task-outline-prefix')).to_have_text('M2:')
    expect(row(2).locator('.task-outline-prefix')).to_have_text('M3:')
    expect(page.locator('.task-card')).to_have_count(5)

    filter_button = page.get_by_role('button', name='Filter by milestone', exact=True)
    filter_button.click()
    options = page.get_by_role('group', name='Milestone filters')
    option = options.get_by_role('button', name=f'M1: {long_title}', exact=True)
    expect(option).to_have_attribute('title', f'M1: {long_title}')
    option.click()
    expect(page.locator('.task-card')).to_have_count(4)
    expect(option).to_be_focused()
    expect(filter_button).to_have_attribute('title', f'M1: {long_title}')
    assert filter_button.locator('span').last.evaluate(
        'label => label.scrollWidth > label.clientWidth && getComputedStyle(label).textOverflow === "ellipsis"')
    assert filter_button.bounding_box()['width'] < 215

    done = page.get_by_role('region', name='Done')
    done.get_by_role('button', name='Archive all done tasks').click()
    expect(done.locator('.task-card')).to_have_count(0)
    expect(done.get_by_role('button', name='Archive all done tasks')).to_be_disabled()
    expect(sidebar.locator('.task-outline-row[data-id="3"].task-outline-context')).to_have_attribute('data-archived', 'true')
    expect(row(4)).to_have_count(0)
    expect(row(6)).to_have_attribute('data-depth', '2')
    expect(row(5)).to_have_attribute('data-archived', 'false')
    filter_button.click()
    expect(option).to_have_attribute('aria-pressed', 'true')
    option.click()
    expect(done.locator('.task-card')).to_have_count(1)
    expect(done.get_by_role('article', name='Outside this filter')).to_be_visible()

    page.get_by_label('Show archive', exact=True).check()
    expect(done.locator('.task-card')).to_have_count(2)
    expect(row(6)).to_be_visible()
    sidebar.get_by_role('button', name='Archived tasks in sidebar', exact=True).click()
    expect(row(4)).to_have_attribute('data-archived', 'true')
    row(3).locator('.task-outline-reference').click()
    page.get_by_role('button', name='Restore', exact=True).click()
    expect(row(3)).to_have_attribute('data-archived', 'false')
    expect(done.locator('.task-card')).to_have_count(1)


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_filter_multiple_milestones_and_add_to_an_empty_column(workspace_page):
    from playwright.sync_api import expect
    _, page, url, ws = workspace_page

    def create(title, **fields):
        ws.tasks.mutate(dict(action='create', revision=ws.tasks.read()['revision'], title=title, **fields))

    create('Design', milestone=True)
    create('Release', milestone=True)
    create('Design task', parent_id=1)
    create('Release task', parent_id=2)
    create('Unassigned task')
    page.goto(url)
    page.locator('#tasks-open').click()
    titles = page.locator('.task-card-title')
    expect(titles).to_have_count(3)

    sidebar = page.locator('#task-sidebar')
    design = sidebar.get_by_role('button', name='Filter board by #M1')
    release = sidebar.get_by_role('button', name='Filter board by #M2')
    design.click()
    expect(titles).to_have_text(['Design task'])
    filter_button = page.get_by_role('button', name='Filter by milestone', exact=True)
    filter_button.click()
    options = page.get_by_role('group', name='Milestone filters')
    design_option = options.get_by_role('button', name='M1: Design')
    release_option = options.get_by_role('button', name='M2: Release')
    expect(design_option).to_have_attribute('aria-pressed', 'true')
    release_option.press('Enter')
    expect(release_option).to_be_focused()
    expect(release_option).to_have_attribute('aria-pressed', 'true')
    expect(release).to_have_attribute('aria-pressed', 'true')
    expect(filter_button).to_have_text('◇2 milestones')
    expect(titles).to_have_text(['Design task', 'Release task'])

    release_option.press('Escape')
    expect(filter_button).to_be_focused()
    expect(options).to_be_hidden()
    review = page.get_by_role('region', name='To review')
    add = review.get_by_role('button', name='Add task to To review')
    expect(add).to_have_text('+ Add task')
    assert add.bounding_box()['height'] == 24
    assert add.bounding_box()['width'] < review.bounding_box()['width'] / 2
    add.click()
    dialog = page.get_by_role('dialog', name='New task')
    dialog.get_by_label('Title').fill('Review checklist')
    milestone = dialog.get_by_role('combobox', name='Milestone')
    expect(milestone).to_have_value('')
    milestone.select_option('2')
    dialog.get_by_role('button', name='Create').click()
    expect(review.get_by_role('article', name='Review checklist')).to_be_visible()
    assert ws.tasks.read()['cards'][-1]['milestone_id'] == 2

    design.click()
    expect(titles).to_have_text(['Release task', 'Review checklist'])
    filter_button.click()
    options.get_by_role('button', name='All milestones').click()
    expect(release).to_have_attribute('aria-pressed', 'false')
    expect(titles).to_have_count(4)


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_sidebar_selection_moves_board_cards_together_without_shifting_layout(workspace_page):
    from playwright.sync_api import expect
    _, page, url, ws = workspace_page

    def change(**data):
        return ws.tasks.mutate(dict(revision=ws.tasks.read()['revision'], **data))

    change(action='create', title='Release', milestone=True)
    change(action='create', title='First', parent_id=1)
    change(action='create', title='Second', parent_id=1, status='in_progress')
    change(action='create', title='Other', status='done')
    page.goto(url)
    page.locator('#tasks-open').click()
    sidebar = page.locator('#task-sidebar')
    first = page.get_by_role('article', name='First', exact=True)
    second = page.get_by_role('article', name='Second', exact=True)
    other = page.get_by_role('article', name='Other', exact=True)
    first_row = sidebar.locator('.task-outline-row[data-id="2"]')
    second_row = sidebar.locator('.task-outline-row[data-id="3"]')
    first_row.hover()
    expect(first).to_have_class('task-card sidebar-hover')
    page.get_by_label('Search cards').hover()
    expect(first).to_have_class('task-card')
    original = first.bounding_box()
    first_row.click(modifiers=['Control'])
    second_row.click(modifiers=['Control'])
    expect(first).to_have_attribute('aria-selected', 'true')
    expect(second).to_have_attribute('aria-selected', 'true')
    expect(page.locator('.task-bulk')).to_contain_text('2 selected')
    assert first.bounding_box() == original
    first.drag_to(other, target_position={'x': 12, 'y': 10})
    done = page.locator('.task-lane[data-status="done"]')
    expect(done.locator('.task-card-title')).to_have_text(['First', 'Second', 'Other'])
    expect(first).to_have_attribute('aria-selected', 'true')
    expect(second).to_have_attribute('aria-selected', 'true')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_sidebar_milestone_filter_and_board_order_and_insertion(workspace_page):
    from playwright.sync_api import expect
    _, page, url, ws = workspace_page

    def change(**data):
        return ws.tasks.mutate(dict(revision=ws.tasks.read()['revision'], **data))

    change(action='create', title='Plan', milestone=True)
    change(action='create', title='Other')
    change(action='create', title='Second', parent_id=1)
    change(action='create', title='First', parent_id=1)
    change(action='outline_move', ids=[4], parent_id=1, before=3)
    page.goto(url)
    page.locator('#tasks-open').click()
    sidebar = page.locator('#task-sidebar')
    titles = page.locator('.task-lane[data-status="backlog"] .task-card-title')
    diamond = sidebar.get_by_role('button', name='Filter board by #M1')
    clear = sidebar.get_by_role('button', name='Clear milestone filter')
    expect(clear).to_be_disabled()
    expect(titles).to_have_text(['Other', 'Second', 'First'])
    open_milestone = sidebar.get_by_role('button', name='Open #M1: Plan')
    open_milestone.press('Enter')
    expect(page.get_by_role('dialog', name='M1: Plan')).to_be_visible()
    page.get_by_role('button', name='Close card').click()
    expect(open_milestone).to_be_focused()
    diamond.click()
    expect(titles).to_have_text(['Second', 'First'])
    expect(diamond).to_have_attribute('aria-pressed', 'true')
    diamond.click()
    expect(titles).to_have_count(3)
    diamond.click()
    clear.click()
    expect(titles).to_have_count(3)
    page.get_by_role('button', name='Order by sidebar').click()
    expect(titles).to_have_text(['First', 'Second', 'Other'])
    page.get_by_role('article', name='Other', exact=True).drag_to(
        page.get_by_role('article', name='First', exact=True), target_position={'x': 12, 'y': 10})
    expect(titles).to_have_text(['Other', 'First', 'Second'])
    diamond.click()
    between = page.get_by_role('button', name='Add task before Second')
    between.hover()
    between.click()
    page.get_by_role('textbox', name='Title').fill('In between')
    page.get_by_role('button', name='Create', exact=True).click()
    expect(titles).to_have_text(['First', 'In between', 'Second'])
    diamond.click()
    expect(titles).to_have_text(['Other', 'First', 'In between', 'Second'])
    page.reload()
    expect(titles).to_have_text(['Other', 'First', 'In between', 'Second'])
    assert next(card for card in ws.tasks.read()['cards'] if card['title'] == 'In between')['milestone_id'] == 1


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_task_comment_attaches_previews_and_downloads_files(workspace_page):
    import base64
    import io
    from PIL import Image
    from playwright.sync_api import expect
    _, page, url, ws = workspace_page
    ws.tasks.mutate(dict(action='create', title='Task', revision=0))
    ws.tasks.mutate(dict(action='update', ids=[1], changes={'description': '**TODO**: review this card'}, revision=1))
    picture = io.BytesIO()
    Image.new('RGB', (8, 8), 'purple').save(picture, format='PNG')

    page.goto(url)
    page.locator('#tasks-open').click()
    card = page.get_by_role('article', name='Task', exact=True)
    card.click()
    detail = page.locator('.task-detail')
    expect(detail.locator('.task-description-preview .md-marker[data-kind=TODO]')).to_have_text('TODO')
    attach = detail.get_by_role('button', name='Attach files to card comment')
    for theme in ('light', 'dark'):
        page.evaluate('(theme)=>document.documentElement.dataset.theme=theme', theme)
        page.set_viewport_size({'width': 390, 'height': 700})
        icon = attach.locator('svg').bounding_box()
        assert (icon['width'], icon['height']) == pytest.approx((18, 18), abs=0.25)
        assert detail.evaluate('el=>el.scrollWidth<=el.clientWidth+1')
    with page.expect_file_chooser() as chooser:
        attach.click()
    chooser.value.set_files({'name': 'notes.txt', 'mimeType': 'text/plain', 'buffer': b'April notes'})
    expect(detail.get_by_role('button', name='Remove pending notes.txt')).to_be_visible()
    body = detail.get_by_role('textbox', name='Comment', exact=True)
    body.fill('TODO: check this screenshot')
    body.evaluate("""(el, encoded) => {
      const bytes = Uint8Array.from(atob(encoded), c => c.charCodeAt(0));
      const transfer = new DataTransfer();
      transfer.items.add(new File([bytes], 'clipboard.png', {type: 'image/png'}));
      const event = new ClipboardEvent('paste', {bubbles: true, cancelable: true});
      Object.defineProperty(event, 'clipboardData', {value: transfer});
      el.dispatchEvent(event);
    }""", base64.b64encode(picture.getvalue()).decode())
    expect(detail.locator('.pending-file img')).to_be_visible()
    detail.get_by_role('button',name='screenshot-',exact=False).filter(has_not_text='×').click()
    rename=page.get_by_role('dialog',name='Rename attachment')
    rename.get_by_role('textbox',name='Name').fill('review.png')
    rename.get_by_role('button',name='Save name').click()
    detail.get_by_role('button', name='Close card').click()
    card.click()
    expect(detail.get_by_role('button', name='Remove pending review.png')).to_be_visible()
    expect(body).to_have_value('TODO: check this screenshot')
    detail.get_by_role('button', name='Comment', exact=True).click()
    comment = detail.locator('.task-comment')
    expect(comment).to_have_count(1)
    expect(comment.locator('.md-marker[data-kind=TODO]')).to_have_text('TODO')
    comment.get_by_text('Preview review.png').click()
    expect(comment.get_by_role('img', name='review.png')).to_be_visible()
    page.wait_for_function("document.querySelector('.task-comment img').naturalWidth === 8")
    with page.expect_download() as download:
        comment.get_by_role('button', name='notes.txt').click()
    assert download.value.suggested_filename == 'notes.txt'
    assert download.value.path().read_bytes() == b'April notes'
    comment.get_by_role('button', name='Delete comment').click()
    expect(comment).to_have_count(0)
    assert not list(ws.attachments.directory.iterdir())


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_task_shortcut_and_branch_hover(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    (root / 'plan.md').write_text('# Plan')
    def create(title, **fields):
        ws.tasks.mutate(dict(action='create', title=title, revision=ws.tasks.read()['revision'], **fields))
    create('Release', milestone=True)
    create('Prepare', parent_id=1)
    create('Review', parent_id=2, status='done')
    create('Sibling', parent_id=1)
    create('Independent')
    page.goto(url)
    page.keyboard.press('Alt+t')
    board = page.locator('.task-board')
    expect(board).to_be_visible()
    page.keyboard.press('Alt+t')
    expect(board).to_have_count(0)
    page.locator('.file-entry[data-path="plan.md"]').click()
    editor = page.locator('.cm-content')
    editor.click()
    editor.press('End')
    page.keyboard.insert_text(' draft')
    page.keyboard.press('Alt+t')
    expect(board).to_be_visible()
    page.set_viewport_size({'width': 1100, 'height': 700})
    sidebar = page.locator('#task-sidebar')
    matches = board.locator('.sidebar-hover .task-card-title')
    sidebar.locator('[data-id="1"]').hover()
    expect(matches).to_have_text(['Prepare', 'Sibling', 'Review'])
    sidebar.locator('[data-id="2"]').hover()
    expect(matches).to_have_text(['Prepare', 'Review'])
    expect(board.locator('.task-edge-right')).to_have_text('→ 1')
    expect(board.locator('.task-edge-right')).to_be_visible()
    board.locator('.task-lanes').evaluate('node => node.scrollLeft = node.scrollWidth')
    expect(board.locator('.task-edge-right')).to_be_hidden()
    expect(board.locator('.task-edge-left')).to_be_visible()
    board.get_by_role('article', name='Review', exact=True).click()
    page.get_by_label('Description', exact=True).fill('Ready to ship')
    description = page.get_by_label('Description', exact=True)
    description.evaluate('field => field.setSelectionRange(2, 5)')
    page.keyboard.press('Alt+t')
    expect(editor).to_contain_text('Plan draft')
    expect(editor).to_be_focused()
    assert (root / 'plan.md').read_text() == '# Plan'
    page.keyboard.press('Alt+t')
    expect(description).to_have_value('Ready to ship')
    expect(description).to_be_focused()
    assert description.evaluate('field => [field.selectionStart, field.selectionEnd]') == [2, 5]

    assert next(c for c in ws.tasks.read()['cards'] if c['title'] == 'Review')['description'] == 'Ready to ship'
