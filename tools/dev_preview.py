"""Run an isolated first-use preview without resetting the normal database."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--fresh", action="store_true", help="Create an independent empty database")
parser.add_argument("--port", type=int, default=8874)
args = parser.parse_args()
env = os.environ.copy()
if args.fresh:
    preview_dir = Path(tempfile.mkdtemp(prefix="prism-preview-"))
    env["PRISM_DB_PATH"] = str(preview_dir / "preview.sqlite3")
    env.pop("PRISM_DATABASE_URL", None)
    print(f"Independent preview database: {env['PRISM_DB_PATH']}", flush=True)
print(f"Open http://127.0.0.1:{args.port}/?onboarding=1", flush=True)
subprocess.run([sys.executable, "-m", "uvicorn", "app.api.main:app", "--host", "127.0.0.1", "--port", str(args.port)], env=env, check=True, cwd=Path(__file__).resolve().parents[1])
