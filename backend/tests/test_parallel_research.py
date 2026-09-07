import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import parallel_research_service as service
from app.annual_research import ResearchPolicy
from app.main import app


@pytest.fixture(autouse=True)
def isolate_archives(monkeypatch, tmp_path):
    monkeypatch.setattr(service, 'ARCHIVES', tmp_path / 'packaged')


def frame():
    return pd.DataFrame([{'symbol': f'sh60000{i}', 'name': f'测试{i}', 'close': 10.,
        'change': 1., 'above20': 1., 'eligible': True, 'baseline_short': 90-i,
        'atr_pct': .02} for i in range(5)])


def test_no_replacement_after_risk_rejection():
    checks = {'sh600000': {'passed': True, 'quote_time': '2026-09-04 15:00:00', 'confidence': 70},
              'sh600003': {'passed': True, 'quote_time': '2026-09-04 15:00:00', 'confidence': 70}}
    items, reasons, _ = service.select_signals(frame(), ResearchPolicy('test', market_filter=True), checks, 5)
    assert [i['symbol'] for i in items] == ['sh600000']
    assert len(reasons) == 2


@pytest.mark.parametrize('condition', ['weak_market', 'missing_data', 'low_score'])
def test_empty_is_valid_and_never_filled(condition):
    data = frame()
    expected = 5
    if condition == 'weak_market':
        data['above20'] = 0
    elif condition == 'missing_data':
        expected = 10
    else:
        data['baseline_short'] = 60
    items, reasons, _ = service.select_signals(data, ResearchPolicy('test', market_filter=True), {}, expected)
    assert items == []
    assert reasons


def test_api_has_real_frozen_results_and_no_fake_forward_records(monkeypatch, tmp_path):
    monkeypatch.setattr(service, 'STORE', tmp_path)
    client = TestClient(app)
    response = client.get('/api/parallel-research?mode=swing&period=holdout')
    assert response.status_code == 200
    body = response.json()
    assert body['research']['candidate']['metrics']['net_return_pct'] == pytest.approx(-2.07420186)
    assert body['old_version_replaced'] is False
    assert body['history'] == []
    assert body['seed']['kind'] == 'reconstructed'
    assert client.get('/api/parallel-research?mode=invalid').status_code == 422


def test_tracking_uses_equivalent_adjustment_and_does_not_rewrite(monkeypatch, tmp_path):
    monkeypatch.setattr(service, 'STORE', tmp_path)
    item = {'code': '600000', 'symbol': 'sh600000', 'name': '测试', 'price': 10, 'score': 80}
    for day, close in [('2026-09-03', 10), ('2026-09-04', 5.5)]:
        payload = {'date': day, 'modes': {'short': {'items': [item], 'old_items': [item]}},
                   'close_prices': {'sh600000': close}, 'adjusted_closes': {'sh600000': close},
                   'tracking_bases': {'sh600000': {'2026-09-03': 5}}}
        (tmp_path / f'{day}.json').write_text(json.dumps(payload), encoding='utf-8')
    before = {p.name: p.read_bytes() for p in tmp_path.glob('*.json')}
    result = service.parallel_research()
    assert result['history'][1]['items'][0]['tracking_return_pct'] == pytest.approx(10.)
    assert result['history'][1]['old_items'][0]['tracking_return_pct'] == pytest.approx(10.)
    assert {p.name: p.read_bytes() for p in tmp_path.glob('*.json')} == before


def test_intraday_does_not_capture_even_if_previous_close_is_available(monkeypatch):
    class Response:
        text = ''
        def raise_for_status(self):
            pass
    monkeypatch.setattr(service.requests, 'get', lambda *a, **kw: Response())
    monkeypatch.setattr(service, 'parse_tencent_quotes', lambda _, **kw: {'000001': {'quote_time': '2026-09-04 15:00:00'}})

    monkeypatch.setattr(service, 'now_cn', lambda: datetime(2026, 9, 7, 11, 0, tzinfo=ZoneInfo('Asia/Shanghai')))
    assert service._close_date() is None


def test_refresh_is_single_flight(monkeypatch):
    monkeypatch.setitem(service._state, 'running', True)
    monkeypatch.setattr(service, 'Thread', lambda **kwargs: pytest.fail('不得启动第二个下载任务'))
    assert service.start_refresh()['running'] is True


@pytest.mark.parametrize('daily_price,valid', [(3000, True), (2990, False)])
def test_post_close_requires_matching_daily_close(monkeypatch, daily_price, valid):
    class Response:
        text = ''
        def raise_for_status(self):
            pass
        def json(self):
            return {'data': {'sh000001': {'day': [['2026-09-04', '3000', str(daily_price)]]}}}
    monkeypatch.setattr(service.requests, 'get', lambda *a, **kw: Response())
    monkeypatch.setattr(service, 'parse_tencent_quotes', lambda _, **kw: {'000001': {'price': 3000, 'quote_time': '2026-09-04 16:14:02'}})
    monkeypatch.setattr(service, 'now_cn', lambda: datetime(2026, 9, 4, 16, 30, tzinfo=ZoneInfo('Asia/Shanghai')))
    if valid:
        assert service._close_date() == '2026-09-04'
    else:
        with pytest.raises(ValueError, match='收盘尚未一致'):
            service._close_date()


def test_legacy_timestamp_rule_remains_strict():
    from app.research_quality import verified_quote_date
    stamp = {'quote_time': '2026-09-04 16:14:02'}
    assert verified_quote_date(stamp, close=True) is None
    assert str(verified_quote_date(stamp, close=True, allow_post_close=True)) == '2026-09-04'
