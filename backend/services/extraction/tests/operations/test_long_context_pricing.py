import pytest

from mujuthaek_extraction.model.pricing import PRICES


def test_long_context_charges_the_entire_request_at_the_higher_rate():
    price = PRICES["gpt-6-luna"]
    assert price.usd(272_000, 0, 0, 1000) == pytest.approx(0.0277)
    assert price.usd(272_001, 0, 0, 1000) == pytest.approx(0.0551502)
    assert price.usd(300_000, 100_000, 50_000, 1000) == pytest.approx((150_000 * 0.1 + 100_000 * 0.01 + 50_000 * 0.125) * 2 / 1_000_000 + 0.00075)


def test_budget_reservation_uses_the_long_context_rate_before_sending():
    price = PRICES["gpt-6-luna"]
    assert price.worst_usd(300_000, 2000) == pytest.approx(0.0765)
    assert price.worst_usd(300_000, 2000) >= price.usd(300_000, 0, 0, 2000)
