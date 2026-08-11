import dramatiq
from dramatiq.broker import Broker
from dramatiq.brokers.redis import RedisBroker
from dramatiq.brokers.stub import StubBroker

from app.core.config import get_settings
from app.runtime_jobs.profile import is_local_runtime_profile


def configure_broker() -> Broker:
    settings = get_settings()
    broker: Broker
    if is_local_runtime_profile(settings):
        broker = StubBroker()
    else:
        broker = RedisBroker(url=settings.redis_url)
    dramatiq.set_broker(broker)
    return broker


broker = configure_broker()
