from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command):
    print("$", " ".join(command))
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main():
    parser = argparse.ArgumentParser(
        description="SentiOH repeatable integration health check."
    )
    parser.add_argument(
        "--git-pull",
        action="store_true",
        help="Run git pull first when this folder is connected to the team repository.",
    )
    args = parser.parse_args()

    if args.git_pull:
        run(["git", "pull", "--ff-only"])

    run([sys.executable, "ingestion/load_data.py", "--data-dir", "demo_data"])
    run([sys.executable, "matching/evaluate.py", "--data-dir", "demo_data"])
    run([sys.executable, "scripts/check_recall_data.py"])
    run([sys.executable, "scripts/validate_fsai_snapshot.py"])
    run([sys.executable, "scripts/check_real_fsai_showcase.py"])
    run([sys.executable, "scripts/check_all_fsai_agent_termination.py"])
    run([sys.executable, "smoke_test.py"])
    run([sys.executable, "-m", "pytest", "-q"])
    print("PASS: SentiOH integration health check completed.")


if __name__ == "__main__":
    main()
