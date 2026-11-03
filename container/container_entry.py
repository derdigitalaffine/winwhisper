"""One private stdio service; Ollama is never published on the Windows network."""

import os
from pathlib import Path
import signal
import subprocess
import time
import urllib.request


def main():
    data = Path(os.environ.get("WINWHISPER_DATA", "/data"))
    (data / "logs").mkdir(parents=True, exist_ok=True)
    log = (data / "logs/ollama.log").open("ab")
    ollama = subprocess.Popen(
        ["ollama", "serve"], stdin=subprocess.DEVNULL, stdout=log, stderr=log
    )
    service = None

    def stop(*_):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(150):
            if ollama.poll() is not None:
                raise RuntimeError(
                    "Lokales Ollama konnte nicht starten. Siehe logs/ollama.log."
                )
            try:
                with opener.open("http://127.0.0.1:11434/api/version", timeout=1):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("Lokales Ollama antwortet nicht.")
        from whisperx_studio.managed_windows_service import WindowsService, serve

        service = WindowsService()
        serve(service)
    finally:
        try:
            if service and not service.closed:
                service.command("shutdown", {})
        finally:
            ollama.terminate()
            try:
                ollama.wait(timeout=5)
            except subprocess.TimeoutExpired:
                ollama.kill()
                ollama.wait()
            log.close()


if __name__ == "__main__":
    main()
