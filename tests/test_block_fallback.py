"""Blocks mode: a block that cannot be built in parallel is built step by step by the main builder,
so a stuck block slows the project down instead of stopping it."""
import json
from pathlib import Path

from appling import blocks
from appling.blockbuild import protected_folders
from test_blocks import Engine, library, make, to_blocks_review  # noqa: F401
from test_workflow import approve, wait_idle


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


def test_an_ai_program_outage_pauses_the_project_and_never_turns_it_into_a_step_by_step_build(tmp_path, library):
    """A usage limit or lost connection says nothing about the block, so it must not cost the project its parallel build."""
    class Outage(Engine):
        down = True
        def __call__(self, connection, run):
            brief = json.loads(run.prompt)
            if self.down and self.role(run) == 'sw-developer' and brief.get('worker') and 'in blocks/poster/ only' in brief['goal']:
                with self.lock:
                    self.calls.append('block:poster')
                raise RuntimeError('Codex exited before completing the task. Usage limit reached.')
            return super().__call__(connection, run)
        def barrier_parties(self):
            return []
    engine = Outage(); store, workflow, pid = make(tmp_path, engine)
    try:
        to_blocks_review(store, workflow, pid); approve(store, workflow, pid, 'blocks')
        state = store.get(pid)
        assert state['paused'] and state['attention']['reason'] == 'engine' and 'Usage limit reached' in state['attention']['message']
        assert state['block_status']['notifier']['status'] == 'tested'            # finished work is kept
        assert state['block_status']['poster']['status'] == 'planned' and not state['block_status']['poster'].get('serial')
        assert not [e for e in store.events(pid) if e['type'] == 'serial_fallback'] and 'body' not in engine.calls
        assert not [i for i in store.inbox(pid) if i.get('blocks_scope')]
        engine.down = False
        workflow.submit(pid, 'continue'); wait_idle(workflow, pid)
        state = store.get(pid)
        assert state['phase'] == 'implementation_verified', [m['content'][:200] for m in store.messages(pid)][-3:]
        assert engine.calls.count('block:poster') == 2 and engine.calls.count('block:notifier') == 1
        assert not state['block_status']['poster'].get('serial')
    finally:
        workflow.shutdown()


def test_a_path_into_applings_folder_inside_a_finished_block_goes_back_to_that_blocks_builder(tmp_path, library):
    from appling.context import ROOT
    class Leaky(Engine):
        goals = []
        def __call__(self, connection, run):
            brief = json.loads(run.prompt)
            result = super().__call__(connection, run)
            if self.role(run) == 'sw-developer' and brief.get('worker') and 'in blocks/notifier/ only' in brief['goal']:
                self.goals.append(brief['goal'])
                check = run.root / 'blocks/notifier/check.mjs'
                check.write_text(f"import '{ROOT}/scripts/browser-check.mjs';\n" if len(self.goals) == 1 else "import 'playwright';\n")
            return result
    engine = Leaky(); engine.barrier_parties = lambda: []   # the block is rebuilt alone, so nothing overlaps
    store, workflow, pid = make(tmp_path, engine)
    try:
        to_blocks_review(store, workflow, pid); approve(store, workflow, pid, 'blocks')
        state = store.get(pid)
        assert state['phase'] == 'implementation_verified', [m['content'][:200] for m in store.messages(pid)][-3:]
        # The main builder may not edit that block, so its own builder got the request and fixed it.
        assert len(engine.goals) == 2 and "point into Appling's own folder" in engine.goals[1]
        assert str(ROOT) not in (Path(state['root']) / 'blocks/notifier/check.mjs').read_text()
        assert not [i for i in store.inbox(pid) if i.get('blocks_scope') or i.get('scope')]
    finally:
        workflow.shutdown()
