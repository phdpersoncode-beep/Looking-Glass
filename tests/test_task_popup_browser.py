import os

import pytest
from test_requested_features import workspace_page

pytestmark = [pytest.mark.browser, pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_copy_permanent_card_reference_and_create_nested_tasks_inline(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    def change(**data):return ws.tasks.mutate(dict(revision=ws.tasks.read()['revision'],**data))
    change(action='create',title='Plan a release',milestone=True)
    change(action='create',title='One branch',parent_id=1)
    change(action='create',title='Existing child',parent_id=2)
    change(action='create',title='Following task',parent_id=1)
    change(action='create',title='Another card')
    chromium=page.context.browser.browser_type.name=='chromium'
    if chromium:
        page.context.grant_permissions(['clipboard-read','clipboard-write'])
    else:
        page.add_init_script("""() => {
          const write = navigator.clipboard.writeText.bind(navigator.clipboard);
          navigator.clipboard.writeText = async text => { await write(text); window.copiedCard = text; };
        }""")
    page.goto(url);page.locator('#tasks-open').click()
    copy=page.get_by_role('button',name='Copy card reference',exact=False)
    expect(copy).to_have_count(0)
    page.locator('#task-sidebar').get_by_role('button',name='Open #M1',exact=False).last.click()
    popup=page.locator('.task-detail')
    title=popup.get_by_role('textbox',name='Title',exact=True)
    expect(copy).to_have_count(1)
    expect(copy).to_have_accessible_name('Copy card reference #C01')
    assert copy.bounding_box()['y']>=title.bounding_box()['y']+title.bounding_box()['height']
    copy.click()
    expect(popup.locator('.task-permanent-reference [role=status]')).to_have_text('Copied')
    copied=page.evaluate('navigator.clipboard.readText()' if chromium else 'window.copiedCard')
    assert copied=='#C01'
    checklist=popup.get_by_role('region',name='Card tasks')
    branch=checklist.get_by_role('textbox',name='Task name 2',exact=True)
    branch.press('Control+Enter')
    draft=checklist.get_by_role('textbox',name='New task title')
    expect(draft).to_be_focused()
    expect(page.get_by_role('dialog')).to_have_count(1)
    existing=checklist.get_by_role('textbox',name='Task name 3',exact=True)
    following=checklist.get_by_role('textbox',name='Task name 4',exact=True)
    assert existing.bounding_box()['y']<draft.bounding_box()['y']<following.bounding_box()['y']
    draft.fill('Cancelled title');draft.press('Escape')
    expect(draft).to_have_count(0);expect(branch).to_be_focused()
    expect(popup).to_be_visible()
    following.press('Shift+Enter')
    expect(draft).to_be_focused()
    assert draft.bounding_box()['y']>following.bounding_box()['y']
    draft.fill('Survives retry')
    def fail_create(route):
        if route.request.method=='POST':
            route.fulfill(status=409,json={'error':'Tasks changed. Try again.'})
        else:
            route.continue_()
    page.route('**/api/tasks',fail_create)
    draft.press('Enter')
    expect(checklist.get_by_text('Tasks changed. Try again.',exact=True)).to_be_visible()
    expect(draft).to_have_value('Survives retry')
    page.unroute('**/api/tasks',fail_create)
    popup.get_by_role('button',name='Close card',exact=True).click()
    expect(popup).to_have_count(0)
    page.locator('#task-sidebar').get_by_role('button',name='Open #M1',exact=False).last.click()
    expect(draft).to_have_value('Survives retry')
    draft.press('Enter')
    expect(draft).to_have_count(0)
    expect(checklist.get_by_role('textbox',name='Task name 6')).to_have_value('Survives retry')
    assert next(card for card in ws.tasks.read()['cards'] if card['id']==6)['parent_id']==1
    popup.get_by_role('button',name='Close card',exact=True).click()
    expect(copy).to_have_count(0)
    page.locator('.task-card[data-id="5"]').click()
    expect(copy).to_have_accessible_name('Copy card reference #C05')


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_card_popup_geometry_backdrop_drafts_and_editable_heading(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    def change(**data):return ws.tasks.mutate(dict(revision=ws.tasks.read()['revision'],**data))
    change(action='create',title='Plan the release')
    change(action='create',title='Ship a task')
    change(action='update',ids=[1],changes={'milestone':True})
    change(action='create',title='Nested task',parent_id=1)
    page.goto(url);page.locator('#tasks-open').click()
    card=page.locator('#task-sidebar .task-outline-row[data-id="1"]')
    def open_milestone():
        card.get_by_role('button', name='Open card details').click()

    open_milestone()
    popup=page.locator('.task-detail')
    expect(popup).to_be_visible()
    expect(page.get_by_role('dialog',name='M1: Plan the release',exact=True)).to_be_visible()
    expect(card).to_be_visible();expect(page.locator('#task-sidebar')).to_be_visible()
    assert popup.evaluate('e=>e.matches(":modal")')
    for theme in ('light','dark'):
        page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
        for width,height in ((1600,1000),(1100,800),(800,800),(390,700)):
            page.set_viewport_size({'width':width,'height':height})
            box=popup.bounding_box()
            assert abs(box['width']-min(768,width-(24 if width<=600 else 48)))<2
            assert abs(box['x']+box['width']/2-width/2)<2
            assert abs(box['y']+box['height']/2-height/2)<2
            assert box['height']<=height-(24 if width<=600 else 64)+2
            assert box['x']>=10 and box['y']>=10
            assert popup.evaluate('e=>e.scrollWidth<=e.clientWidth+1')
    page.set_viewport_size({'width':1440,'height':960})
    title=popup.get_by_role('textbox',name='Title',exact=True)
    assert title.evaluate('e=>!!e.closest("h2") && getComputedStyle(e).borderTopWidth==="0px"')
    assert popup.get_by_role('textbox',name='Title',exact=True).count()==1
    assert popup.locator('label',has_text='Title').count()==0
    title.fill('A long Unicode planning heading — café, milestones, and shared tasks. ' * 4)
    assert title.evaluate('e=>e.clientHeight>50 && e.scrollHeight<=e.clientHeight+1')
    title.fill('A directly editable heading')
    expect(popup.get_by_role('heading',name='M1: A directly editable heading',exact=True)).to_be_visible()
    page.get_by_label('Description',exact=True).fill('An unsaved plan')
    page.emulate_media(reduced_motion='no-preference')
    popup.get_by_role('checkbox',name='Complete Nested task',exact=True).check()
    expect(popup.locator('.task-confetti i').first).to_be_visible()
    # Checklist context actions stay in the modal layer and remain usable.
    popup.locator('.task-outline-row[data-id="3"]').click(button='right',position={'x':8,'y':16})
    menu=popup.get_by_role('menu',name='Selected task actions')
    expect(menu.get_by_role('menuitem',name='Archive',exact=True)).to_be_visible()
    menu.get_by_role('menuitem',name='Clear selection',exact=True).click()
    # Interior whitespace and a text-selection gesture ending outside stay open.
    box=popup.bounding_box()
    popup.click(position={'x':10,'y':100})
    expect(popup).to_be_visible()
    page.mouse.move(box['x']+10,box['y']+100);page.mouse.down();page.mouse.move(8,300,steps=5);page.mouse.up()
    expect(popup).to_be_visible()
    # A backdrop click dismisses without activating the board behind it.
    page.mouse.click(8,300)
    expect(popup).to_have_count(0)
    saved = next(card for card in ws.tasks.read()['cards'] if card['id'] == 1)
    assert saved['title'] == 'A directly editable heading'
    assert saved['description'] == 'An unsaved plan'
    expect(card.locator('.task-outline-name')).to_have_value('A directly editable heading')
    open_milestone()
    title.fill('Save on Escape')
    page.keyboard.press('Escape')
    expect(popup).to_have_count(0)
    open_milestone()
    expect(title).to_have_value('Save on Escape')
    title.fill('Discard this edit')
    popup.get_by_role('button',name='Cancel',exact=True).click()
    expect(popup).to_have_count(0)
    open_milestone()
    expect(title).to_have_value('Save on Escape')
    popup.get_by_role('button',name='Close card',exact=True).click()
    # Normal cards use their name as the editable heading and show #C separately.
    page.locator('.task-card[data-id="2"]').click()
    expect(popup.get_by_role('heading',name='Ship a task',exact=True)).to_be_visible()
    expect(popup.locator('.task-permanent-reference')).to_have_text('Card #C02')
    title.fill('')
    popup.get_by_role('button',name='Close card',exact=True).click()
    expect(popup).to_be_visible()
    assert not title.evaluate('e=>e.checkValidity()')
    title.fill('Ship the full task')
    popup.get_by_role('button',name='Close card',exact=True).click()
    page.reload()
    expect(page.locator('.task-card[data-id="2"]')).to_contain_text('Ship the full task')


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_popup_focus_scroll_polling_and_nested_navigation(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    def change(**data):return ws.tasks.mutate(dict(revision=ws.tasks.read()['revision'],author='Agent',**data))
    change(action='create',title='Parent')
    change(action='create',title='Child',parent_id=1)
    for index in range(20):change(action='create',title=f'Board task {index}')
    page.goto(url);page.locator('#tasks-open').click()
    page.locator('.task-card[data-id="1"]').click()
    popup=page.locator('.task-detail');title=popup.get_by_label('Title',exact=True)
    title.fill('Draft heading <script>plain text</script>')
    page.get_by_label('Description',exact=True).fill('Parent draft')
    change(action='comment',id=1,body='A polling update')
    expect(popup.locator('.task-comment',has_text='A polling update')).to_be_visible()
    expect(title).to_have_value('Draft heading <script>plain text</script>')
    title.focus();page.keyboard.press('Shift+Tab')
    expect(popup.get_by_role('button',name='Close card',exact=True)).to_be_focused()
    page.keyboard.press('Tab');expect(title).to_be_focused()
    # Switching to a child uses the same conflict review and autosave as closing.
    popup.get_by_role('button',name='Open #C02',exact=True).click()
    popup.get_by_text('Review latest saved card').click()
    popup.get_by_role('button',name='Use this revision and keep my edits').click()
    popup.get_by_role('button',name='Open #C02',exact=True).click()
    expect(popup.get_by_role('heading',name='Child',exact=True)).to_be_visible()
    assert next(card for card in ws.tasks.read()['cards'] if card['id'] == 1)['description'] == 'Parent draft'
    popup.get_by_role('button',name='Close card',exact=True).click()
    page.locator('.task-card[data-id="1"]').click()
    expect(title).to_have_value('Draft heading <script>plain text</script>')
    expect(page.get_by_label('Description',exact=True)).to_have_value('Parent draft')
    # Long activity scrolls inside the popup while the board remains still.
    for index in range(20):change(action='comment',id=1,body=f'Comment {index}')
    expect(popup.locator('.task-comment')).to_have_count(21)
    before=page.locator('#surface').evaluate('e=>e.scrollTop')
    toolbar=popup.get_by_role('toolbar',name='Card actions')
    toolbar_before=toolbar.bounding_box()
    popup.locator('.task-comment-form').scroll_into_view_if_needed()
    assert popup.locator('.task-detail-content').evaluate('e=>e.scrollTop>0')
    assert toolbar.bounding_box()==toolbar_before
    assert page.locator('#surface').evaluate('e=>e.scrollTop')==before
    expect(popup.get_by_role('button',name='Close card',exact=True)).to_be_visible()
    popup.get_by_role('button',name='Close card',exact=True).click()
    expect(page.locator('.task-card[data-id="1"]')).to_be_focused()
