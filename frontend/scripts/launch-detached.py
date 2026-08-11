"""Launch a process fully detached from the calling shell/session.

Usage: launch-detached.py <cwd> <logfile> <cmd...>

The child is started in a new session (``start_new_session=True``) so it
survives the parent shell exiting — including a laptop-restart-style cleanup of
the terminal's process group. stdout/stderr go to <logfile>.
"""
from __future__ import annotations

import subprocess
import sys


def main() -> int:
    if len(sys.argv) < 4:
        print("usage: launch-detached.py <cwd> <logfile> <cmd...>", file=sys.stderr)
        return 2
    cwd, log, cmd = sys.argv[1], sys.argv[2], sys.argv[3:]
    with open(log, "ab") as logfile:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=logfile,
            stderr=logfile,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    print(proc.pid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
