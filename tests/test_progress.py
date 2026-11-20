import concurrent.futures
from appling.progress import publish_due, watch
from appling.store import Store


def project(tmp_path):
    store=Store(tmp_path/'state');p=store.add(tmp_path/'project')
    store.update(p['id'],phase='build',running=True,turn=dict(id='turn'))
    event=store.event(p['id'],'turn_start',turn='turn')
    return store,p['id'],event['ts']


def test_written_updates_are_due_every_five_minutes_and_persist_without_changing_work(tmp_path):
    store,pid,started=project(tmp_path)
    store.event(pid,'tool',phase='complete',name='commandExecution',exit_code=1)
    before=store.get(pid)
    assert not publish_due(store,pid,now=started+299)
    assert publish_due(store,pid,now=started+300)
    assert not publish_due(store,pid,now=started+599)
    assert publish_due(store,pid,now=started+600)
    assert store.get(pid)==before
    messages=Store(store.home).messages(pid)
    assert len(messages)==2 and all(m['kind']=='progress' for m in messages)
    assert 'building and testing the app' in messages[0]['content'] and 'nonzero' not in messages[0]['content']
    assert 'No activity in the last five minutes' in messages[1]['content']
    import time
    stamp=time.strftime('%a %d %b %Y, %H:%M',time.localtime(started+300))
    assert messages[0]['content'].startswith(stamp) and messages[0]['ts']==started+300   # the owner sees when it was written
    assert len([e for e in store.events(pid) if e['type']=='status_update'])==2


def test_concurrent_watchers_claim_one_update_and_never_backfill_a_burst(tmp_path):
    store,pid,started=project(tmp_path)
    stores=[Store(store.home),Store(store.home)]
    with concurrent.futures.ThreadPoolExecutor() as pool:
        results=list(pool.map(lambda s:publish_due(s,pid,now=started+1800),stores))
    assert sum(results)==1 and len(store.messages(pid))==1
    assert not publish_due(store,pid,now=started+1801)


def test_stopped_finished_or_paused_jobs_do_not_publish(tmp_path):
    store,pid,started=project(tmp_path)
    for fields in [dict(paused=True),dict(paused=False,running=False),dict(running=True,turn=None)]:
        store.update(pid,**fields)
        assert not publish_due(store,pid,now=started+900)
    assert not store.messages(pid)


def test_reports_are_labelled_redacted_and_raw_commands_and_secret_questions_are_excluded(tmp_path,monkeypatch):
    store,pid,started=project(tmp_path)
    monkeypatch.setenv('MY_SECRET_TOKEN','private-progress-secret')
    store.event(pid,'worker_commentary',text='Model said tests passed private-progress-secret')
    store.event(pid,'tool',phase='start',name='commandExecution',args='raw-sensitive-command')
    store.ask(pid,'secret','private-secret-question',[])
    assert publish_due(store,pid,now=started+300)
    text=store.messages(pid)[0]['content']
    assert 'not yet checked' in text and '[REDACTED]' in text
    assert all(s not in text for s in ['private-progress-secret','raw-sensitive-command','private-secret-question'])


def test_new_turn_gets_a_full_interval_before_first_update(tmp_path):
    store,pid,started=project(tmp_path)
    assert publish_due(store,pid,now=started+300)
    store.update(pid,turn=dict(id='next'))
    event=store.event(pid,'turn_start',turn='next')
    assert not publish_due(store,pid,now=event['ts']+299)


def test_service_watcher_covers_all_projects_and_stops_when_instance_changes(tmp_path,monkeypatch):
    store,pid,started=project(tmp_path)
    other=store.add(tmp_path/'other')
    store.update(other['id'],running=True,turn=dict(id='other'))
    store.event(other['id'],'turn_start',turn='other')
    monkeypatch.setattr('appling.progress.time.time',lambda:started+301)
    class Stop:
        def is_set(self):return False
        def wait(self,seconds):
            assert seconds==5
            store.update(pid,running=False,turn=None)
    checks=iter([True,False])
    watch(store,None,Stop(),alive=lambda:next(checks))
    assert len(store.messages(pid))==len(store.messages(other['id']))==1
