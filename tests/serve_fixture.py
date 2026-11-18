"""Isolated browser-test desk; never uses real profiles, game builds, or AI accounts.

Run: python tests/serve_fixture.py
POST the desk's authenticated /api/shutdown to finish and clean its temp directory.
"""
import argparse
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading

from test_providers import MockProvider
import engine
import providers
import server


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=4181)
    parser.add_argument("--mock-port",type=int,default=4182)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="revision-room-fixture-") as tmp:
        server.ENGINE=engine.ReviewEngine(Path(tmp)/"runs")
        server.RUNS=server.ENGINE.root
        server.PROFILES=providers.ProfileStore(Path(tmp)/"profiles.json")
        server.INFO={"available":False,"loggedIn":False,"message":"测试环境：未连接真实 Codex"}
        server.builds=lambda: []
        remote=ThreadingHTTPServer(("127.0.0.1",args.mock_port),MockProvider)
        remote.url=f"http://127.0.0.1:{remote.server_port}"
        remote.calls=[];remote.release=threading.Event()
        thread=threading.Thread(target=remote.serve_forever,daemon=True);thread.start()
        desk=ThreadingHTTPServer(("127.0.0.1",args.port),server.Handler)
        print(f"Fixture desk: http://127.0.0.1:{desk.server_port}; mock: {remote.url}/v1",flush=True)
        try:
            desk.serve_forever()
        finally:
            desk.server_close();remote.release.set();remote.shutdown();remote.server_close();thread.join()


if __name__=="__main__":main()
