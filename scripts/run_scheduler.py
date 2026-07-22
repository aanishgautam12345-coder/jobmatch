"""Run the single dedicated notification scheduler process."""

import signal
import threading

from app.services.scheduler import start_scheduler, stop_scheduler


def main() -> int:
    stopped = threading.Event()

    def shutdown(*_args):
        stopped.set()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    scheduler = start_scheduler()
    if scheduler is None:
        return 0
    try:
        stopped.wait()
    finally:
        stop_scheduler()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
