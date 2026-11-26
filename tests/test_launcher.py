import errno
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from unittest.mock import Mock
import pytest
from appling import __main__ as launcher


@pytest.mark.parametrize('missing',[False,True])
def test_launcher_reuses_installed_runtime_and_bootstraps_only_missing_dependencies(tmp_path,missing):
    shutil.copyfile(Path(__file__).parents[1]/'start.sh',tmp_path/'start.sh')
    (tmp_path/'.venv/bin').mkdir(parents=True);(tmp_path/'ui/node_modules').mkdir(parents=True)
    (tmp_path/'bin').mkdir()
    trace=tmp_path/'calls'
    python=tmp_path/'.venv/bin/python'
    python.write_text('#!'+sys.executable+'\n'+'''
import os,sys,json
with open(os.environ['LAUNCH_TRACE'],'a') as f:f.write(json.dumps(['python',*sys.argv[1:]])+'\\n')
if sys.argv[1:]==['-m','appling.service','status','--quiet']:sys.exit(1)
if sys.argv[1]=='-c':sys.exit(int(os.environ['MISSING_RUNTIME']))
''');python.chmod(0o755)
    npm=tmp_path/'bin/npm'
    npm.write_text('#!'+sys.executable+'\n'+'''
import os,sys,json
with open(os.environ['LAUNCH_TRACE'],'a') as f:f.write(json.dumps(['npm',*sys.argv[1:]])+'\\n')
''');npm.chmod(0o755)
    env=dict(os.environ,PATH=str(tmp_path/'bin')+':'+os.environ['PATH'],
        LAUNCH_TRACE=str(trace),MISSING_RUNTIME=str(int(missing)))
    result=subprocess.run(['bash','start.sh','--no-open','--port','9230'],cwd=tmp_path,env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    import json
    calls=[json.loads(line) for line in trace.read_text().splitlines()]
    installs=[call for call in calls if call[:4]==['python','-m','pip','install']]
    assert len(installs)==int(missing)
    assert ['npm','run','build'] in calls
    assert calls[-1]==['python','-m','appling.service','start','--no-open','--port','9230']


def listener(port, failure=None):
    sock=Mock()
    sock.getsockname.return_value=('127.0.0.1',port)
    if failure:
        sock.bind.side_effect=failure
    return sock


def test_default_skips_occupied_port_and_retains_successful_socket(monkeypatch):
    occupied=listener(9210,OSError(errno.EADDRINUSE,'occupied'))
    free=listener(9211)
    factory=Mock(side_effect=[occupied,free]);monkeypatch.setattr(launcher.socket,'socket',factory)
    assert launcher.reserve_port(9210,fallback=True) is free
    occupied.close.assert_called_once()
    free.bind.assert_called_once_with(('127.0.0.1',9211))
    free.listen.assert_called_once();free.close.assert_not_called()


def test_explicit_port_never_silently_falls_back(monkeypatch):
    occupied=listener(9210,OSError(errno.EADDRINUSE,'occupied'))
    factory=Mock(return_value=occupied);monkeypatch.setattr(launcher.socket,'socket',factory)
    with pytest.raises(OSError) as error:
        launcher.reserve_port(9210)
    assert error.value.errno==errno.EADDRINUSE
    assert factory.call_count==1;occupied.close.assert_called_once()


def test_permission_failure_is_reported_without_trying_other_ports(monkeypatch):
    denied=listener(9210,PermissionError(errno.EPERM,'denied'))
    factory=Mock(return_value=denied);monkeypatch.setattr(launcher.socket,'socket',factory)
    with pytest.raises(PermissionError):
        launcher.reserve_port(9210,fallback=True)
    assert factory.call_count==1


def test_browser_and_server_use_the_reserved_port(monkeypatch,leftover_cleanup_stays_off):
    sock=listener(9212);sock.fileno.return_value=17
    monkeypatch.setattr(launcher,'reserve_port',lambda *a,**k:sock)
    # Leftovers of a force-quit server are stopped before this one creates its app and takes work.
    app=object();monkeypatch.setattr(launcher,'create_app',lambda home:leftover_cleanup_stays_off==[None] and app)
    config=Mock();monkeypatch.setattr(launcher.uvicorn,'Config',config)
    server=Mock();monkeypatch.setattr(launcher.uvicorn,'Server',server)
    browser=Mock();monkeypatch.setattr(launcher.webbrowser,'open',browser)
    timer=Mock(side_effect=lambda delay,callback:Mock(start=callback))
    monkeypatch.setattr(launcher.threading,'Timer',timer)
    monkeypatch.setattr('sys.argv',['appling-c'])
    launcher.main()
    browser.assert_called_once_with('http://127.0.0.1:9212')
    assert config.call_args.kwargs['port']==9212 and config.call_args.args==(app,)
    server.assert_called_once_with(config.return_value)
    # The reserved socket itself is handed over (uvicorn's fd= option does not work on Windows).
    server.return_value.run.assert_called_once_with(sockets=[sock])
    sock.close.assert_called_once()


def test_restart_reuses_port_after_closed_connection_without_sharing_live_listener():
    first=launcher.reserve_port(0)
    port=first.getsockname()[1]
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=2) as client:
            connection,_=first.accept()
            connection.sendall(b'closed')
            connection.close()
            assert client.recv(6)==b'closed'
            assert client.recv(1)==b''
    finally:
        first.close()
    replacement=launcher.reserve_port(port)
    try:
        with pytest.raises(OSError) as error:launcher.reserve_port(port)
        assert error.value.errno==errno.EADDRINUSE
    finally:
        replacement.close()


def test_sandbox_permission_denial_names_the_capability_and_recovery(monkeypatch,capsys):
    monkeypatch.setattr(launcher,'reserve_port',Mock(side_effect=PermissionError(errno.EPERM,'Operation not permitted')))
    monkeypatch.setattr(sys,'argv',['appling','--no-open'])
    with pytest.raises(SystemExit):
        launcher.main()
    err=capsys.readouterr().err
    assert 'binding was not permitted' in err and './start.sh' in err and 'normal Terminal' in err
