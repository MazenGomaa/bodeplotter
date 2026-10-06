# Spec: web frontend (roadmap phase E2)

Part of the design spec. Overview and the index of all sections: `docs/SPEC.md`. Section numbers are kept, because the code cites them.
Nothing of this is built. It is milestone E2 of `docs/spec/roadmap.md` (section 15, Phase E) and must not be started before the Pi hardware gate E1 has been reported.

## E2. Web frontend

FastAPI + WebSocket, plotting in the browser. It lives in this repository as a second frontend, `web/` next to `gui/`, sharing `sweep/core.py`, the drivers, the I/O layer and the math. No long-lived fork: a feature branch during development only, then merge. Requirements:
- sweep state on the server: a sweep goes on if the browser disconnects, and a reconnecting browser shows the progress;
- one controlling client, the others view only;
- generator `safe_off` on abort, on error and on server shutdown, plus the watchdog;
- LAN only, with a simple password (this is the Pi's network; the instruments stay on USB, and instrument LAN was dropped by the user on 2026-10-06);
- logs in RAM or with a small rotation (SD card wear);
- exports downloadable from the browser.

Developed and tested first in WSL / Windows against the mocks, then deployed to the Pi.
