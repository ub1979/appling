"""Blocks mode: interfaces are agreed first, then checked by the controller after each block is built."""
import json
from pathlib import Path

import pytest

from appling import acceptance, blocks
from appling.blockbuild import body_goal
from test_blocks import CRITERIA, PREREQS, REQUIREMENTS, Engine, library, make, plan_for, to_blocks_review  # noqa: F401
from test_workflow import approve


def contract_plan():
    plan = plan_for()
    notifier, poster = plan['blocks']
    notifier['contract'] = dict(entry='index.py', config=['BOT_TOKEN'],
                                exports=[dict(name='notify', kind='function', input='text: str', output='None', errors='raises SendError')])
    poster['contract'] = dict(entry='blocks/poster/index.py',
                              exports=[dict(name='post', kind='function', input='text: str', output='PostResult'),
                                       dict(name='PostResult', kind='type')])
    poster['depends_on'] = ['notifier']; poster['uses'] = {'notifier': ['notify']}
    plan['body']['uses'] = {'notifier': ['notify'], 'poster': ['post']}
    return plan


def spec():
    return acceptance.normalize(CRITERIA, PREREQS, REQUIREMENTS)


def test_plan_contracts_are_normalized_shown_for_review_and_reach_the_builders():
    checked = blocks.validate(contract_plan(), spec(), strict_contracts=True)
    notifier, poster = checked['blocks']
    assert checked['version'] == 2 and poster['contract']['entry'] == 'index.py'
    assert poster['uses'] == {'notifier': ['notify']} and checked['body']['uses'] == {'notifier': ['notify'], 'poster': ['post']}
    text = blocks.markdown(checked, spec())
    assert '| `notify` | function | text: str | None | raises SendError |' in text
    assert 'Entry file: `blocks/poster/index.py`' in text and 'App body uses: notifier: notify; poster: post' in text
    goal = blocks.builder_goal(poster, checked, spec())
    assert 'Agreed contract' in goal and 'blocks/poster/index.py' in goal and '"you_use": ["notify"]' in goal
    assert '"contract"' in body_goal(checked, spec()) and 'expects the body to use' in body_goal(checked, spec())


def test_older_plans_without_contracts_are_unchanged():
    checked = blocks.validate(plan_for(), spec(), strict_contracts=True)
    assert checked['version'] == 1 and all('contract' not in b and 'uses' not in b for b in checked['blocks'])
    goal = blocks.builder_goal(checked['blocks'][0], checked, spec())
    assert 'Agreed contract' not in goal and 'in blocks/notifier/ only' in goal
    assert 'Agreed contract' not in blocks.markdown(checked, spec()) and '"contract"' not in body_goal(checked, spec())
    assert blocks.conformance('/nonexistent', checked['blocks'][0]) == ([], [])


def test_a_plan_that_uses_a_name_nobody_offers_is_rejected_before_anything_is_built():
    wrong = contract_plan(); wrong['blocks'][1]['uses'] = {'notifier': ['send']}
    with pytest.raises(ValueError, match="uses send from notifier, but notifier's contract does not offer that"):
        blocks.validate(wrong, spec(), strict_contracts=True)
    assert 'uses' not in blocks.validate(wrong, spec())['blocks'][1]      # a second imperfect proposal still builds
    body = contract_plan(); body['body']['uses'] = {'poster': ['publish']}
    with pytest.raises(ValueError, match='The body uses publish from poster'):
        blocks.validate(body, spec(), strict_contracts=True)
    stranger = contract_plan(); stranger['blocks'][0]['uses'] = {'poster': ['post']}
    with pytest.raises(ValueError, match='does not depend on'):
        blocks.validate(stranger, spec(), strict_contracts=True)
    bare = contract_plan(); del bare['blocks'][1]['contract']
    with pytest.raises(ValueError, match='no contract: poster'):
        blocks.validate(bare, spec(), strict_contracts=True)
    broken = contract_plan(); broken['blocks'][0]['contract']['exports'] = []
    with pytest.raises(ValueError, match='at least one export'):
        blocks.validate(broken, spec(), strict_contracts=True)
    assert 'contract' not in blocks.validate(broken, spec())['blocks'][0]


def test_conformance_reports_names_missing_from_source_and_names_no_test_uses(tmp_path):
    block = blocks.validate(contract_plan(), spec())['blocks'][1]
    folder = tmp_path / 'blocks/poster'; (folder / 'tests').mkdir(parents=True)
    # A differently named entry file is something to correct once, not a hard failure: the plan named it before any code existed.
    missing, soft = blocks.conformance(tmp_path, block)
    assert len(missing) == 2 and soft[0].startswith('The entry file blocks/poster/index.py does not exist')
    (folder / 'index.py').write_text('class PostResult: pass\n')
    (folder / 'README.md').write_text('post(text) publishes it')           # documentation is not an implementation
    (folder / 'tests/test_poster.py').write_text('def test_nothing(): pass\n')
    missing, untested = blocks.conformance(tmp_path, block)
    assert missing == ["post (function) is in the contract but nowhere in the block's source."] and untested == []
    (folder / 'index.py').write_text('class PostResult: pass\ndef post(text): return PostResult()\n')
    missing, untested = blocks.conformance(tmp_path, block)
    assert missing == [] and untested == ['post (function) is not used by any test in the block.']   # a type needs no test
    (folder / 'tests/test_poster.py').write_text('from index import post\ndef test_post(): assert post("x")\n')
    assert blocks.conformance(tmp_path, block) == ([], [])


class ContractEngine(Engine):
    """Plans with contracts. The first proposal uses a name nobody offers. The notifier's first build
    forgets the agreed name; the poster never tests its export."""

    def __init__(self):
        super().__init__()
        self.plans = []; self.goals = {'notifier': [], 'poster': [], 'body': []}

    def barrier_parties(self):
        return []      # the poster depends on the notifier here, so they do not overlap

    def __call__(self, connection, run):
        brief = json.loads(run.prompt); role = self.role(run); root = run.root
        if role == 'sw-architect':
            self.plans.append(brief['goal'])
            plan = contract_plan()
            if len(self.plans) == 1:
                plan['blocks'][1]['uses'] = {'notifier': ['send']}
            return plan
        if role == 'sw-developer' and brief.get('worker'):
            ident = 'notifier' if 'in blocks/notifier/ only' in brief['goal'] else 'poster'
            self.goals[ident].append(brief['goal'])
            result = super().__call__(connection, run)
            folder = root / 'blocks' / ident; (folder / 'tests').mkdir(exist_ok=True)
            if ident == 'notifier':
                name = 'send' if len(self.goals[ident]) == 1 else 'notify'
                (folder / 'index.py').write_text(f'def {name}(text): return None\n')
                (folder / 'tests/test_notifier.py').write_text(f'from index import {name}\ndef test_it(): {name}("x")\n')
            else:
                (folder / 'index.py').write_text('class PostResult: pass\ndef post(text): return PostResult()\n')
                (folder / 'tests/test_poster.py').write_text('def test_nothing(): pass\n')
            return result
        if role == 'sw-developer':
            self.goals['body'].append(brief['goal'])
        return super().__call__(connection, run)


def test_interfaces_are_agreed_first_then_checked_after_each_block_is_built(tmp_path, library):
    engine = ContractEngine(); store, workflow, pid = make(tmp_path, engine)
    try:
        to_blocks_review(store, workflow, pid)
        # The inconsistent first proposal went back to the planner; the owner only sees the consistent one.
        assert len(engine.plans) == 2 and "contract does not offer that" in engine.plans[1]
        review = store.inbox(pid)[0]
        assert review['kind'] == 'blocks' and '| `notify` | function |' in review['question']
        approve(store, workflow, pid, 'blocks')
        state = store.get(pid); root = Path(state['root'])
        assert state['phase'] == 'implementation_verified', [m['content'][:200] for m in store.messages(pid)][-3:]
        # The notifier's tests passed, but it did not provide the agreed name: sent back once, then accepted.
        assert len(engine.goals['notifier']) == 2 and "nowhere in the block's source" in engine.goals['notifier'][1]
        assert 'def notify' in (root / 'blocks/notifier/index.py').read_text()
        assert 'Every contract name is in the source and the tests.' in (root / '.sdlc/evidence/blocks/notifier/interface.log').read_text()
        # An export no test mentions gets one repair round, then is recorded as a note instead of stalling the project.
        assert len(engine.goals['poster']) == 2 and 'not used by any test' in engine.goals['poster'][1]
        assert state['block_status']['poster']['test']['interface_notes'] == ['post (function) is not used by any test in the block.']
        assert '"contract"' in engine.goals['body'][0]
        published = {b['name']: b for b in blocks.catalogue(library)}
        assert published['notifier']['contract']['exports'][0]['name'] == 'notify'
    finally:
        workflow.shutdown()
