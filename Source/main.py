import logging
import os
import sys
import threading

from logging_config import log_pfad, richte_logging_ein


def _startfehler_anzeigen(fehler: Exception) -> None:
    try:
        richte_logging_ein()
        logging.error(
            "JobScout AI konnte nicht gestartet werden.",
            exc_info=(type(fehler), fehler, fehler.__traceback__),
        )
    except Exception:
        pass

    pfad = log_pfad()
    nachricht = (
        "JobScout AI konnte nicht gestartet werden.\n\n"
        f"Fehler: {fehler}\n\n"
        f"Weitere Details stehen in:\n{pfad}\n\n"
        "Soll die Logdatei jetzt geoeffnet werden?"
    )
    try:
        import tkinter as tk
        from ui_text import messagebox

        fenster = tk.Tk()
        fenster.withdraw()
        log_oeffnen = messagebox.askyesno("JobScout AI - Startfehler", nachricht)
        fenster.destroy()
        if log_oeffnen and pfad.exists():
            os.startfile(pfad)
    except Exception:
        pass


def main() -> int:
    portable_ai = None
    try:
        richte_logging_ein()
        from portable_ai import PortableAiRuntime

        portable_ai = PortableAiRuntime()
        # Warm in the background after constructing the UI, never before it appears.
        from app import JobScoutAI

        app = JobScoutAI()
        app.portable_ai = portable_ai
        def vorwaermen():
            portable_ai.vorwaermen()
            app._gui_ausfuehren(app._vorwaerm_status_aktualisieren)

        threading.Thread(target=vorwaermen, daemon=True, name="Gemma-Vorwaermen").start()
        if "--smoke-test" in sys.argv:
            from config import VERSION
            import json

            fehler = []

            def callback_fehler(typ, wert, traceback):
                fehler.append(typ.__name__)
                logging.error("Technischer Startcheck: GUI-Fehler", exc_info=(typ, wert, traceback))
                app.app.after(0, app.beenden)

            app.app.report_callback_exception = callback_fehler
            app._provider_status_aktualisieren = lambda: None
            app.zeige_einstellungen()

            def tour_pruefen(index=0):
                from setup_dialogs import EINLEITUNG

                app._einleitung_oeffnen()
                tour = app.einleitung_fenster
                if index < len(EINLEITUNG):
                    if tour.index != index:
                        tour.anzeigen(index)
                    ansicht, ziel, *_ = EINLEITUNG[index]

                    def sichtbar_pruefen():
                        widget = app._einleitungs_ziel(ziel)
                        if app.ansicht != ansicht or widget is None or not widget.winfo_viewable():
                            fehler.append(f"Tutorialziel nicht sichtbar: {ziel}")
                        app.app.after(80, lambda: tour_pruefen(index + 1))

                    app.app.after(500, sichtbar_pruefen)
                else:
                    tour.schliessen(speichern=False)
                    # Exercise the incremental layout without model calls or saved test jobs.
                    from models import Job
                    vorher = app.analyse_jobs
                    app.analyse_jobs = []
                    app.ki_laeuft = True
                    event = threading.Event()
                    app.ki_analyse_abbruch = event
                    app.zeige_ki_zusammenfassung()
                    container = app._ki_live_container
                    label = app._ki_live_label
                    app._ki_analyse_fortschritt(4, 20, None, event)
                    job = Job("Technischer Layoutcheck", "Test", "Test", "Test")
                    job.ki_zusammenfassung = "Technischer Test ohne Speicherung."
                    app._ki_analyse_fortschritt(1, 15, [job], event)
                    app._ki_analyse_fortschritt(1, 15, [job], event)
                    if (app._ki_live_container is not container or app._ki_live_label is not label
                            or len(container.winfo_children()) != 1):
                        fehler.append("Live-Analyse baut Widgets neu auf oder dupliziert Karten")
                    app.analyse_jobs = vorher
                    app.ki_laeuft = False
                    app.ki_analyse_abbruch = None
                    app.app.after(100, app.beenden)

            app.app.after(100, tour_pruefen)
            app.starten()
            if fehler:
                raise RuntimeError("Technischer Startcheck fehlgeschlagen: " + ", ".join(fehler))
            (log_pfad().parent / "startcheck.json").write_text(
                json.dumps({"version": VERSION, "startcheck": "ok"}), encoding="utf-8"
            )
        else:
            app.starten()
        return 0
    except Exception as fehler:
        if "--smoke-test" in sys.argv:
            logging.exception("Technischer Startcheck fehlgeschlagen.")
        else:
            _startfehler_anzeigen(fehler)
        return 1
    finally:
        if portable_ai is not None:
            portable_ai.beenden()

if __name__ == "__main__":
    raise SystemExit(main())
