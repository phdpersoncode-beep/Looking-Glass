import os
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import expect
from test_requested_features import open_file, workspace_page

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER'),
]


def crumb(page, path):
    return page.get_by_role('button', name='Browse neighboring files from ' + path, exact=True)


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_choose_neighbor_with_keys_preserves_draft_and_file_history(workspace_page):
    root, page, url, _ = workspace_page
    (root/'src'/'audit'/'extra').mkdir(parents=True)
    (root/'src'/'audit'/'main.py').write_text('value = 1\n')
    (root/'src'/'audit'/'neighbor.py').write_text('value = 2\n')
    (root/'src'/'audit'/'analysis.ipynb').write_text('{"cells":[]}')
    (root/'src'/'audit'/'hidden.py').write_text('value = 3\n')
    (root/'src'/'audit'/'extra'/'more.py').write_text('value = 4\n')
    (root/'.looking.ignore').write_text('hidden.py\n')

    page.goto(url)
    page.get_by_role('button', name='Expand all folders').click()
    open_file(page, 'src/audit/main.py')
    page.locator('.cm-content').focus()
    page.keyboard.press('Control+End')
    page.keyboard.insert_text('draft = True')
    expect(page.locator('#dirty')).to_contain_text('Unsaved')

    file_crumb = crumb(page, 'src/audit/main.py')
    file_crumb.press('Enter')
    picker = page.get_by_role('dialog', name='Neighboring files')
    query = picker.get_by_role('combobox', name='Filter files and folders')
    expect(query).to_be_focused()
    expect(picker.get_by_role('option')).to_have_text(['extra', 'analysis.ipynb', 'main.py', 'neighbor.py'])
    expect(picker.get_by_role('option', name='main.py')).to_have_attribute('aria-selected', 'true')
    query.press('ArrowDown')
    expect(picker.get_by_role('option', name='neighbor.py')).to_have_attribute('aria-selected', 'true')
    query.press('Enter')
    expect(picker).not_to_be_visible()
    expect(page.locator('#document-name')).to_have_text('src/audit/neighbor.py')
    expect(page.locator('.cm-content')).to_be_focused()

    page.get_by_role('button', name='Back to previous file').click()
    expect(page.locator('#document-name')).to_have_text('src/audit/main.py')
    expect(page.locator('.cm-content')).to_contain_text('draft = True')
    assert (root/'src'/'audit'/'main.py').read_text() == 'value = 1\n'

    crumb(page, 'src/audit').click()
    expect(picker.locator('[data-breadcrumb-location]')).to_have_text('src')
    expect(picker.get_by_role('option', name='audit')).to_have_attribute('aria-selected', 'true')
    query.press('Enter')
    picker.get_by_role('option', name='extra').click()
    expect(picker.get_by_role('option', name='more.py')).to_be_visible()
    picker.get_by_role('button', name='Go to parent folder').click()
    expect(picker.get_by_role('option', name='extra')).to_have_attribute('aria-selected', 'true')
    query.fill('absent')
    expect(picker.get_by_role('status')).to_have_text('No matching files or folders.')
    query.fill('neighbor')
    expect(picker.get_by_role('option')).to_have_text(['neighbor.py'])
    query.press('Escape')
    expect(picker).not_to_be_visible()
    expect(crumb(page, 'src/audit')).to_be_focused()

    file_crumb.click()
    picker.get_by_role('option', name='analysis.ipynb').click()
    notebook_dialog = page.get_by_role('dialog', name='Notebooks are not supported')
    expect(notebook_dialog.get_by_role('textbox', name='File path')).to_have_value(str(root/'src'/'audit'/'analysis.ipynb'))
    page.keyboard.press('Escape')
    expect(notebook_dialog).not_to_be_visible()
    expect(page.locator('.cm-content')).to_contain_text('draft = True')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_breadcrumb_picker_ignores_stale_folder_results_and_fits_narrow_pane(workspace_page):
    root, page, url, _ = workspace_page
    (root/'src').mkdir()
    (root/'src'/'part.py').touch()
    (root/'README.md').touch()
    page.set_viewport_size({'width': 780, 'height': 700})
    held = []

    def delay_inner(route):
        directory = parse_qs(urlparse(route.request.url).query).get('directory')
        if directory == ['src']:
            held.append(route)
        else:
            route.continue_()

    page.route('**/api/workspace/children?*', delay_inner)
    page.goto(url)
    page.locator('.file-folder[data-directory="src"] summary').click()
    open_file(page, 'src/part.py')
    page.locator('#theme').click()
    crumb(page, 'src/part.py').click()
    picker = page.get_by_role('dialog', name='Neighboring files')
    expect(picker.get_by_role('status')).to_have_text('Loading files…')
    crumb(page, 'src').click()
    expect(picker.get_by_role('option', name='README.md')).to_be_visible()
    with page.expect_response(lambda response: 'directory=src' in response.url):
        held.pop().fulfill(json={'entries': [{'name': 'stale.py', 'path': 'src/stale.py', 'directory': False}],
                                 'truncated': False})
    page.evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    expect(picker.get_by_role('option', name='stale.py')).to_have_count(0)
    expect(picker.get_by_role('option', name='README.md')).to_be_visible()
    rect = picker.bounding_box()
    assert rect['x'] >= 0 and rect['x'] + rect['width'] <= 780
    assert rect['y'] >= 0 and rect['y'] + rect['height'] <= 700
    page.locator('header strong').click()
    expect(picker).not_to_be_visible()
