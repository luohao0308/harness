import signal
import time

from app.sandbox.warm_pool import WarmPoolManager


def run_warm_pool_service() -> None:
    running = True

    def stop(_signum, _frame) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    manager = WarmPoolManager()
    while running:
        manager.prewarm()
        time.sleep(5)


if __name__ == "__main__":
    run_warm_pool_service()
