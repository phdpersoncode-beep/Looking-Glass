import os

import pytest
from test_requested_features import workspace_page

pytestmark = [pytest.mark.browser, pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]


def seed(ws):
    def change(**data):
        return ws.tasks.mutate(dict(revision=ws.tasks.read()['revision'],author='Agent',**data))
    for title in ('Later epic','First epic','Build board','Review changes','Write docs'):
        change(action='create',title=title)
    change(action='update',ids=[1],changes={'milestone':True,'milestone_number':9})
    change(action='update',ids=[2],changes={'milestone':True,'milestone_number':2})
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
    expect(page.locator('.task-card[data-id="2"] .task-card-title')).to_have_text('M2: First epic')
    expect(page.locator('.task-card[data-id="2"] .task-reference')).to_have_count(0)
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
    # Pen opens the card inside the main pane, leaving the outline usable.
    sidebar.locator('.task-outline-row[data-id="3"]').hover()
    sidebar.get_by_role('button',name='Edit Build board',exact=True).click()
    detail=page.locator('.task-detail')
    expect(detail).to_be_visible();expect(sidebar).to_be_visible()
    assert detail.evaluate('e=>document.querySelector(".document-panel").contains(e)')
    page.get_by_label('Description',exact=True).fill('Keep this parent draft')
    checklist=page.locator('.task-checklist')
    expect(checklist.get_by_label('Task name 6',exact=True)).to_have_value('Keyboard flow')
    checklist.get_by_role('button',name='+ Add subitem',exact=True).click()
    page.locator('.task-dialog:not(.task-detail)').get_by_label('Title',exact=True).fill('Added from card checklist')
    page.get_by_role('button',name='Create',exact=True).click()
    expect(page.locator('.task-dialog')).to_have_count(1)
    expect(checklist.get_by_label('Task name 8',exact=True)).to_have_value('Added from card checklist')
    checklist.get_by_role('button',name='Open #C06',exact=True).click()
    expect(page.locator('.task-dialog h2')).to_have_text('Task · #C06')
    sidebar.get_by_role('button',name='Open #C03',exact=True).click()
    expect(page.get_by_label('Description',exact=True)).to_have_value('Keep this parent draft')
    page.get_by_role('button',name='Save',exact=True).click()
    # Keyboard creation adds a full card subitem, also visible on the board.
    name=sidebar.get_by_label('Task name 3',exact=True);name.focus();name.press('Control+Enter')
    page.get_by_label('Title',exact=True).fill('New checklist item')
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
    expect(page.locator('.task-card[data-id="3"] .task-assignment')).to_contain_text('#M9')
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
    row(3).drag_to(row(3),source_position={'x':100,'y':16},target_position={'x':30,'y':16})
    expect(row(3)).to_have_attribute('data-depth','1')
    # Checklists reuse draggable blades and clickable permanent card references.
    row(1).hover();sidebar.get_by_role('button',name='Edit Later epic',exact=True).click()
    checklist=page.locator('.task-checklist')
    first=checklist.locator('.task-outline-row[data-id="5"]');second=checklist.locator('.task-outline-row[data-id="3"]')
    second.drag_to(first,source_position={'x':8,'y':16},target_position={'x':8,'y':4})
    expect(checklist.locator('.task-outline-row').first).to_have_attribute('data-id','3')
    assert checklist.locator('.task-outline-row').evaluate_all('(rows)=>rows.map(r=>+r.dataset.id)')==[3,6,5]
    checklist.get_by_role('button',name='Open #C06',exact=True).click()
    expect(page.locator('.task-dialog h2')).to_have_text('Task · #C06')
    page.get_by_role('button',name='Cancel',exact=True).click()
    # Ctrl+click selections are shared with the Kanban action bar and context menu.
    row(3).click(modifiers=['Control'],position={'x':8,'y':16})
    row(5).click(modifiers=['Control'],position={'x':8,'y':16})
    expect(page.locator('.task-bulk')).to_contain_text('2 selected')
    expect(page.locator('.task-card[data-id="3"]')).to_have_attribute('aria-selected','true')
    row(3).click(button='right',position={'x':8,'y':16})
    menu=page.get_by_role('menu',name='Selected task actions')
    menu.get_by_role('menuitem',name='Assign to M2: First epic',exact=True).click()
    expect(page.locator('.task-card[data-id="5"] .task-assignment')).to_contain_text('#M2')
    assert next(c for c in ws.tasks.read()['cards'] if c['id']==6)['milestone_id']==2
    row(5).click(button='right',position={'x':8,'y':16})
    menu.get_by_role('menuitem',name='Archive',exact=True).click()
    expect(row(5)).to_have_count(0)
    page.get_by_label('Show archive',exact=True).check()
    expect(row(5)).to_be_visible()
    row(5).click(button='right',position={'x':8,'y':16})
    menu.get_by_role('menuitem',name='Delete',exact=True).click()
    page.get_by_role('button',name='Delete permanently',exact=True).click()
    expect(row(5)).to_have_count(0)


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_outline_conflicts_archived_context_and_theme_layout(workspace_page):
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
    expect(sidebar.locator('.task-outline-row[data-id="2"]')).to_have_class('task-outline-row task-outline-milestone task-outline-context')
    expect(name).to_be_visible()
    assert sidebar.get_by_label('Task name 2',exact=True).get_attribute('readonly') is not None
    for theme in ('light','dark'):
        page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
        page.set_viewport_size({'width':800,'height':800})
        expect(sidebar).to_be_visible()
        row=sidebar.locator('.task-outline-row[data-id="6"]');row.hover()
        pen=row.get_by_role('button',name='Edit Keyboard flow',exact=True)
        expect(pen).to_be_visible()
        assert row.bounding_box()['height']<=38
        assert pen.bounding_box()['x']+pen.bounding_box()['width']<=sidebar.bounding_box()['x']+sidebar.bounding_box()['width']
