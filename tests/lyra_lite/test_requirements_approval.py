"""Status bookkeeping cannot revoke approval; product changes still do."""
import hashlib
import subprocess

import pytest

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


@pytest.mark.parametrize('revision_format', [None, 1])
def test_legacy_migration_requires_matching_approved_snapshot_and_unchanged_scope(tmp_path, revision_format):
    store = ProjectStore(tmp_path).init()
    path = tmp_path / 'requirements.md'
    path.write_text(DRAFT)
    _git(tmp_path, 'init', '-q')
    _git(tmp_path, 'add', 'requirements.md')
    _git(tmp_path, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'Approved draft')
    legacy = hashlib.sha256(review._STATUS.sub('', DRAFT, count=1).strip().encode()).hexdigest()
    store.update_state(requirements_approved=legacy, requirements_revision_format=revision_format)
    path.write_text(APPROVED.replace('CSV only', 'CSV and database writes'))
    assert not review.reconcile_requirements_approval(store)
    assert store.state()['requirements_approved'] == legacy
    path.write_text(APPROVED)
    assert review.reconcile_requirements_approval(store)
    assert store.state()['requirements_approved'] == review.requirements_revision(tmp_path)
    assert store.state()['requirements_revision_format'] == 3
    assert not review.reconcile_requirements_approval(store)


def test_nested_scope_under_approval_notes_is_not_excluded(tmp_path):
    path = tmp_path / 'requirements.md'
    nested = DRAFT.replace('Approval pending.', 'Approval pending.\n\n### Menu changes\nOpen recent projects.')
    path.write_text(nested)
    before = review.requirements_revision(tmp_path)
    assert 'Open recent projects.' in review.requirements_content(nested)
    path.write_text(nested.replace('Open recent projects.', 'Delete recent projects.'))
    assert review.requirements_revision(tmp_path) != before


def _format2_approval(root, draft):
    store = ProjectStore(root).init()
    (root / 'requirements.md').write_text(draft)
    legacy = hashlib.sha256(review._requirements_content(draft, include_nested=False).encode()).hexdigest()
    store.update_state(requirements_approved=legacy, requirements_revision_format=2)
    card = store.add_inbox('requirements', revision=legacy,
                          question='Review requirements.\n\n---\n\n' + draft)
    store.close_inbox(card['id'], 'answered', answer='Approve requirements')
    return store, card


def test_format2_migration_requires_reviewed_nested_scope(tmp_path):
    draft = DRAFT.replace('Approval pending.', 'Approval pending.\n\n### Menu changes\nOpen recent projects.')
    store, card = _format2_approval(tmp_path, draft)
    old = store.state()['requirements_approved']
    (tmp_path / 'requirements.md').write_text(draft.replace('**Status:** Draft', '**Status:** Approved'))
    assert review.reconcile_requirements_approval(store)
    assert store.state()['requirements_approved'] != old
    assert store.state()['requirements_approved'] == review.requirements_revision(tmp_path)
    assert store.state()['requirements_revision_format'] == 3
    assert not review.reconcile_requirements_approval(store)


def test_format2_migration_rejects_unreviewed_nested_change(tmp_path):
    draft = DRAFT.replace('Approval pending.', 'Approval pending.\n\n### Menu changes\nOpen recent projects.')
    store, _ = _format2_approval(tmp_path, draft)
    old = store.state()['requirements_approved']
    (tmp_path / 'requirements.md').write_text(draft.replace('Open recent projects.', 'Delete all projects.'))
    assert not review.reconcile_requirements_approval(store)
    assert store.state()['requirements_approved'] == old


def test_format2_migration_rejects_missing_review_evidence(tmp_path):
    draft = DRAFT.replace('Approval pending.', 'Approval pending.\n\n### Menu changes\nOpen recent projects.')
    store, card = _format2_approval(tmp_path, draft)
    store.close_inbox(card['id'], 'expired')
    assert not review.reconcile_requirements_approval(store)
