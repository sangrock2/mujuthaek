import pytest

from mujuthaek_collector.config import Settings
from mujuthaek_collector.core.http_client import clear_robots_cache
from tests.fakes import FakeClient, MemoryFileStore, MemoryStore


@pytest.fixture
def settings():
    return Settings(db_url="", rabbitmq_url="", s3_endpoint=None, s3_bucket="test", delay_seconds=0, max_pages=3, detail_limit=20)


@pytest.fixture
def store():
    return MemoryStore()


@pytest.fixture
def file_store():
    return MemoryFileStore()


@pytest.fixture
def client():
    return FakeClient()


@pytest.fixture(autouse=True)
def fresh_robots_cache():
    """robots.txt 캐시는 프로세스 전체가 같이 써서, 테스트끼리 섞이지 않게 매번 비워요."""
    clear_robots_cache()
    yield
    clear_robots_cache()
