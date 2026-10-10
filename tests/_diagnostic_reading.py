import json
import pytest
from test_requested_features import workspace_page, open_file
from test_discussion_reading_browser import endpoint
from test_spotlight_navigation_browser import settle

pytestmark = pytest.mark.browser

@pytest.mark.parametrize('workspace_page', ['firefox'], indirect=True)
@pytest.mark.parametrize('trial', range(20))
def test_observe_low_html(workspace_page, trial):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    text=''.join(f'<p id="p{i}"><a href="https://example.invalid">Reference</a> <strong>Passage {i:02}</strong>: '+('Prose for reading a long document. '*10)+'</p>' for i in range(40))
    (root/'report.html').write_text(text)
    at=text.index('Passage 30')
    ws.create_thread('report.html',at,at+10,'Review. '*80,'Reviewer',ws.read('report.html')['version'])
    page.set_viewport_size({'width':1000,'height':680});page.goto(url);open_file(page,'report.html')
    target=page.frame_locator('#html-preview').locator('#p30 strong')
    target.evaluate('''el=>{
      window.observations=[];const range=document.createRange();range.setStart(el.firstChild,2);range.setEnd(el.firstChild,3);
      const record=(type,event)=>observations.push({type,time:performance.now(),y:window.scrollY,top:range.getBoundingClientRect().top,eventY:event?.clientY});
      for(const type of ['pointermove','pointerdown','mousedown','mouseup','click','scroll','focus','message'])window.addEventListener(type,event=>record(type,event),true);
      window.observe=record;
    }''')
    page.locator('.thread [data-action=jump]').first.evaluate('el=>el.click()');settle(page)
    target.scroll_into_view_if_needed()
    target.evaluate('''el=>{const r=el.getBoundingClientRect();window.scrollBy(0,(r.top+r.bottom)/2-(window.innerHeight-8))}''');settle(page)
    point=endpoint(target,2);before=point['y'];bounds=page.locator('#html-preview').bounding_box()
    target.evaluate('()=>observe("before")')
    page.mouse.click(bounds['x']+point['x'],bounds['y']+point['y'])
    expect(page.locator('#passage-spotlight')).to_be_visible();settle(page)
    after=endpoint(target,2)['y']
    print(json.dumps({'trial':trial,'before':before,'after':after,'events':target.evaluate('()=>{observe("after");return observations}')}))
    assert abs(after-before)<2

@pytest.mark.parametrize('workspace_page', ['chromium'], indirect=True)
@pytest.mark.parametrize('trial', range(20))
def test_observe_context(workspace_page, trial):
    from test_context_return_browser import test_context_restores_reader_and_drafts
    page=workspace_page[1]
    page.add_init_script('''
      window.contextObservations=[];
      let previous='';
      function observe(){
        const scroller=window.heldReader?.querySelector('.cm-scroller');
        if(scroller){
          const data={top:scroller.scrollTop,height:scroller.scrollHeight,clientHeight:scroller.clientHeight,held:window.heldScroll,hidden:window.heldReader.hidden,original:!!document.querySelector('.original-reading'),fonts:document.fonts.status};
          const key=JSON.stringify(data);
          if(key!==previous){contextObservations.push({...data,time:performance.now()});previous=key;}
        }
        requestAnimationFrame(observe);
      }
      requestAnimationFrame(observe);
    ''')
    try:
        test_context_restores_reader_and_drafts(workspace_page, 'edit', 'source', 'return')
    finally:
        print(json.dumps({'context_trial':trial,'events':page.evaluate('()=>contextObservations')}))
