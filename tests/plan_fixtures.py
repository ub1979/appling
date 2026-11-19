"""Small complete plan responses for controller integration tests."""
import copy


def plan_result(tasks,plan='Contracts, parallel implementation and final integration.',requirement='FR-1'):
    tasks=copy.deepcopy(tasks)
    for t in tasks:
        t.setdefault('kind','integration' if 'integration' in t['id'] else 'development')
        t.setdefault('requirements',[requirement])
        t.setdefault('inputs',[dict(task=d,contract='tested interface from '+d) for d in t.get('depends_on',[])])
        t.setdefault('outputs',['tested output of '+t['id']])
        t.setdefault('acceptance',[dict(command='verify '+t['id'],expect='expected behavior passes')])
        for check in t['acceptance']:
            check.setdefault('requires_tasks',list(t.get('depends_on',[])))
    return dict(plan=plan,tasks=tasks,runtime=dict(tools=[],bootstrap=[],browser=False),
        journeys=[dict(id='J1',requirements=[requirement],tasks=[t['id'] for t in tasks],
            trigger='Owner asks to increment',operations='Create counter and increment its persisted value',
            review='Local operation; no external write',result='Counter changes from zero to one',check='browser click increment')])
