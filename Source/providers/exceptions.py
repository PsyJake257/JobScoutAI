class ProviderError(Exception):
    def __init__(
        self,
        technische_meldung: str,
        benutzer_meldung: str,
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
    ):
        super().__init__(technische_meldung)
        self.benutzer_meldung = benutzer_meldung
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
