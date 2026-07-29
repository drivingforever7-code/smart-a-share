from __future__ import annotations

import pytest

from app.market_service import MarketService, _stock_search_terms


@pytest.fixture
def service(monkeypatch) -> MarketService:
    instance = MarketService()
    items = [
        {"code": "600519", "name": "贵州茅台"},
        {"code": "000001", "name": "平安银行"},
        {"code": "300750", "name": "宁德时代"},
    ]
    monkeypatch.setattr(instance, "_analyzed_market", lambda _mode: (items, {}))
    return instance


def test_stock_name_has_full_pinyin_and_initials():
    assert _stock_search_terms("贵州茅台") == ("guizhoumaotai", "gzmt")


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("600519", "600519"),
        ("贵州茅台", "600519"),
        ("茅台", "600519"),
        ("guizhoumaotai", "600519"),
        ("gzmt", "600519"),
        ("payh", "000001"),
        ("ningde", "300750"),
    ],
)
def test_search_accepts_code_name_full_pinyin_and_initials(
    service: MarketService,
    query: str,
    expected: str,
):
    assert service.search(query)[0]["code"] == expected
