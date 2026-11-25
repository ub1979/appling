"""Blocks mode: a block that cannot be built in parallel is built step by step by the main builder,
so a stuck block slows the project down instead of stopping it."""
import json
from pathlib import Path

from appling import blocks
from appling.blockbuild import protected_folders
from test_blocks import Engine, library, make, to_blocks_review  # noqa: F401
from test_workflow import approve


class Fallback(Engine):
    """The poster's own builder cannot finish. The main builder can, on its first or a later turn."""

    def __init__(self, finishes_on=1, touches_other_block=False):
        super().__init__()
        self.stuck = {'poster'}; self.finishes_on = finishes_on; self.touches_other_block = touches_other_block
        self.body_goals = []

    def __call__(self, connection, run):
        brief = json.loads(run.prompt)
        if self.role(run) == 'sw-developer' and not brief.get('worker'):
            self.body_goals.append(brief['goal'])
            if len(self.body_goals) >= self.finishes_on:
                folder = run.root / 'blocks/poster'; folder.mkdir(parents=True, exist_ok=True)
                (folder / 'ok').write_text('ok'); (folder / 'README.md').write_text('# poster\n')
                (folder / 'block.json').write_text(json.dumps(dict(name='poster')))
            if self.touches_other_block:
                (run.root / 'blocks/notifier/ok').write_text('changed by the main builder')
        return super().__call__(connection, run)


def test_a_block_stuck_in_parallel_is_built_step_by_step_without_asking_the_owner(tmp_path, library):
    engine = Fallback(); store, workflow, pid = make(tmp_path, engine)
    try:
        to_blocks_review(store, workflow, pid); approve(store, workflow, pid, 'blocks')
        state = store.get(pid); root = Path(state['root'])
        assert state['phase'] == 'implementation_verified', [m['content'][:200] for m in store.messages(pid)][-3:]
        assert not [i for i in store.inbox(pid) if i.get('blocks_scope') or i.get('scope')]
        assert engine.calls.count('block:poster') == 1 and engine.calls.count('body') == 1
        # The main builder was told which block to build, why its own builder stopped, and what it may edit.
        goal = engine.body_goals[0]
        assert 'step by step' in goal and '"folder": "blocks/poster/"' in goal and 'Needs the real site' in goal
        assert 'These are the only folders under blocks/ you may edit' in goal
        # Appling ran the block's own test itself before accepting it.
        assert (root / '.sdlc/evidence/blocks/poster/test.log').read_text().startswith('command:')
        poster = state['block_status']['poster']
        assert poster['serial'] and poster['status'] in {'tested', 'merged'} and poster['test']['passed']
        assert any('Nothing is needed from you' in m['content'] for m in store.messages(pid))
        assert {b['name'] for b in blocks.catalogue(library)} == {'notifier', 'poster'}
    finally:
        workflow.shutdown()


def test_a_block_unfinished_after_the_first_turn_goes_back_to_the_main_builder_once_more(tmp_path, library):
    engine = Fallback(finishes_on=2); store, workflow, pid = make(tmp_path, engine)
    try:
        to_blocks_review(store, workflow, pid); approve(store, workflow, pid, 'blocks')
        state = store.get(pid)
        assert state['phase'] == 'implementation_verified', [m['content'][:200] for m in store.messages(pid)][-3:]
        assert engine.calls.count('body') == 2 and 'Social poster in blocks/poster/ is not finished' in engine.body_goals[1]
        assert not [i for i in store.inbox(pid) if i.get('blocks_scope')]
        assert state['block_status']['poster']['serial_rounds'] == 2
    finally:
        workflow.shutdown()


def test_the_main_builder_may_write_only_the_blocks_it_was_handed(tmp_path, library):
    plan = dict(blocks=[dict(id='notifier', folder='blocks/notifier/'), dict(id='poster', folder='blocks/poster/')])
    assert protected_folders(plan, {}) == ['blocks/']                                   # unchanged for every other project
    assert protected_folders(plan, {'poster': dict(serial=True)}) == ['blocks/notifier/']
    engine = Fallback(touches_other_block=True); store, workflow, pid = make(tmp_path, engine)
    try:
        to_blocks_review(store, workflow, pid); approve(store, workflow, pid, 'blocks')
        state = store.get(pid)
        assert state['phase'] == 'body' and state['paused']
        assert any('changed files inside blocks/notifier/' in m['content'] for m in store.messages(pid))
    finally:
        workflow.shutdown()
