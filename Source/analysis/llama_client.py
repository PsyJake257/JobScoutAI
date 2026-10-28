"""Structured, cancellable chat requests against our local llama.cpp server."""
import json
import logging
import os
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import LOCAL_AI_ANALYSIS_MODEL, LOCAL_AI_ANALYSIS_TIMEOUT_SECONDS, LOCAL_AI_ANALYSIS_MAX_OUTPUT_TOKENS
from cancellation import OperationCancelled, abbruch_pruefen


class LlamaAnalysisClient:
    def __init__(self, model=LOCAL_AI_ANALYSIS_MODEL, base_url=None,
                 timeout_seconds=LOCAL_AI_ANALYSIS_TIMEOUT_SECONDS, response_schema=None,
                 max_output_tokens=LOCAL_AI_ANALYSIS_MAX_OUTPUT_TOKENS):
        self.model, self._base_url = model, base_url
        self.timeout_seconds, self.response_schema = timeout_seconds, response_schema
        self.max_output_tokens = max_output_tokens
        self.last_error_kind = self.last_error_message = ""
        self.last_metrics = {}
        self._aktive_antwort = None
        self._antwort_lock = threading.Lock()

    @property
    def base_url(self):
        return (self._base_url or os.environ.get("JOBSCOUT_OLLAMA_URL", "http://127.0.0.1:11436")).rstrip("/")

    def generate_json(self, prompt, abbruch_event=None):
        abbruch_pruefen(abbruch_event)
        if abbruch_event is None:
            return self._generate_json_synchron(prompt, None)
        result, done = {}, threading.Event()

        def run():
            try:
                result["value"] = self._generate_json_synchron(prompt, abbruch_event)
            except Exception as error:
                result["error"] = error
            finally:
                done.set()
        threading.Thread(target=run, daemon=True).start()
        while not done.wait(0.1):
            if abbruch_event.is_set():
                self.abbrechen()
                raise OperationCancelled("Lokale KI-Anfrage abgebrochen.")
        abbruch_pruefen(abbruch_event)
        if "error" in result:
            raise result["error"]
        return result.get("value")

    def _generate_json_synchron(self, prompt, abbruch_event):
        self.last_error_kind = self.last_error_message = ""
        self.last_metrics = {}
        format_ = {"type": "json_object"}
        if self.response_schema:
            format_ = {"type": "json_schema", "json_schema": {"name": "jobscout", "schema": self.response_schema}}
        payload = {"model": self.model, "messages": [{"role": "user", "content": prompt}],
                   "stream": True, "temperature": 0.1, "max_tokens": self.max_output_tokens,
                   "response_format": format_, "chat_template_kwargs": {"enable_thinking": False},
                   "reasoning_effort": "none"}
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + os.environ.get("JOBSCOUT_LOCAL_AI_KEY", "")}
        request = Request(self.base_url + "/v1/chat/completions", data=json.dumps(payload).encode(), headers=headers, method="POST")
        started, chunks, finish = time.perf_counter(), [], ""
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                with self._antwort_lock:
                    self._aktive_antwort = response
                try:
                    while line := response.readline():
                        abbruch_pruefen(abbruch_event)
                        if time.perf_counter() - started > self.timeout_seconds:
                            raise TimeoutError("Zeitlimit pro Stelle")
                        if not line.startswith(b"data:"):
                            continue
                        raw = line[5:].strip()
                        if raw == b"[DONE]":
                            break
                        event = json.loads(raw)
                        if event.get("error"):
                            raise ValueError("Fehler im lokalen Antwortstream")
                        for choice in event.get("choices", []):
                            chunks.append(choice.get("delta", {}).get("content") or "")
                            finish = choice.get("finish_reason") or finish
                finally:
                    with self._antwort_lock:
                        if self._aktive_antwort is response:
                            self._aktive_antwort = None
            abbruch_pruefen(abbruch_event)
            if finish == "length":
                self._fehler_setzen("output_limit", "Die Antwort hat das Ausgabelimit erreicht.")
                return None
            from analysis.ai_analysis import _parse_json_object
            data = _parse_json_object("".join(chunks))
            if not isinstance(data, dict) or not finish:
                self._fehler_setzen("invalid_json", "Keine vollständige strukturierte Antwort.")
                return None
            self.last_metrics = {"elapsed_seconds": round(time.perf_counter() - started, 2), "done_reason": finish}
            logging.info("Gemma-Antwort: Modell=%s, Dauer=%.1fs, Grund=%s.", self.model, self.last_metrics["elapsed_seconds"], finish)
            return data
        except OperationCancelled:
            raise
        except HTTPError as error:
            self._fehler_setzen("http", f"HTTP {error.code}")
        except (TimeoutError, URLError, OSError) as error:
            abbruch_pruefen(abbruch_event)
            self._fehler_setzen("timeout" if isinstance(error, TimeoutError) or "timed out" in str(error) else "connection", "Lokale Anfrage fehlgeschlagen.")
        except (ValueError, TypeError):
            self._fehler_setzen("invalid_response", "Ungültige lokale Modellantwort.")
        logging.warning("Gemma-Anfrage fehlgeschlagen: %s", self.last_error_kind)
        return None

    def abbrechen(self):
        with self._antwort_lock:
            response = self._aktive_antwort
            self._aktive_antwort = None
        if response is not None:
            def close():
                try:
                    response.close()
                except OSError:
                    pass
            threading.Thread(target=close, daemon=True).start()

    def _fehler_setzen(self, art, meldung):
        self.last_error_kind, self.last_error_message = art, meldung
