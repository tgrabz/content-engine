#!/usr/bin/env python3
"""Background auto-updater. Polls git for changes and pulls automatically.
Backend hot-reload (uvicorn --reload) and Vite HMR pick up changes instantly."""

import subprocess
import time
import sys

INTERVAL = 60  # seconds between checks


def run(cmd, cwd=None):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)


def check_and_update(repo_dir):
    # Fetch latest
    run(["git", "fetch", "origin", "main"], cwd=repo_dir)

    # Check if behind
    local = run(["git", "rev-parse", "HEAD"], cwd=repo_dir).stdout.strip()
    remote = run(["git", "rev-parse", "origin/main"], cwd=repo_dir).stdout.strip()

    if local == remote:
        return False

    print(f"  Update found! {local[:8]} → {remote[:8]}")

    # Pull
    result = run(["git", "pull", "origin", "main", "--ff-only"], cwd=repo_dir)
    if result.returncode != 0:
        print(f"  Pull failed: {result.stderr}")
        return False

    # Install new deps if requirements changed
    diff = run(["git", "diff", f"{local}..{remote}", "--name-only"], cwd=repo_dir).stdout
    if "requirements.txt" in diff:
        print("  Installing new Python deps...")
        run(["pip", "install", "-q", "-r", "requirements.txt"], cwd=f"{repo_dir}/backend")
    if "package-lock.json" in diff:
        print("  Installing new frontend deps...")
        run(["npm", "ci", "--silent"], cwd=f"{repo_dir}/frontend")

    print("  Updated! Hot-reload will pick up changes.")
    return True


if __name__ == "__main__":
    from pathlib import Path
    repo_dir = str(Path(__file__).parent.parent)

    print(f"\n  Auto-updater watching for changes (every {INTERVAL}s)")
    print(f"  Repo: {repo_dir}\n")

    while True:
        try:
            check_and_update(repo_dir)
        except Exception as e:
            print(f"  Update check failed: {e}")
        time.sleep(INTERVAL)
