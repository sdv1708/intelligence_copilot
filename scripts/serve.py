"""Build the frontend, then serve it and the API from one port.

    .venv/Scripts/python.exe -m scripts.serve                 # build, then serve
    .venv/Scripts/python.exe -m scripts.serve --port 8000
    .venv/Scripts/python.exe -m scripts.serve --skip-build    # serve what is there
    .venv/Scripts/python.exe -m scripts.serve --build-only    # bundle and stop

This is a wrapper, not a server. `api/main.py` already mounts `web/dist` and
installs the SPA fallback; what it does *not* do is build the bundle, and it
decides whether to serve one at **import time**, so a build that happens after
uvicorn has imported the app is a build that will not be served until a restart.
That ordering is the entire reason this script exists:

    npm run build   →   import api.main   →   uvicorn.run

Development wants the opposite arrangement — Vite on 5173 with hot reload,
proxying `/api` to uvicorn on 8077, which is two processes and two ports. Use
`.claude/launch.json` for that. This script is the single-process form: no CORS,
no proxy, one URL to open.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"
DIST_DIR = WEB_DIR / "dist"


def build_frontend() -> int:
    """Run `npm run build` in web/. Returns a process exit code.

    `shutil.which` first because npm missing is the common case on a machine set
    up for the backend only, and `FileNotFoundError` out of `subprocess` names
    the executable and nothing else — not what to do about it. On Windows npm is
    `npm.cmd`, which is why the resolved path is handed to `subprocess` rather
    than the bare name.
    """
    npm = shutil.which("npm")
    if npm is None:
        print(
            "npm was not found on PATH, so the frontend cannot be built.\n"
            "Install Node.js, or pass --skip-build to serve an existing bundle.",
            file=sys.stderr,
        )
        return 1

    # `flush` on everything printed before a subprocess: npm writes straight to
    # the console while this process's stdout is block-buffered when piped, so
    # without it the commentary arrives after the output it introduces.
    print(f"Building the frontend in {WEB_DIR} ...", flush=True)
    if not (WEB_DIR / "node_modules").is_dir():
        print("  node_modules is missing; running npm install first.", flush=True)
        installed = subprocess.run([npm, "install"], cwd=WEB_DIR)
        if installed.returncode != 0:
            return installed.returncode

    # `npm run build` is `tsc -b && vite build`, so a type error fails here
    # rather than shipping a stale bundle.
    return subprocess.run([npm, "run", "build"], cwd=WEB_DIR).returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the React frontend and serve it with the API on one port."
    )
    parser.add_argument("--port", type=int, default=8000, help="default: 8000")
    parser.add_argument("--host", default="127.0.0.1", help="default: 127.0.0.1")
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="serve whatever is already in web/dist",
    )
    parser.add_argument(
        "--build-only",
        action="store_true",
        help="build the bundle and exit without starting a server",
    )
    args = parser.parse_args(argv)

    if not args.skip_build:
        code = build_frontend()
        if code != 0:
            print("Frontend build failed; not starting the server.", file=sys.stderr)
            return code
    elif not (DIST_DIR / "index.html").is_file():
        # --skip-build with nothing to skip to. The API would still come up and
        # serve JSON perfectly well, but the user asked for the bundled app, so
        # silently starting an API-only server would be answering a different
        # question.
        print(
            f"--skip-build was given but there is no bundle at {DIST_DIR}.\n"
            "Drop the flag to build one.",
            file=sys.stderr,
        )
        return 1

    if args.build_only:
        print(f"Bundle written to {DIST_DIR}")
        return 0

    # Imported here, not at module scope: uvicorn and the FastAPI app between
    # them pull in torch and a provider SDK, and --build-only should not pay
    # several seconds for imports it never uses.
    import uvicorn

    print(f"\nServing the app and the API on http://{args.host}:{args.port}")
    print("Startup loads the embedding model; give it ~20 seconds.\n", flush=True)

    # The import string, rather than the imported object, so that api.main is
    # imported *after* the build above — `mount_frontend()` runs at import time
    # and only mounts a bundle that already exists.
    uvicorn.run("api.main:app", host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
