# Overheard
Network monitoring and Pi-hole-like ad blocking built for the Arduino UNO Q: a stdlib-only Python DNS filter with a lock-protected dashboard, LED matrix characters, a 3DS page and a Mac launcher.

- Start here: [HANDOFF.md](HANDOFF.md) (everything: goals, rules, state, next steps).
- Current build: this folder (r17). Older builds: `archive/`. Planning docs: `docs/planning/`. Agency project (separate, runs on a local server): `agency/`.
- Install on the board: double-click `Install Overheard.command` (Mac), then `Check Overheard.command`.
- Several boards (home, apartment): one `sites/<name>.conf` each, then double-click `Link Sites.command`; each dashboard shows the others as a read-only summary ([docs/multi-site.md](docs/multi-site.md)).
- Dev: `make ci` (ruff, sprite check, pytest, smoke). Python 3 stdlib only at runtime.
- No keys or secrets are in this repo.
