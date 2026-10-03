import subprocess
import pytest
from looking_glass.workspace import Workspace, Problem
from looking_glass.revisions import Revisions


def git(root,*args):
    return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path,'init')
    git(tmp_path,'config','user.name','Looking Glass Test')
    git(tmp_path,'config','user.email','test@example.invalid')
    for name in ('one.md','two.py','three.txt'):
        (tmp_path/name).write_text('original\n')
    git(tmp_path,'add','one.md','two.py','three.txt')
    git(tmp_path,'commit','-m','initial')
    return tmp_path


def test_selective_checkpoint_preserves_unrelated_index(repo):
    (repo/'one.md').write_text('selected edit\n')
    (repo/'two.py').write_text('staged agent edit\n')
    git(repo,'add','two.py')
    (repo/'two.py').write_text('unstaged agent edit after staging\n')
    (repo/'three.txt').write_text('unrelated unsaved\n')
    (repo/'untracked.txt').write_text('untracked\n')
    revisions=Revisions(Workspace(repo))
    result=revisions.checkpoint(['one.md'],'Review introduction')
    assert len(result['commit'])==40
    assert git(repo,'show','HEAD:one.md')=='selected edit'
    assert git(repo,'show','HEAD:two.py')=='original'
    assert git(repo,'show',':two.py')=='staged agent edit'
    assert (repo/'two.py').read_text()=='unstaged agent edit after staging\n'
    assert (repo/'three.txt').read_text()=='unrelated unsaved\n'
    assert (repo/'untracked.txt').exists()
    assert git(repo,'diff','--cached','--name-only')=='two.py'


def test_staged_selection_rejected(repo):
    (repo/'one.md').write_text('staged\n')
    git(repo,'add','one.md')
    before=git(repo,'rev-parse','HEAD')
    with pytest.raises(Problem,match='staged changes'):
        Revisions(Workspace(repo)).checkpoint(['one.md'],'should fail')
    assert git(repo,'rev-parse','HEAD')==before


def test_first_commit_and_subdirectory(repo,tmp_path_factory):
    child=repo/'child'
    child.mkdir()
    (child/'nested.md').write_text('nested')
    revisions=Revisions(Workspace(child))
    assert revisions.status()['files']==[dict(path='nested.md',status='??')]
    revisions.checkpoint(['nested.md'],'nested checkpoint')
    assert git(repo,'show','HEAD:child/nested.md')=='nested'
    new=tmp_path_factory.mktemp('new-repo')
    (new/'first.txt').write_text('first')
    revisions=Revisions(Workspace(new))
    assert not revisions.status()['repository']
    revisions.init()
    git(new,'config','user.name','Test')
    git(new,'config','user.email','test@example.invalid')
    revisions.checkpoint(['first.txt'],'first checkpoint')
    assert git(new,'show','HEAD:first.txt')=='first'


def test_deleted_selected_file(repo):
    (repo/'one.md').unlink()
    revisions=Revisions(Workspace(repo))
    revisions.checkpoint(['one.md'],'remove selected file')
    assert 'one.md' not in git(repo,'ls-tree','--name-only','HEAD').splitlines()


def test_literal_path_names_do_not_select_unrelated_files(repo):
    (repo/'[ab].md').write_text('literal filename')
    (repo/'a.md').write_text('unrelated filename')
    revisions=Revisions(Workspace(repo))
    revisions.checkpoint(['[ab].md'],'literal selection')
    assert git(repo,'show','--pretty=','--name-only','HEAD')=='[ab].md'
    assert 'a.md' in git(repo,'ls-files','--others','--exclude-standard').splitlines()
