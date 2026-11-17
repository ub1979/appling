from __future__ import annotations
import argparse
import webbrowser
import threading
import uvicorn
from .server import create_app


def main():
    parser=argparse.ArgumentParser(description='Appling C — your local app studio')
    parser.add_argument('--port',type=int,default=9210)
    parser.add_argument('--home',help='Separate studio settings and state directory')
    parser.add_argument('--no-open',action='store_true')
    args=parser.parse_args()
    app=create_app(args.home)
    if not args.no_open:
        threading.Timer(1.2,lambda:webbrowser.open(f'http://127.0.0.1:{args.port}')).start()
    uvicorn.run(app,host='127.0.0.1',port=args.port,log_level='info')


if __name__=='__main__':
    main()
