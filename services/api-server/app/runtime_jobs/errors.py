class RuntimeJobDeferredError(RuntimeError):
    """Ask the coordinator to release a job without consuming an attempt."""

    def __init__(self, reason: str, *, delay_seconds: float = 30.0) -> None:
        super().__init__(reason)
        self.reason = reason
        self.delay_seconds = delay_seconds
