from __future__ import annotations
import argparse
import errno
import socket
import webbrowser
import threading
import uvicorn
from .server import create_app


def reserve_port(port, *, fallback=False):
    """Keep the socket bound until Uvicorn takes over, avoiding a port race."""
    for candidate in range(port, min(port + (50 if fallback else 1), 65536)):
        listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        try:
            # Allow an orderly restart on the same URL while closed HTTP/SSE
            # connections drain in TIME_WAIT. This does not share a live port.
            listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            listener.bind(('127.0.0.1',candidate))
            listener.listen(2048)
            return listener
        except OSError as exc:
            listener.close()
            if exc.errno!=errno.EADDRINUSE or not fallback:
                raise
    raise OSError(errno.EADDRINUSE,f'No free port found between {port} and {min(port+49,65535)}')


def main():
    parser=argparse.ArgumentParser(description='Appling C — your local app studio')
    parser.add_argument('--port',type=int,help='Use this exact port; otherwise try 9210 and the next available ports')
    parser.add_argument('--home',help='Separate studio settings and state directory')
    parser.add_argument('--no-open',action='store_true')
    parser.add_argument('--managed',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    port=9210 if args.port is None else args.port
    if not 0<=port<=65535:
        parser.error('Port must be between 0 and 65535.')
    try:
        listener=reserve_port(port,fallback=args.port is None)
    except OSError as exc:
        if exc.errno==errno.EADDRINUSE:
            parser.error(f'Port {port} is already in use. Omit --port to select an available port, or choose another port.')
        if exc.errno in {errno.EPERM,errno.EACCES}:
            # Seen when Appling is launched from inside another agent's sandbox,
            # which forbids binding localhost. The failed capability is reported as is.
            parser.error(f'Cannot open a localhost listener on 127.0.0.1:{port}: binding was not permitted ({exc}). '
                         'If you started Appling from inside another coding agent or sandboxed terminal, '
                         'start it from your normal Terminal instead: ./start.sh')
        parser.error(f'Cannot open a localhost listener: {exc}')
    try:
        actual_port=listener.getsockname()[1]
        url=f'http://127.0.0.1:{actual_port}'
        if actual_port!=port and port!=0:
            print(f'Port {port} is occupied; using {actual_port}.',flush=True)
        print(f'Open Appling: {url}',flush=True)
        app=create_app(args.home)
        if args.managed:
            from .service import serve_managed
            serve_managed(app,listener,actual_port,args.no_open)
            return
        if not args.no_open:
            threading.Timer(1.2,lambda:webbrowser.open(url)).start()
        uvicorn.run(app,host='127.0.0.1',port=actual_port,fd=listener.fileno(),log_level='info')
    finally:
        listener.close()


if __name__=='__main__':
    main()
