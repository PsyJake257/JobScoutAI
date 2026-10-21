class OperationCancelled(RuntimeError):
    pass


def abbruch_pruefen(abbruch_event) -> None:
    if abbruch_event is not None and abbruch_event.is_set():
        raise OperationCancelled("Vorgang wurde abgebrochen.")
