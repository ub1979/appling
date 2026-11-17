import errno
from unittest.mock import Mock
import pytest
from appling import __main__ as launcher


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


def test_browser_and_server_use_the_reserved_port(monkeypatch):
    sock=listener(9212);sock.fileno.return_value=17
    monkeypatch.setattr(launcher,'reserve_port',lambda *a,**k:sock)
    app=object();monkeypatch.setattr(launcher,'create_app',lambda home:app)
    server=Mock();monkeypatch.setattr(launcher.uvicorn,'run',server)
    browser=Mock();monkeypatch.setattr(launcher.webbrowser,'open',browser)
    timer=Mock(side_effect=lambda delay,callback:Mock(start=callback))
    monkeypatch.setattr(launcher.threading,'Timer',timer)
    monkeypatch.setattr('sys.argv',['appling-c'])
    launcher.main()
    browser.assert_called_once_with('http://127.0.0.1:9212')
    assert server.call_args.kwargs['port']==9212
    assert server.call_args.kwargs['fd']==17
    assert server.call_args.args==(app,)
    sock.close.assert_called_once()
