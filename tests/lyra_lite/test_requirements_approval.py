"""Status bookkeeping cannot revoke approval; product changes still do."""
import hashlib
import subprocess

from lyra_lite import review
from lyra_lite.store import ProjectStore

DRAFT = ('# Requirements\n\n**Status:** Draft\n\n## Features\nLoad CSV only.\n\n'
         '## Approval gates and current state\nApproval pending.\n\n'
         '## Open verification\nVerify read-only access.\n')
APPROVED = DRAFT.replace('**Status:** Draft', '**Status:** Approved').replace('Approval pending.', 'Both approvals recorded; planning is next.')


def test_only_approval_bookkeeping_is_excluded(tmp_path):
    path = tmp_path / 'requirements.md'
    path.write_text(DRAFT)
    before = review.requirements_revision(tmp_path)
    path.write_text(APPROVED)
    assert review.requirements_revision(tmp_path) == before
    path.write_text(APPROVED.replace('CSV only', 'CSV and write-capable database access'))
    assert review.requirements_revision(tmp_path) != before
    path.write_text(APPROVED.replace('Verify read-only access.', 'Permit write access.'))
    assert review.requirements_revision(tmp_path) != before


def test_heading_inside_code_is_requirement_content():
    text = '# Requirements\n```markdown\n## Approval gates and current state\nSample data\n```\n'
    assert 'Sample data' in review.requirements_content(text)


def _git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def test_legacy_migration_requires_matching_approved_snapshot_and_unchanged_scope(tmp_path):
    store = ProjectStore(tmp_path).init()
    path = tmp_path / 'requirements.md'
    path.write_text(DRAFT)
    _git(tmp_path, 'init', '-q')
    _git(tmp_path, 'add', 'requirements.md')
    _git(tmp_path, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'Approved draft')
    legacy = hashlib.sha256(review._STATUS.sub('', DRAFT, count=1).strip().encode()).hexdigest()
    store.update_state(requirements_approved=legacy)
    path.write_text(APPROVED.replace('CSV only', 'CSV and database writes'))
    assert not review.reconcile_requirements_approval(store)
    assert store.state()['requirements_approved'] == legacy
    path.write_text(APPROVED)
    assert review.reconcile_requirements_approval(store)
    assert store.state()['requirements_approved'] == review.requirements_revision(tmp_path)
    assert store.state()['requirements_revision_format'] == 2
    assert not review.reconcile_requirements_approval(store)
