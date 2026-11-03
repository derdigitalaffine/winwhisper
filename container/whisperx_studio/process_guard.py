"""Set Linux parent-death handling before exec, without threaded preexec_fn.

WhisperX workers must release resources even if their service crashes. For the
recorder SIGINT lets PipeWire finish the WAV header instead of leaving it open.
"""

from __future__ import annotations

import ctypes
import os
import signal
import sys


def main():
    parent, death_signal = int(sys.argv[1]), int(sys.argv[2])
    command = sys.argv[3:]
    if not command or death_signal not in (signal.SIGTERM, signal.SIGINT):
        raise ValueError("Ungültiger Prozessauftrag.")
    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(1, death_signal, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
        # The parent can exit between fork and prctl; close that race explicitly.
        if os.getppid() != parent:
            raise SystemExit(1)
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
