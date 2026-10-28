"""Bundled offline llama.cpp runtime for Gemma 4 E2B."""
import json
import logging
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time
from urllib.request import Request, urlopen

from config import LOCAL_AI_ANALYSIS_CONTEXT_TOKENS, LOCAL_AI_ANALYSIS_MODEL

PORTABLE_MODEL = LOCAL_AI_ANALYSIS_MODEL
MODEL_FILE = "gemma-4-E2B-it-Q4_K_M.gguf"


class PortableAiRuntime:
    def __init__(self, basis_ordner=None):
        self.basis_ordner = Path(basis_ordner or (Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent))
        self.model_ordner = self.basis_ordner / "models"
        self.ollama_exe = self.basis_ordner / "runtime" / "cpu" / "llama-server.exe"
        self.prozess = None
        self._log_stream = None
        self.backend = ""
        self.url = ""
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._warm_client = None
        self._vorgewaermt = False
        self.vorwaerm_status = "Noch nicht vorbereitet"

    def starten(self):
        with self._lock:
            return self._starten()

    def _starten(self):
        if self._stop_event.is_set():
            return False
        if self.prozess is not None and self.prozess.poll() is None and self._bereit():
            return True
        self._stop_process()
        if not (self.model_ordner / MODEL_FILE).is_file():
            raise RuntimeError(f"Gemma-Modell fehlt: {self.model_ordner / MODEL_FILE}")
        for backend in ("vulkan", "cpu"):
            if self._stop_event.is_set():
                return False
            executable = self.basis_ordner / "runtime" / backend / "llama-server.exe"
            if not executable.is_file():
                continue
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            key = secrets.token_urlsafe(32)
            self.url = f"http://127.0.0.1:{port}"
            os.environ["JOBSCOUT_OLLAMA_URL"] = self.url
            os.environ["JOBSCOUT_LOCAL_AI_KEY"] = key
            self.backend = backend
            logs = self.basis_ordner / "data" / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            self._log_stream = (logs / "llama.log").open("ab")
            args = [str(executable), "--model", str(self.model_ordner / MODEL_FILE),
                    "--alias", PORTABLE_MODEL, "--host", "127.0.0.1", "--port", str(port),
                    "--api-key", key, "--offline", "--no-webui", "--no-agent", "--no-slots",
                    "--ctx-size", str(LOCAL_AI_ANALYSIS_CONTEXT_TOKENS), "--parallel", "1",
                    "--threads", str(max(2, min(8, (os.cpu_count() or 4) // 2))),
                    "--n-gpu-layers", "-1" if backend == "vulkan" else "0"]
            try:
                self.prozess = subprocess.Popen(args, cwd=executable.parent, stdin=subprocess.DEVNULL,
                                               stdout=self._log_stream, stderr=self._log_stream,
                                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                process = self.prozess
                deadline = time.monotonic() + 60
                while not self._stop_event.is_set() and time.monotonic() < deadline and process.poll() is None:
                    if self._bereit():
                        if self._stop_event.is_set():
                            break
                        logging.info("Gemma 4 E2B bereit: Backend=%s, Modell=%s.", backend, PORTABLE_MODEL)
                        return True
                    time.sleep(0.2)
            except OSError:
                logging.warning("Gemma-Laufzeit konnte mit %s nicht starten.", backend)
            self._stop_process()
        if self._stop_event.is_set():
            return False
        raise RuntimeError("Gemma-Laufzeit startet nicht. Details: data/logs/llama.log")

    def vorwaermen(self):
        with self._lock:
            if self._stop_event.is_set() or self._vorgewaermt:
                return
            self.vorwaerm_status = "Vorbereitung läuft im Hintergrund"
            try:
                if not self.starten():
                    return
                from analysis.llama_client import LlamaAnalysisClient
                self._warm_client = LlamaAnalysisClient(response_schema={
                    "type": "object", "properties": {"bereit": {"type": "boolean", "const": True}},
                    "required": ["bereit"], "additionalProperties": False,
                }, max_output_tokens=16)
                prompt = ("Technische lokale Textverarbeitung ohne personenbezogene Daten. " * 40
                          + 'Diese technischen Platzhalter nicht auswerten. Antworte nur mit {"bereit":true}.')
                result = self._warm_client.generate_json(prompt, self._stop_event)
                self._vorgewaermt = result == {"bereit": True}
                self.vorwaerm_status = "Bereit" if self._vorgewaermt else "Modell geladen; Aufwärmanfrage fehlgeschlagen"
                logging.info("Gemma-Vorwärmen: %s, Backend=%s.", self.vorwaerm_status, self.backend)
            except Exception:
                if not self._stop_event.is_set():
                    self.vorwaerm_status = "Vorwärmen fehlgeschlagen; erneuter Start bei KI-Aktion"
                    logging.exception("Gemma konnte im Hintergrund nicht vorgewärmt werden.")
            finally:
                self._warm_client = None

    def _bereit(self):
        try:
            request = Request(self.url + "/v1/models", headers={"Authorization": "Bearer " + os.environ.get("JOBSCOUT_LOCAL_AI_KEY", "")})
            with urlopen(request, timeout=0.5) as response:
                models = json.load(response).get("data", [])
            return any(item.get("id") == PORTABLE_MODEL for item in models)
        except (OSError, ValueError):
            return False

    def beenden(self):
        self._stop_event.set()
        client = self._warm_client
        if client is not None:
            client.abbrechen()
        self._stop_process()

    def _stop_process(self):
        process, self.prozess = self.prozess, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        stream, self._log_stream = self._log_stream, None
        if stream is not None:
            stream.close()
        self._vorgewaermt = False
