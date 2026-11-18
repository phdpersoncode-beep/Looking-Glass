import os

import pytest
from test_requested_features import workspace_page

pytestmark=[pytest.mark.browser,pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'),reason='Set LOOKING_GLASS_BROWSER')]


def seed(ws):
    def change(**data):return ws.tasks.mutate(dict(revision=ws.tasks.read()['revision'],author='Agent',**data))
    change(action='create',title='Release')
    change(action='update',ids=[1],changes={'milestone':True})
    change(action='create',title='Build the board',parent_id=1)
    change(action='create',title='Keyboard editing',parent_id=2)
    change(action='create',title='Check focus',parent_id=3)
    change(action='create',title='Write documentation')
    change(action='create',title='CLI examples',parent_id=5)
    return change


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_compact_metadata_and_header_icon_actions_save_archive_restore_delete(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    seed(ws)
    page.goto(url);page.locator('#tasks-open').click()
    page.locator('.task-card[data-id="5"]').click()
    popup=page.locator('.task-detail');toolbar=popup.get_by_role('toolbar',name='Card actions')
    status=popup.get_by_label('Status',exact=True);milestone=popup.get_by_label('Milestone',exact=True)
    expect(status.locator('option:checked')).to_have_text('◌ Backlog')
    expect(milestone.locator('option:checked')).to_have_text('◇ No milestone')
    title=popup.get_by_label('Title',exact=True)
    assert status.bounding_box()['y']>title.bounding_box()['y']+title.bounding_box()['height']
    assert abs(status.bounding_box()['y']-milestone.bounding_box()['y'])<2
    assert milestone.bounding_box()['x']>status.bounding_box()['x']+status.bounding_box()['width']
    assert status.bounding_box()['y']<popup.get_by_label('Description',exact=True).bounding_box()['y']
    assert status.bounding_box()['width']<=140 and milestone.bounding_box()['width']<=225
    expect(popup.locator('form .task-edit-actions')).to_have_count(0)
    expect(popup.get_by_role('heading',name='Tasks',exact=True)).to_be_visible()
    expect(popup.get_by_role('heading',name='Checklist',exact=True)).to_have_count(0)
    for name in ('Save','Cancel','Promote to milestone','Archive','Delete','Close card'):
        action=toolbar.get_by_role('button',name=name,exact=True)
        expect(action).to_be_visible();expect(action.locator('svg')).to_be_visible()
        assert action.get_attribute('title')
        assert action.inner_text()==''
    status.select_option('to_review');milestone.select_option('1')
    title.fill('Document the shared plan')
    toolbar.get_by_role('button',name='Save',exact=True).click()
    expect(popup).to_have_count(0)
    saved=next(c for c in ws.tasks.read()['cards'] if c['id']==5)
    assert saved['title']=='Document the shared plan' and saved['status']=='to_review' and saved['milestone_id']==1
    page.locator('.task-card[data-id="5"]').click()
    expect(status.locator('option:checked')).to_have_text('◎ To review')
    expect(milestone).to_have_value('1')
    toolbar.get_by_role('button',name='Archive',exact=True).click()
    expect(popup).to_have_count(0)
    page.get_by_label('Show archive',exact=True).check()
    page.locator('.task-card[data-id="5"]').click()
    toolbar.get_by_role('button',name='Restore',exact=True).click()
    expect(popup).to_have_count(0)
    page.get_by_label('Show archive',exact=True).uncheck()
    page.locator('.task-card[data-id="5"]').click()
    toolbar.get_by_role('button',name='Delete',exact=True).click()
    page.locator('.task-dialog:not(.task-detail)').get_by_role('button',name='Delete permanently',exact=True).click()
    expect(page.locator('.task-dialog')).to_have_count(0)
    expect(page.locator('.task-card[data-id="5"]')).to_have_count(0)
    # Deleting a parent retains its checklist items and lifts them.
    assert next(c for c in ws.tasks.read()['cards'] if c['id']==6)['parent_id']==1


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_collapse_expand_lists_are_independent_preserve_drafts_and_survive_polls(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    (root/'notes.md').write_text('Planning notes\n')
    change=seed(ws)
    page.goto(url);page.locator('#tasks-open').click()
    sidebar=page.locator('#task-sidebar')
    expect(sidebar.locator('.task-outline-row')).to_have_count(6)
    expect(sidebar.locator('.task-outline-fold')).to_have_count(0)
    before=ws.tasks.read()['revision']
    sidebar.get_by_role('button',name='Collapse all tasks',exact=True).click()
    expect(sidebar.locator('.task-outline-row')).to_have_count(2)
    assert sidebar.locator('.task-outline-row').evaluate_all('(rows)=>rows.map(r=>+r.dataset.id)')==[1,5]
    assert ws.tasks.read()['revision']==before
    page.locator('.task-card[data-id="2"]').click()
    popup=page.locator('.task-detail');tasks=popup.get_by_role('region',name='Card tasks',exact=True)
    expect(tasks.get_by_role('heading',name='Tasks',exact=True)).to_be_visible()
    expect(tasks.locator('.task-outline-row')).to_have_count(2)
    expect(tasks.locator('.task-outline-fold')).to_have_count(0)
    title=popup.get_by_label('Title',exact=True);title.fill('Keep the parent draft')
    tasks.get_by_role('button',name='Collapse all tasks',exact=True).focus()
    page.keyboard.press('Enter')
    expect(tasks.locator('.task-outline-row')).to_have_count(1)
    expect(title).to_have_value('Keep the parent draft')
    # Polling adds a deeper child while both views stay collapsed.
    change(action='create',title='New agent subitem',parent_id=3)
    expect(page.locator('.task-card[data-id="7"]')).to_have_count(1)
    expect(tasks.locator('.task-outline-row')).to_have_count(1)
    expect(sidebar.locator('.task-outline-row')).to_have_count(2)
    tasks.get_by_role('button',name='Expand all tasks',exact=True).click()
    expect(tasks.locator('.task-outline-row')).to_have_count(3)
    expect(title).to_have_value('Keep the parent draft')
    tasks.get_by_role('button',name='Collapse all tasks',exact=True).click()
    popup.get_by_role('button',name='Close card',exact=True).click()
    page.locator('.task-card[data-id="2"]').click()
    expect(tasks.locator('.task-outline-row')).to_have_count(1)
    expect(title).to_have_value('Keep the parent draft')
    popup.get_by_role('button',name='Close card',exact=True).click()
    # A different card starts expanded; its state does not affect the plan.
    page.locator('.task-card[data-id="1"]').click()
    expect(tasks.locator('.task-outline-row')).to_have_count(4)
    popup.get_by_role('button',name='Close card',exact=True).click()
    sidebar.get_by_role('button',name='Expand all tasks',exact=True).click()
    expect(sidebar.locator('.task-outline-row')).to_have_count(7)
    expect(page.locator('.task-card')).to_have_count(7)
    page.locator('.file-entry[data-path="notes.md"]').click()
    page.locator('.tab-name',has_text='Tasks').click()
    expect(sidebar.locator('.task-outline-row')).to_have_count(7)
    page.locator('.task-card[data-id="2"]').click()
    expect(tasks.locator('.task-outline-row')).to_have_count(1)


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_icon_toolbar_and_metadata_fit_light_dark_and_narrow_popups(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    seed(ws)
    page.goto(url);page.locator('#tasks-open').click();page.locator('.task-card[data-id="1"]').click()
    popup=page.locator('.task-detail')
    for theme in ('light','dark'):
        page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
        for width in (1440,800,390):
            page.set_viewport_size({'width':width,'height':800})
            popup.evaluate('e=>e.scrollTop=0')
            toolbar=popup.get_by_role('toolbar',name='Card actions')
            boxes=toolbar.locator('button').evaluate_all('(buttons)=>buttons.map(b=>{const r=b.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height};})')
            edge=popup.bounding_box()
            for index,box in enumerate(boxes):
                assert box['width']>=26 and box['height']>=26
                assert box['left']>=edge['x'] and box['right']<=edge['x']+edge['width']
                assert box['top']>=edge['y'] and box['bottom']<edge['y']+65
                if index:assert boxes[index-1]['right']<=box['left']
            status=popup.get_by_label('Status',exact=True).bounding_box();milestone=popup.get_by_label('Milestone',exact=True).bounding_box()
            assert abs(status['y']-milestone['y'])<2
            assert status['x']+status['width']<milestone['x']
            assert popup.evaluate('e=>e.scrollWidth<=e.clientWidth+1')
            expect(popup.get_by_label('Milestone number (#M)',exact=True)).to_have_value('1')
            expect(popup.get_by_role('button',name='Collapse all tasks',exact=True)).to_be_visible()
