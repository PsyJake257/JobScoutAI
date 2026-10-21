import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


PORTABLE_OLLAMA_HOST = "127.0.0.1:11435"
PORTABLE_OLLAMA_URL = f"http://{PORTABLE_OLLAMA_HOST}"
PORTABLE_MODEL = "qwen3:4b"


class PortableAiRuntime:
    def __init__(self, basis_ordner: Path | None = None):
        self.basis_ordner = basis_ordner or _basis_ordner()
        self.runtime_ordner = self.basis_ordner / "runtime" / "ollama"
        self.ollama_exe = self.runtime_ordner / "ollama.exe"
        self.model_ordner = self.basis_ordner / "models"
        self.prozess: subprocess.Popen | None = None
        self._log_stream = None

    def starten(self) -> bool:
        if not self.ollama_exe.is_file() or not self.model_ordner.is_dir():
            logging.info("Keine eingebettete KI-Laufzeit gefunden; verwende externes Ollama.")
            return False

        os.environ["JOBSCOUT_OLLAMA_URL"] = PORTABLE_OLLAMA_URL
        if self._bereit():
            logging.info("Portable KI-Laufzeit ist bereits unter %s erreichbar.", PORTABLE_OLLAMA_URL)
            return True

        umgebung = os.environ.copy()
        umgebung.update(
            {
                "OLLAMA_HOST": PORTABLE_OLLAMA_HOST,
                "OLLAMA_MODELS": str(self.model_ordner),
                "OLLAMA_NOHISTORY": "1",
            }
        )
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if self.prozess is None or self.prozess.poll() is not None:
            if self._log_stream is not None:
                self._log_stream.close()
            log_ordner = self.basis_ordner / "data" / "logs"
            log_ordner.mkdir(parents=True, exist_ok=True)
            self._log_stream = (log_ordner / "ollama.log").open("ab")
            try:
                self.prozess = subprocess.Popen(
                    [str(self.ollama_exe), "serve"],
                    cwd=self.runtime_ordner,
                    env=umgebung,
                    stdin=subprocess.DEVNULL,
                    stdout=self._log_stream,
                    stderr=self._log_stream,
                    creationflags=flags,
                )
            except OSError:
                self._log_stream.close()
                self._log_stream = None
                raise
        for _ in range(40):
            if self._bereit():
                logging.info("Portable KI-Laufzeit gestartet: %s mit %s.", PORTABLE_OLLAMA_URL, PORTABLE_MODEL)
                return True
            if self.prozess.poll() is not None:
                break
            time.sleep(0.25)

        logging.warning("Portable KI-Laufzeit konnte nicht gestartet werden.")
        self.beenden()
        return False

    def beenden(self) -> None:
        if self.prozess is None or self.prozess.poll() is not None:
            if self._log_stream is not None:
                self._log_stream.close()
                self._log_stream = None
            return
        try:
            self.prozess.terminate()
            self.prozess.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.run(
                ["taskkill", "/PID", str(self.prozess.pid), "/T", "/F"],
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
            )
        finally:
            self.prozess = None
            if self._log_stream is not None:
                self._log_stream.close()
                self._log_stream = None

    def _bereit(self) -> bool:
        try:
            with urlopen(f"{PORTABLE_OLLAMA_URL}/api/tags", timeout=0.5) as antwort:
                daten = json.loads(antwort.read().decode("utf-8"))
        except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
            return False
        namen = {str(modell.get("name", "")) for modell in daten.get("models", [])}
        return PORTABLE_MODEL in namen or f"{PORTABLE_MODEL}:latest" in namen


def _basis_ordner() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent
