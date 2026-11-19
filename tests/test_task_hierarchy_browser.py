import os

import pytest
from test_requested_features import workspace_page

pytestmark = [pytest.mark.browser, pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]


def seed(ws):
    def change(**data):
        return ws.tasks.mutate(dict(revision=ws.tasks.read()['revision'],author='Agent',**data))
    for title in ('Later epic','First epic','Build board','Review changes','Write docs'):
        change(action='create',title=title)
    change(action='update',ids=[2],changes={'milestone':True})
    change(action='update',ids=[1],changes={'milestone':True})
    change(action='outline_move',ids=[3,4],parent_id=2)
    change(action='create',title='Keyboard flow',parent_id=3)
    return change


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_outline_keyboard_edits_hierarchy_details_and_sidebar_restore(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    (root/'notes.md').write_text('Notes for planning.\n')
    change=seed(ws)
    page.goto(url);page.locator('.file-entry[data-path="notes.md"]').click()
    expect(page.locator('#thread-search')).to_be_visible()
    page.locator('#tasks-open').click()
    sidebar=page.locator('#task-sidebar')
    expect(sidebar).to_be_visible()
    expect(page.locator('#thread-search')).to_be_hidden()
    assert sidebar.locator('.task-outline-row').evaluate_all('(rows)=>rows.map(r=>+r.dataset.id)')==[2,3,6,4,1,5]
    expect(sidebar.locator('.task-outline-row[data-id="2"] .task-outline-prefix')).to_have_text('M1:')
    expect(page.locator('.task-card[data-id="2"]')).to_have_count(0)
    name=sidebar.get_by_label('Task name 4',exact=True)
    name.fill('Review the changes');name.press('Enter')
    expect(page.locator('.task-card[data-id="4"]')).to_contain_text('Review the changes')
    name.focus();name.press('Tab')
    expect(sidebar.locator('.task-outline-row[data-id="4"]')).to_have_attribute('data-depth','2')
    assert next(c for c in ws.tasks.read()['cards'] if c['id']==4)['parent_id']==3
    name.press('Shift+Tab')
    expect(sidebar.locator('.task-outline-row[data-id="4"]')).to_have_attribute('data-depth','1')
    name.press('Alt+ArrowUp')
    expect(sidebar.locator('.task-outline-row').nth(1)).to_have_attribute('data-id','4')
    assert sidebar.locator('.task-outline-row').evaluate_all('(rows)=>rows.map(r=>+r.dataset.id)')==[2,4,3,6,1,5]
    # Inline drafts and caret survive unrelated agent updates without replacing rows.
    name.fill('Unsent inline draft');name.evaluate('(e)=>{window.keptTaskName=e;e.setSelectionRange(7,7);}')
    change(action='create',title='External task')
    expect(sidebar.get_by_label('Task name 7',exact=True)).to_have_value('External task')
    expect(name).to_have_value('Unsent inline draft')
    assert name.evaluate('(e)=>e===window.keptTaskName && e.selectionStart===7 && document.activeElement===e')
    name.press('Escape')
    expect(name).to_have_value('Review the changes')
    # A row click opens the centered card popup above the board and outline.
    sidebar.locator('.task-outline-row[data-id="3"]').click(position={'x':110,'y':16})
    detail=page.locator('.task-detail')
    expect(detail).to_be_visible();expect(sidebar).to_be_visible()
    assert detail.evaluate('e=>e.matches(":modal")')
    page.get_by_label('Description',exact=True).fill('Keep this parent draft')
    checklist=page.locator('.task-checklist')
    expect(checklist.get_by_label('Task name 6',exact=True)).to_have_value('Keyboard flow')
    checklist.get_by_role('button',name='+ Add subitem',exact=True).click()
    page.locator('.task-dialog:not(.task-detail)').get_by_label('Title',exact=True).fill('Added from card checklist')
    page.get_by_role('button',name='Create',exact=True).click()
    expect(page.locator('.task-dialog')).to_have_count(1)
    expect(checklist.get_by_label('Task name 8',exact=True)).to_have_value('Added from card checklist')
    page.evaluate("""() => {
        window.maxTaskDetails = 1;
        new MutationObserver(() => {
            const details = document.querySelectorAll('.task-detail').length;
            window.maxTaskDetails = Math.max(window.maxTaskDetails, details);
        }).observe(document.body, {childList: true});
    }""")
    checklist.get_by_role('button',name='Open #C06',exact=True).click()
    expect(page.get_by_role('heading',name='Keyboard flow',exact=True)).to_be_visible()
    assert page.evaluate('window.maxTaskDetails') == 1
    expect(detail).to_have_count(1)
    page.get_by_role('button',name='Close card',exact=True).click()
    sidebar.get_by_role('button',name='Open #C03',exact=True).click()
    expect(page.get_by_label('Description',exact=True)).to_have_value('Keep this parent draft')
    page.get_by_role('button',name='Close card',exact=True).click()
    expect(page.locator('.task-detail')).to_have_count(0)
    # Keyboard creation adds a full card subitem, also visible on the board.
    name=sidebar.get_by_label('Task name 3',exact=True);name.focus();name.press('Control+Enter')
    page.locator('.task-dialog:not(.task-detail)').get_by_label('Title',exact=True).fill('New checklist item')
    page.get_by_role('button',name='Create',exact=True).click()
    expect(sidebar.locator('.task-outline-row[data-id="9"]')).to_have_attribute('data-depth','2')
    expect(page.locator('.task-card[data-id="9"]')).to_contain_text('New checklist item')
    page.get_by_role('button',name='Hide task list',exact=True).click()
    expect(sidebar).to_be_hidden()
    page.get_by_role('button',name='Show task list',exact=True).click()
    expect(sidebar).to_be_visible()
    resize=page.get_by_role('separator',name='Resize task list');resize.focus();resize.press('ArrowLeft')
    width=resize.get_attribute('aria-valuenow')
    page.locator('.file-entry[data-path="notes.md"]').click()
    expect(sidebar).to_be_hidden();expect(page.locator('#thread-search')).to_be_visible()
    expect(page.get_by_role('button',name='Hide discussions',exact=True)).to_be_visible()
    page.locator('.tab-name',has_text='Tasks').click()
    expect(sidebar.get_by_label('Task name 4',exact=True)).to_have_value('Review the changes')
    page.reload()
    expect(page.get_by_role('separator',name='Resize task list')).to_have_attribute('aria-valuenow',width)
    expect(sidebar.locator('.task-outline-row[data-id="9"]')).to_have_attribute('data-depth','2')


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_outline_dragging_reassigns_reorders_nests_and_shares_multiselection(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    seed(ws)
    page.goto(url);page.locator('#tasks-open').click()
    sidebar=page.locator('#task-sidebar')
    row=lambda id: sidebar.locator(f'.task-outline-row[data-id="{id}"]')
    # Drop a task under a milestone: its entire subtree follows.
    row(3).drag_to(row(1),source_position={'x':8,'y':16},target_position={'x':90,'y':16})
    expect(row(3)).to_have_attribute('data-depth','1')
    expect(page.locator('.task-card[data-id="3"] .task-assignment')).to_contain_text('#M2')
    assert next(c for c in ws.tasks.read()['cards'] if c['id']==6)['milestone_id']==1
    # Drag vertically to reorder direct siblings, then horizontally to nest/outdent.
    row(5).drag_to(row(1),source_position={'x':8,'y':16},target_position={'x':90,'y':16})
    expect(row(5)).to_have_attribute('data-depth','1')
    row(5).drag_to(row(3),source_position={'x':30,'y':16},target_position={'x':30,'y':4})
    expect(sidebar.locator('.task-outline-row').nth(3)).to_have_attribute('data-id','5')
    assert sidebar.locator('.task-outline-row').evaluate_all('(rows)=>rows.map(r=>+r.dataset.id)')==[2,4,1,5,3,6]
    # Same blade dragged to the right indents under its preceding sibling.
    row(3).drag_to(row(3),source_position={'x':30,'y':16},target_position={'x':100,'y':16})
    expect(row(3)).to_have_attribute('data-depth','2')
    row(3).drag_to(row(3),source_position={'x':100,'y':16},target_position={'x':67,'y':16})
    expect(row(3)).to_have_attribute('data-depth','1')
    # Checklists reuse draggable blades and clickable permanent card references.
    row(1).click(position={'x':110,'y':16})
    checklist=page.locator('.task-checklist')
    first=checklist.locator('.task-outline-row[data-id="5"]');second=checklist.locator('.task-outline-row[data-id="3"]')
    second.drag_to(first,source_position={'x':8,'y':16},target_position={'x':8,'y':4})
    expect(checklist.locator('.task-outline-row').first).to_have_attribute('data-id','3')
    assert checklist.locator('.task-outline-row').evaluate_all('(rows)=>rows.map(r=>+r.dataset.id)')==[3,6,5]
    checklist.get_by_role('button',name='Open #C06',exact=True).click()
    expect(page.locator('.task-dialog h2')).to_have_attribute('aria-label','Keyboard flow')
    page.get_by_role('button',name='Cancel',exact=True).click()
    # Ctrl+click selections are shared with the Kanban action bar and context menu.
    row(3).click(modifiers=['Control'],position={'x':8,'y':16})
    row(5).click(modifiers=['Control'],position={'x':8,'y':16})
    expect(page.locator('.task-bulk')).to_contain_text('2 selected')
    expect(page.locator('.task-card[data-id="3"]')).to_have_attribute('aria-selected','true')
    row(3).click(button='right',position={'x':8,'y':16})
    menu=page.get_by_role('menu',name='Selected task actions')
    menu.get_by_role('menuitem',name='Assign to M1: First epic',exact=True).click()
    expect(page.locator('.task-card[data-id="5"] .task-assignment')).to_contain_text('#M1')
    assert next(c for c in ws.tasks.read()['cards'] if c['id']==6)['milestone_id']==2
    row(5).click(button='right',position={'x':8,'y':16})
    menu.get_by_role('menuitem',name='Archive',exact=True).click()
    expect(row(5)).to_have_attribute('data-archived','true')
    expect(page.locator('.task-card[data-id="5"]')).to_have_count(0)
    page.get_by_label('Show archive',exact=True).check()
    expect(row(5)).to_be_visible()
    row(5).click(button='right',position={'x':8,'y':16})
    menu.get_by_role('menuitem',name='Delete',exact=True).click()
    page.get_by_role('button',name='Delete permanently',exact=True).click()
    expect(row(5)).to_have_count(0)


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_outline_conflicts_archived_visibility_and_theme_layout(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    change=seed(ws)
    page.goto(url);page.locator('#tasks-open').click()
    sidebar=page.locator('#task-sidebar');name=sidebar.get_by_label('Task name 3',exact=True)
    name.fill('My unsent title')
    change(action='update',ids=[3],changes={'title':'Agent title'})
    expect(page.locator('.task-card[data-id="3"]')).to_contain_text('Agent title')
    expect(name).to_have_value('My unsent title')
    name.press('Enter')
    expect(sidebar.locator('.task-outline-status')).to_contain_text('Saved title: Agent title')
    sidebar.get_by_role('button',name='Keep my title using this revision',exact=True).click()
    expect(page.locator('.task-card[data-id="3"]')).to_contain_text('My unsent title')
    change(action='update',ids=[2],changes={'archived':True})
    expect(sidebar.locator('.task-outline-row[data-id="2"]')).to_have_attribute('data-archived','true')
    expect(name).to_be_visible()
    for theme in ('light','dark'):
        page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
        page.set_viewport_size({'width':800,'height':800})
        expect(sidebar).to_be_visible()
        row=sidebar.locator('.task-outline-row[data-id="3"]')
        fold=row.get_by_role('button',name='Collapse My unsent title',exact=True)
        expect(fold).to_be_visible()
        assert row.bounding_box()['height']<=38
        assert fold.bounding_box()['width'] == 24
        assert fold.bounding_box()['x']+fold.bounding_box()['width']<=sidebar.bounding_box()['x']+sidebar.bounding_box()['width']


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('surface', ['kanban', 'sidebar', 'checklist'])
def test_drag_preview_slides_neighbors_and_saves_only_on_drop(workspace_page, surface):
    from playwright.sync_api import expect
    _, page, url, ws = workspace_page
    for title, status, parent in (
        ('Plan', 'backlog', None), ('First', 'in_progress', 1),
        ('Second', 'in_progress', 1), ('Move me', 'backlog', 1), ('Next', 'backlog', None),
    ):
        ws.tasks.mutate(dict(action='create', title=title, status=status, parent_id=parent,
                             revision=ws.tasks.read()['revision']))
    page.goto(url)
    page.locator('#tasks-open').click()
    if surface == 'kanban':
        group = page.locator('.task-lane[data-status="in_progress"]')
        source = page.locator('.task-card[data-id="4"]')
        row = '.task-card'
    elif surface == 'sidebar':
        group = page.locator('#task-sidebar .task-outline-list')
        source = group.locator('[data-id="4"]')
        row = '.task-outline-row'
    else:
        with page.expect_response(lambda response: '/api/tasks/1/activity' in response.url):
            page.locator('.task-card[data-id="1"]').click()
        group = page.locator('.task-checklist .task-outline-list')
        source = group.locator('[data-id="4"]')
        row = '.task-outline-row'
    first = group.locator('[data-id="2"]')
    gap = group.locator('.task-drop-preview')
    start = source.bounding_box()
    destination = first.bounding_box()
    x, y = destination['x'] + 8, destination['y'] + 7

    def start_drag():
        page.mouse.move(start['x'] + 8, start['y'] + 17)
        page.mouse.down()
        page.mouse.move(start['x'] + 8, start['y'] + 5, steps=3)

    def hover_destination():
        page.mouse.move(x, y)
        page.mouse.move(x, y)
        expect(gap).to_be_visible()
        if surface != 'kanban':
            depth = 1 if surface == 'sidebar' else 0
            expect(group).to_have_attribute('data-task-drop-depth', str(depth))
            expect(gap).to_have_css('margin-inline-start', f'{16 * depth}px')
            assert group.evaluate("list => getComputedStyle(list, '::after').borderInlineEndWidth") == '1px'

    before = ws.tasks.read()
    start_drag()
    group.evaluate("""(group) => {
        const items = [...group.querySelectorAll('[data-id="2"],[data-id="3"]')];
        const positions = () => items.map(item => item.getBoundingClientRect().top);
        const settled = () => !items.some(item => item.getAnimations().length);
        const initial = positions();
        window.dragMotion = {initial, frames: [], end: null};
        const sample = () => {
            const current = positions();
            window.dragMotion.frames.push(current);
            if (settled() && current[0] > initial[0] + 5) window.dragMotion.end = current;
            else if (window.dragMotion.frames.length < 180) requestAnimationFrame(sample);
        };
        requestAnimationFrame(sample);
    }""")
    hover_destination()
    page.wait_for_function('() => window.dragMotion.end', timeout=5000)
    motion = page.evaluate('window.dragMotion')
    for index in (0, 1):
        assert motion['end'][index] > motion['initial'][index] + 20
        assert any(motion['initial'][index] + 1 < frame[index] < motion['end'][index] - 1
                   for frame in motion['frames'])
    assert ws.tasks.read() == before

    page.mouse.move(8, 36)
    page.mouse.up()
    expect(gap).to_have_count(0)
    assert group.get_attribute('data-task-drop-depth') is None
    expect(source).to_be_visible()
    page.wait_for_function('() => !document.getAnimations().some(a => a.effect.target?.matches?.(".task-card,.task-outline-row"))')
    assert ws.tasks.read() == before

    page.emulate_media(reduced_motion='reduce')
    start_drag()
    hover_destination()
    assert first.evaluate('item => item.getAnimations().length') == 0
    page.mouse.up()
    expect(gap).to_have_count(0)
    expect(group.locator(row).nth(1 if surface == 'sidebar' else 0)).to_have_attribute('data-id', '4')
    assert ws.tasks.read()['revision'] == before['revision'] + 1


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('surface', ['sidebar', 'checklist'])
def test_task_list_click_rename_caret_and_branch_toggle(workspace_page, surface):
    from playwright.sync_api import expect
    _, page, url, ws = workspace_page
    for title, parent_id in (('Plan', None), ('Editable name', 1), ('Nested work', 2)):
        ws.tasks.mutate(dict(action='create', title=title, parent_id=parent_id,
                             revision=ws.tasks.read()['revision']))
    page.goto(url)
    page.locator('#tasks-open').click()
    parent = page.get_by_role('article', name='Plan', exact=True)
    if surface == 'checklist':
        parent.click()
        group = page.get_by_role('region', name='Card tasks')
    else:
        group = page.locator('#task-sidebar')
    row = group.locator('.task-outline-row[data-id="2"]')
    descendant = group.locator('.task-outline-row[data-id="3"]')
    title_position = {'x': 135, 'y': 17}
    row.click(position=title_position)
    detail = page.get_by_role('dialog', name='Editable name', exact=True)
    expect(detail).to_be_visible()
    detail.get_by_role('button', name='Close card').click()
    if surface == 'checklist':
        parent.click()

    fold = row.get_by_role('button', name='Collapse Editable name', exact=True)
    assert fold.bounding_box()['width'] == 24
    assert fold.locator('svg').bounding_box()['width'] <= 12
    fold.click()
    expect(descendant).to_have_count(0)
    row.get_by_role('button', name='Expand Editable name', exact=True).click()
    expect(descendant).to_be_visible()
    expect(detail).to_have_count(0)
    assert ws.tasks.read()['revision'] == 3

    row.dblclick(position=title_position)
    name = row.get_by_label('Task name 2', exact=True)
    expect(name).to_be_focused()
    assert row.get_attribute('draggable') == 'false'
    name.evaluate('input => input.setSelectionRange(input.value.length, input.value.length)')
    name.click(position={'x': 1, 'y': 8})
    assert name.evaluate('input => input.selectionStart') == 0
    page.keyboard.insert_text('New ')
    expect(name).to_have_value('New Editable name')
    name.press('Enter')
    expect(page.get_by_role('article', name='New Editable name')).to_have_count(1)
    expect(detail).to_have_count(0)


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize(('surface', 'status', 'symbol', 'column'), [
    ('sidebar', 'in_progress', '◐', 'In progress'),
    ('checklist', 'to_review', '◎', 'To review'),
])
def test_task_list_checkbox_moves_card_to_done(workspace_page, surface, status, symbol, column):
    from playwright.sync_api import expect
    _, page, url, ws = workspace_page
    ws.tasks.mutate(dict(action='create', title='Plan', revision=0))
    ws.tasks.mutate(dict(action='create', title='Child task', parent_id=1, status=status, revision=1))
    page.goto(url)
    page.locator('#tasks-open').click()
    if surface == 'checklist':
        page.get_by_role('article', name='Plan', exact=True).click()
        group = page.get_by_role('region', name='Card tasks')
    else:
        group = page.locator('#task-sidebar')
    row = group.locator('.task-outline-row[data-id="2"]')
    check = row.get_by_role('checkbox', name='Complete Child task')
    name = row.get_by_role('textbox', name='Task name 2')
    indicator = row.locator('.task-outline-symbol')
    expect(check).to_have_css('opacity', '1')
    expect(indicator).to_have_text(symbol)
    expect(indicator).to_have_attribute('title', column)
    assert row.evaluate("""row => {
        const name = row.querySelector('.task-outline-name');
        const checkbox = row.querySelector('input[type=checkbox]');
        const indicator = row.querySelector('.task-outline-symbol');
        const label = row.querySelector('.task-outline-reference');
        return checkbox.getBoundingClientRect().right < name.getBoundingClientRect().left &&
            indicator.getBoundingClientRect().left >= name.getBoundingClientRect().right &&
            getComputedStyle(indicator).color === getComputedStyle(label).color &&
            parseFloat(getComputedStyle(indicator).fontSize) < parseFloat(getComputedStyle(name).fontSize);
    }""")

    def title_gap():
        return name.evaluate("""input => {
            const style = getComputedStyle(input);
            const context = document.createElement('canvas').getContext('2d');
            context.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
            const textEnd = input.getBoundingClientRect().left + parseFloat(style.paddingLeft)
                + context.measureText(input.value).width;
            return input.closest('.task-outline-row').querySelector('.task-outline-symbol')
                .getBoundingClientRect().left - textEnd;
        }""")

    assert 0 < title_gap() <= 8
    name.fill('Go')
    assert 0 < title_gap() <= 8
    page.evaluate("document.documentElement.dataset.theme = 'dark'")
    page.set_viewport_size({'width': 800, 'height': 800})
    name.fill('A long subtask title ' * 20)
    assert title_gap() < 0
    assert indicator.bounding_box()['x'] + indicator.bounding_box()['width'] <= (
        row.bounding_box()['x'] + row.bounding_box()['width']
    )
    name.press('Escape')
    expect(name).to_have_value('Child task')
    assert 0 < title_gap() <= 8

    card = page.locator('.task-card[data-id="2"]')
    done = page.locator('.task-lane[data-status="done"]')
    expect(done.locator(card)).to_have_count(0)
    check.check()
    expect(done.locator(card)).to_have_count(1)
    expect(check).to_be_enabled()
    expect(check).to_be_checked()
    expect(indicator).to_have_text('✓')
    assert [c['status'] for c in ws.tasks.read()['cards']] == ['backlog', 'done']

    check.uncheck()
    expect(page.locator('.task-lane[data-status="backlog"]').locator(card)).to_have_count(1)
    expect(indicator).to_have_text('◌')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('surface', ['sidebar', 'checklist'])
def test_drag_snaps_across_multiple_hierarchy_levels(workspace_page, surface):
    from playwright.sync_api import expect
    _, page, url, ws = workspace_page
    for title, parent in [('Plan', None), ('Group', 1), ('Parent', 2), ('Task', 3), ('Neighbor', 3)]:
        ws.tasks.mutate(dict(action='create', title=title, parent_id=parent, revision=ws.tasks.read()['revision']))
    page.goto(url)
    page.locator('#tasks-open').click()
    if surface == 'checklist':
        page.get_by_role('article', name='Plan', exact=True).click()
        group = page.locator('.task-checklist .task-outline-list')
        original_depth = 2
    else:
        group = page.locator('#task-sidebar .task-outline-list')
        original_depth = 3
    source = group.locator('.task-outline-row[data-id="4"]')
    neighbor = group.locator('.task-outline-row[data-id="5"]')
    expect(neighbor).to_have_attribute('data-depth', str(original_depth))
    start, target = source.bounding_box(), neighbor.bounding_box()
    start_x, start_y = start['x'] + 170, start['y'] + 16
    y = target['y'] + 16
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(start_x - 9, start_y)
    page.mouse.move(start_x - 47, y)
    page.mouse.move(start_x - 47, y)
    depth = original_depth - 2
    expect(group).to_have_attribute('data-task-drop-depth', str(depth))
    expect(group.locator('.task-drop-preview')).to_have_css('margin-inline-start', f'{16 * depth}px')
    assert next(card for card in ws.tasks.read()['cards'] if card['id'] == 4)['parent_id'] == 3
    page.mouse.up()
    expect(source).to_have_attribute('data-depth', str(depth))
    assert next(card for card in ws.tasks.read()['cards'] if card['id'] == 4)['parent_id'] == 1
    assert group.get_attribute('data-task-drop-depth') is None
