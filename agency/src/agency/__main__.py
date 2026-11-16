"""python3 -m agency [--port 8088] [--seed 1] [--tick 1.0]"""
import argparse
import logging
import os
import signal
import threading
import time

from . import auth, config, ledger, loader, returns, server
from .sim import Sim
from .store import Store

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def build(root, data_dir, seed=1, tick_s=1.0, token=None, warmup=150, **sim_kw):
    """sim_kw: model, fetch, clock (test mode; see Sim). Tests inject fakes here."""
    cfg = config.load(os.path.join(root, "config", "agency.json"))
    store = Store(cfg, os.path.join(data_dir, "audit.log"))
    app = server.App(store, Sim(store.org, seed, tick_s, data_dir=data_dir, **sim_kw), token, goal=ledger.Ledger(os.path.join(data_dir, "goal.json"), seed),
                     reinvest=returns.Reinvest(os.path.join(data_dir, "reinvest.json")))
    for _ in range(warmup):
        app.tick()
    return app


def main(argv=None):
    ap = argparse.ArgumentParser(prog="agency", description=__doc__)
    ap.add_argument("--root", default=ROOT, help="project folder holding config/ and departments/")
    ap.add_argument("--data-dir", default=None, help="token and audit log (default <root>/data)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8088)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tick", type=float, default=1.0, help="seconds per simulated tick")
    ap.add_argument("--no-auth", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")          # to stderr (the journal under systemd); the access key is only ever printed on stdout
    data_dir = a.data_dir or os.path.join(a.root, "data")
    try:
        app = build(a.root, data_dir, a.seed, a.tick, None if a.no_auth else auth.load_token(data_dir))
    except (config.ConfigError, loader.OrgError, returns.ReinvestError) as e:
        print("agency: cannot start: %s" % e)
        return 1
    httpd = server.serve(app, a.host, a.port)

    def ticker():
        while True:
            time.sleep(a.tick)
            app.tick()
    threading.Thread(target=ticker, daemon=True).start()
    signal.signal(signal.SIGINT, lambda *_: threading.Thread(target=httpd.shutdown, daemon=True).start())
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=httpd.shutdown, daemon=True).start())
    if app.sim.real:
        print("TEST MODE: real agents %s (model %s), PAPER trading on real prices; everything else is simulated" % (", ".join(sorted(app.sim.real.agents)), app.sim.real.name), flush=True)
    print("agency (simulated): http://%s:%d/%s" % (a.host, a.port, "" if a.no_auth else "?key=" + app.token), flush=True)
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
