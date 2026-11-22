import os

import pytest
from playwright.sync_api import expect
from test_requested_features import open_file, workspace_page

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER'),
]


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_marker_tree_sections_grouping_filter_and_saved_line_navigation(workspace_page):
    root, page, url, _ = workspace_page
    (root/'src').mkdir()
    (root/'src'/'app.py').write_text('def run():\n    # P0: Validate paths\n    return 1\n', encoding='utf-8')
    notes = root/'notes.md'
    notes.write_text('# Notes\n\nTODO: Document the run command\n\n# NOTE: Keep this quiet\n', encoding='utf-8')
    requests = []
    page.on('request', lambda request: requests.append(request.url) if request.url.endswith('/api/marker-tree') else None)
    page.goto(url)
    marker = page.get_by_role('button', name='Marker Tree', exact=True)
    files = page.get_by_role('button', name='File Tree', exact=True)
    expect(marker).to_have_attribute('aria-expanded', 'false')
    expect(files).to_have_attribute('aria-expanded', 'true')
    open_file(page, 'notes.md')
    page.locator('#mode').select_option('preview')
    expect(page.locator('.markdown-preview')).to_be_visible()
    assert requests == []

    marker.focus()
    page.keyboard.press('Enter')
    expect(marker).to_have_attribute('aria-expanded', 'true')
    expect(page.locator('#marker-count')).to_have_text('3')
    folder = page.locator('#marker-results summary', has_text='src')
    expect(folder).to_be_visible()
    expect(page.locator('.marker-hit')).to_have_count(0)
    folder.click()
    page.locator('#marker-results summary', has_text='app.py').click()
    page.get_by_role('button', name='P0 Validate paths').click()
    expect(page.locator('#document-name')).to_have_text('src/app.py')
    expect(page.locator('.cm-activeLine')).to_contain_text('# P0: Validate paths')
    expect(page.locator('.cm-content')).to_be_focused()

    page.get_by_role('button', name='Group markers by tag').click()
    expect(page.locator('#marker-results > details > summary .marker-tag')).to_have_text(['P0', 'TODO', 'NOTE'])
    page.get_by_role('button', name='Filter markers', exact=True).click()
    query = page.get_by_role('searchbox', name='Filter markers')
    query.fill('run command')
    todo = page.get_by_role('button', name='TODO Document the run command')
    expect(todo).to_be_visible()
    expect(page.locator('.marker-hit')).to_have_count(1)
    todo.click()
    expect(page.locator('#mode')).to_have_value('source')
    expect(page.locator('.cm-activeLine')).to_contain_text('TODO: Document the run command')
    page.keyboard.press('Control+Home')
    page.keyboard.insert_text('Draft addition\n')
    expect(page.locator('#dirty')).to_contain_text('Unsaved')
    todo.click()
    expect(page.locator('.cm-activeLine')).to_contain_text('TODO: Document the run command')
    assert not notes.read_text(encoding='utf-8').startswith('Draft addition')
    page.keyboard.press('Control+z')

    query.focus()
    page.keyboard.press('Escape')
    expect(query).not_to_be_visible()
    page.get_by_role('button', name='Expand all marker branches').click()
    expect(page.locator('.marker-hit')).to_have_count(3)
    page.get_by_role('button', name='Collapse all marker branches').click()
    expect(page.locator('.marker-hit')).to_have_count(0)
    files.click()
    expect(page.locator('#file-tree')).not_to_be_visible()
    expect(page.locator('#marker-results')).to_be_visible()
    files.click()
    expect(page.locator('#file-tree')).to_be_visible()

    (root/'new.md').write_text('# P1: Fresh from disk\n', encoding='utf-8')
    page.get_by_role('button', name='Refresh markers', exact=True).click()
    expect(page.locator('#marker-count')).to_have_text('4')
    expect(page.locator('#marker-results > details > summary .marker-tag')).to_have_text(['P0', 'P1', 'TODO', 'NOTE'])
    page.locator('.cm-content').focus()
    page.keyboard.press('Control+End')
    page.keyboard.insert_text('\nTODO: Added in the editor\n')
    page.keyboard.press('Control+s')
    expect(page.locator('#marker-count')).to_have_text('5')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_marker_controls_fit_narrow_dark_sidebar_and_no_hidden_refresh(workspace_page):
    root, page, url, _ = workspace_page
    (root/'file.md').write_text('#P3 A follow-up\n', encoding='utf-8')
    page.set_viewport_size({'width': 780, 'height': 740})
    page.goto(url)
    page.locator('#theme').click()
    page.locator('#file-resize').focus()
    page.keyboard.press('Home')
    page.locator('#marker-section-toggle').click()
    expect(page.locator('#marker-count')).to_have_text('1')
    sidebar = page.locator('#file-sidebar').bounding_box()
    for action in page.locator('#marker-actions button, #file-actions button').all():
        rect = action.bounding_box()
        assert sidebar['x'] <= rect['x'] and rect['x'] + rect['width'] <= sidebar['x'] + sidebar['width']
    page.locator('#marker-section-toggle').click()
    requests = []
    page.on('request', lambda request: requests.append(request.url) if request.url.endswith('/api/marker-tree') else None)
    with page.expect_response(lambda response: '/fragments/files' in response.url):
        page.locator('#refresh-files').click()
    expect(page.locator('#marker-section-toggle')).to_have_attribute('aria-expanded', 'false')
    expect(page.locator('#marker-results details')).to_have_count(0)
    assert not requests


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_marker_icons_and_notebook_copy_path(workspace_page):
    import json

    root, page, url, _ = workspace_page
    (root/'notes').mkdir()
    (root/'notes'/'readme.md').write_text('TODO Document setup\n', encoding='utf-8')
    (root/'tools.py').write_text('# P2: Clean up helpers\n', encoding='utf-8')
    notebook = {
        'cells': [
            {'cell_type': 'markdown', 'source': ['TODO: Explain the setup\n']},
            {'cell_type': 'code', 'outputs': [{'text': '# P0 output only'}],
             'source': ['print("🪞")  #P1: Check notebook records\n']},
        ],
        'metadata': {'language_info': {'name': 'python'}}, 'nbformat': 4,
    }
    (root/'analysis.ipynb').write_text(json.dumps(notebook, indent=1, ensure_ascii=False), encoding='utf-8')

    page.add_init_script('''Object.defineProperty(navigator, 'clipboard', {value: {
        writeText: async text => { window.copiedNotebookPath = text; }
    }});''')
    page.goto(url)
    open_file(page, 'tools.py')
    page.get_by_role('button', name='Marker Tree', exact=True).click()
    expect(page.locator('#marker-count')).to_have_text('4')
    page.get_by_role('button', name='Expand all marker branches').click()
    for name in ['folder', 'markdownFile', 'codeFile', 'notebookFile']:
        expect(page.locator(f'#marker-results svg[data-icon="{name}"]')).to_be_visible()
    target = page.get_by_role('button', name='P1 Check notebook records')
    expect(target).to_have_attribute('title', 'P1 Check notebook records\nanalysis.ipynb · Cell 2, line 1')
    target.click()
    dialog = page.get_by_role('dialog', name='Notebooks are not supported', exact=True)
    path = str(root/'analysis.ipynb')
    expect(dialog.get_by_role('textbox', name='File path')).to_have_value(path)
    dialog.get_by_role('button', name='Copy file path', exact=True).click()
    expect(dialog).to_have_count(0)
    assert page.evaluate('window.copiedNotebookPath') == path
    expect(page.locator('#document-name')).to_have_text('tools.py')
    page.locator('.file-entry[data-path="analysis.ipynb"]').click()
    expect(dialog).to_be_visible()
    page.keyboard.press('Escape')
    expect(dialog).to_have_count(0)
    expect(page.locator('#tabs')).not_to_contain_text('analysis.ipynb')
