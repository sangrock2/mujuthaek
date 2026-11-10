"""LH 테스트 공용 픽스처: 실제 LH·마이홈 응답(fixtures/lh)과 가짜 요청 클라이언트."""

import pytest

from tests.sources.lh.helpers import FakeLhClient, load_fixture, taebaek_myhome_row


@pytest.fixture
def list_body():
    return load_fixture("list.json")


@pytest.fixture
def detail_body():
    return load_fixture("detail.json")


@pytest.fixture
def supply_body():
    return load_fixture("supply.json")


@pytest.fixture
def myhome_rent_body():
    return load_fixture("myhome-rent.json")


@pytest.fixture
def myhome_sale_body():
    return load_fixture("myhome-sale.json")


@pytest.fixture
def lh(list_body, detail_body, supply_body, myhome_rent_body):
    fake = FakeLhClient(list_body, detail_body, supply_body, myhome_rent_body)
    fake.myhome["rent"] = [taebaek_myhome_row()]
    return fake
