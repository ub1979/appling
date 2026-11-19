from pathlib import Path
import json
import os
import sqlite3
import subprocess
import sys

source=Path('/Users/u/funcoding/Appling/appling_c')
target=Path('/Users/u/funcoding/appling_c')
if not source.is_dir() or target.exists():
    raise SystemExit('Source must exist and destination must not exist; no files moved.')
if not (source/'.git').is_dir():
    raise SystemExit('Expected the independent Git repository; no files moved.')

old=str(source);new=str(target)
def relocated(value):
    if isinstance(value,str):
        return new+value[len(old):] if value==old or value.startswith(old+'/') else value
    if isinstance(value,list):return [relocated(v) for v in value]
    if isinstance(value,dict):return {k:relocated(v) for k,v in value.items()}
    return value

def git_status(root):
    return subprocess.run(['git','status','--porcelain=v1','-z'],cwd=root,check=True,capture_output=True).stdout

status_before=git_status(source)
# Check the live-service lease before moving any runtime state.
import fcntl
lease=source/'.appling_c/run/server.lock'
if lease.exists():
    with lease.open('r') as handle:
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit('Appling is running; no files moved.')
        fcntl.flock(handle,fcntl.LOCK_UN)

databases=[p for p in [source/'.appling_c/studio.db/studio.sqlite',source/'.appling_c/studio.sqlite'] if p.is_file()]
# Preserve a portable SQLite backup before updating absolute project paths.
for database in databases:
    backup=database.with_name(database.name+'.before-folder-move')
    if backup.exists():raise SystemExit('A previous move backup exists; no files moved.')
    with sqlite3.connect(database) as connection, sqlite3.connect(backup) as saved:
        connection.backup(saved)
    backup.chmod(0o600)

os.rename(source,target)
changed_files=0
venv=target/'.venv'
files=[]
if (venv/'bin').is_dir():files.extend((venv/'bin').iterdir())
for site in (venv/'lib').glob('python*/site-packages'):
    files.extend(site.glob('__editable__*'))
    files.extend(site.glob('*.pth'))
    files.extend(site.glob('*.egg-link'))
for path in files:
    if path.is_symlink() or not path.is_file() or path.stat().st_size>1000000:continue
    raw=path.read_bytes()
    if b'\x00' in raw or old.encode() not in raw:continue
    path.write_bytes(raw.replace(old.encode(),new.encode()))
    changed_files+=1

projects=[]
for previous in databases:
    database=target/previous.relative_to(source)
    with sqlite3.connect(database) as connection:
        for pid,root,payload in connection.execute('SELECT id,root,state FROM projects').fetchall():
            state=json.loads(payload)
            state['root']=relocated(state['root'])
            for worker in state.get('workers',[]):
                worker['workspace']=relocated(worker['workspace'])
            updated=relocated(root)
            connection.execute('UPDATE projects SET root=?,state=? WHERE id=?',(updated,json.dumps(state),pid))
            projects.append((updated,state.get('workers',[])))
        for key,payload in connection.execute('SELECT key,value FROM settings').fetchall():
            value=json.loads(payload);updated=relocated(value)
            if updated!=value:connection.execute('UPDATE settings SET value=? WHERE key=?',(json.dumps(updated),key))
        for pid,role,payload in connection.execute('SELECT project,role,data FROM checkpoints').fetchall():
            value=json.loads(payload)
            if isinstance(value,dict) and isinstance(value.get('workspace'),str):
                updated=relocated(value['workspace'])
                if updated!=value['workspace']:
                    value['workspace']=updated
                    connection.execute('UPDATE checkpoints SET data=? WHERE project=? AND role=?',(json.dumps(value),pid,role))
for root,workers in projects:
    paths=[w['workspace'] for w in workers if Path(w['workspace']).is_dir()]
    if paths and (Path(root)/'.git').is_dir():
        subprocess.run(['git','-C',root,'worktree','repair',*paths],check=True,capture_output=True)

if git_status(target)!=status_before:
    raise SystemExit('Folder moved, but tracked-file status changed; inspect before running.')
for root,_ in projects:
    if not Path(root).is_dir():raise SystemExit('Folder moved; a saved project path needs attention: '+root)
print(json.dumps(dict(destination=str(target),old_folder_exists=source.exists(),projects_preserved=len(projects),environment_paths_updated=changed_files,started=False)))
