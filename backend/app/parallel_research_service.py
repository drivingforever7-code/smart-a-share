"""冻结方案的独立收盘影子研究，不修改旧版本或发现记录。"""
from __future__ import annotations

import json
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from threading import Event, Lock, Thread
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from .annual_research import ResearchPolicy, feature_frame, rank_candidates
from .config import DATA_DIR
from .research_quality import verified_quote_date
from .verified_quotes import parse_tencent_quotes

ASSET = Path(__file__).parent / 'research_assets' / 'parallel_v1.json'
STORE = DATA_DIR / 'parallel_research'
ARCHIVES = Path(__file__).resolve().parents[1] / 'parallel_archives'
SOURCE = 'https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get'
_lock = Lock()
_state = {'running': False, 'completed': 0, 'total': 0, 'message': '等待收盘研究', 'error': None}
_last_started = 0.0


def now_cn():
    return datetime.now(ZoneInfo('Asia/Shanghai'))


def read_asset():
    return json.loads(ASSET.read_text('utf-8'))


def fetch_verified_quotes(codes):
    """仅此研究接受盘后盘口；调用处还必须核对同日日线收盘。"""
    if not codes:
        return {}
    symbols = [('sh' if c.startswith('6') else 'bj' if c.startswith(('4', '8', '9')) else 'sz') + c for c in codes]
    response = requests.get('https://qt.gtimg.cn/q=' + ','.join(symbols), timeout=8)
    response.raise_for_status()
    response.encoding = 'gbk'
    return parse_tencent_quotes(response.text, allow_post_close=True)


def select_signals(frame: pd.DataFrame, policy: ResearchPolicy, checks: dict, expected: int):
    """先检验覆盖和市场，再检查最多三个候选；淘汰后不补位。"""
    coverage = len(frame) / max(expected, 1)
    breadth = float(frame.change.gt(0).mean()) if len(frame) else 0.0
    above20 = float(frame.above20.mean()) if len(frame) else 0.0
    info = {'coverage': coverage, 'stocks': len(frame), 'expected': expected,
            'rising_ratio': breadth, 'above20_ratio': above20}
    if coverage < .9:
        return [], ['同日有效日线覆盖不足90%，本次不生成候选'], info
    if breadth < .45 or above20 < .45:
        return [], ['市场上涨占比或站上20日均线占比低于45%，本期空榜'], info
    selected = rank_candidates(frame, policy)
    items, rejected = [], []
    for symbol in selected:
        row = frame[frame.symbol == symbol].iloc[0]
        check = checks.get(symbol, {})
        if not check.get('passed'):
            rejected.append(f"{row['name']}：{check.get('reason', '缺少同日收盘及风险核验')}")
            continue
        items.append({'code': symbol[2:], 'symbol': symbol, 'name': str(row['name']),
                      'price': float(row.close), 'score': float(row['baseline_' + policy.mode]),
                      'atr_pct': float(row.atr_pct), 'quote_time': check['quote_time'],
                      'confidence': check['confidence'], 'risks': check.get('risks', []),
                      'reasons': ['市场两项广度均通过45%门槛', '技术分达到70且日线流动性及波动合格', '同日收盘与线上风险检查通过']})
    if not items and not rejected:
        rejected.append('没有达到技术分及流动性、波动要求的股票')
    return items, rejected, info


def _fetch_row(stock: dict, target: str, tracking_dates=()):
    code = stock['code']
    symbol = ('sh' if code.startswith('6') else 'bj' if code.startswith(('4', '8', '9')) else 'sz') + code
    payload = {'symbol': symbol, 'stock': stock}
    for adjust, key in [('', 'raw'), ('qfq', 'adjusted')]:
        response = requests.get(SOURCE, params={'param': f'{symbol},day,,{target},640,{adjust}'}, timeout=15)
        response.raise_for_status()
        obj = response.json().get('data', {}).get(symbol, {})
        rows = obj.get('qfqday' if adjust else 'day') or obj.get('day') or []
        payload[key] = [r for r in rows if r[0] <= target]
    frame = feature_frame(payload)
    if frame.empty:
        return None
    bases = {str(r.date): float(r.close / r.factor) for _, r in frame[frame.date.isin(tracking_dates)].iterrows()}
    frame = frame[frame.date == target]
    if frame.empty:
        return None
    row = frame.iloc[-1]
    if not all(pd.notna(row[k]) for k in ['close', 'change', 'above20', 'atr_pct', 'baseline_short', 'baseline_swing']):
        return None
    return {**row.to_dict(), 'tracking_bases': bases}


def saved_snapshots():
    paths = {p.name: p for p in ARCHIVES.glob('????-??-??.json')}
    paths.update({p.name: p for p in STORE.glob('????-??-??.json')})
    snapshots = []
    for name in sorted(paths, reverse=True)[:60]:
        try:
            snapshots.append(json.loads(paths[name].read_text('utf-8')))
        except (OSError, ValueError):
            continue
    return snapshots


def latest_archive():
    snapshots = saved_snapshots()
    return {'snapshot': snapshots[0] if snapshots else None, 'state': dict(_state)}


def _close_date():
    """用指数原始盘口核实收盘，不用服务器日期充当行情日期。"""
    response = requests.get('https://qt.gtimg.cn/q=sh000001', timeout=8)
    response.raise_for_status()
    response.encoding = 'gbk'
    quote = parse_tencent_quotes(response.text, allow_post_close=True).get('000001', {})
    day = verified_quote_date(quote, close=True, allow_post_close=True)
    current = now_cn()
    if day is None or day != current.date() or (current.hour, current.minute) < (15, 5):
        return None
    response = requests.get(SOURCE, params={'param': f'sh000001,day,,{day.isoformat()},10,'}, timeout=15)
    response.raise_for_status()
    bars = response.json().get('data', {}).get('sh000001', {}).get('day', [])
    matching = [r for r in bars if r[0] == day.isoformat()]
    if not matching or abs(float(matching[-1][2]) / quote['price'] - 1) > .0001:
        raise ValueError('指数盘后盘口与同日日线收盘尚未一致，等待数据源稳定')
    return day.isoformat()


def _run():
    try:
        target = _close_date()
        if target is None:
            _state['message'] = '等待当日15:05后可核验的收盘行情；旧信号仅供历史研究'
            return
        STORE.mkdir(parents=True, exist_ok=True)
        path = STORE / f'{target}.json'
        if path.exists() or (ARCHIVES / path.name).exists():
            _state['message'] = f'{target} 收盘对比已保存，保留原始快照'
            return
        asset = read_asset()
        actual_hash = hashlib.sha256((Path(__file__).parent / 'annual_research.py').read_bytes()).hexdigest()
        if actual_hash != asset['engine_sha256']:
            raise ValueError('研究引擎与已验证版本不一致，停止生成信号')
        from .reliable_data_source import data_source
        from .market_service import market_service
        quotes, _ = data_source.get_spot_quotes()
        stocks = {q['code']: q for q in quotes if len(q.get('code', '')) == 6 and q['code'].isdigit()}
        expected = max(len(stocks), asset['universe_size'])
        if len(stocks) < 3000 or len(stocks) / expected < .9:
            raise ValueError('全市场行情样本不足，无法判断市场广度')
        _state.update(total=len(stocks), completed=0, message='更新全市场日线并核验同日数据')
        tracking = {}
        for saved in saved_snapshots():
            for group in saved['modes'].values():
                for item in [*group['items'], *group['old_items']]:
                    tracking.setdefault(item['code'], set()).add(saved['date'])
        rows, failures = [], 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(_fetch_row, q, target, tracking.get(q['code'], ())) for q in stocks.values()]
            for future in as_completed(futures):
                try:
                    row = future.result()
                    if row is not None:
                        rows.append(row)
                    else:
                        failures += 1
                except Exception:
                    failures += 1
                _state['completed'] += 1
        frame = pd.DataFrame(rows)
        if frame.empty:
            raise ValueError('没有取得当日有效日线')
        if len(frame) / expected < .9:
            raise ValueError(f'同日日线仅覆盖{len(frame)}/{expected}只，不保存为有效空榜，稍后可重试')
        snapshot = {'date': target, 'created_at': now_cn().isoformat(), 'kind': 'forward',
                    'source': SOURCE, 'failed_or_missing': failures, 'modes': {},
                    'engine_sha256': actual_hash, 'close_prices': {r['symbol']: r['close'] for r in rows},
                    'adjusted_closes': {r['symbol']: r['close'] / r['factor'] for r in rows},
                    'tracking_bases': {r['symbol']: r['tracking_bases'] for r in rows if r['tracking_bases']}}
        for mode in ['short', 'swing']:
            policy = ResearchPolicy(**asset['policies'][mode])
            checks = {}
            for symbol in rank_candidates(frame, policy):
                code = symbol[2:]
                try:
                    verified = fetch_verified_quotes([code]).get(code, {})
                    actual = market_service.stock_analysis(code, mode)
                    day = verified_quote_date(verified, close=True, allow_post_close=True)
                    row = frame[frame.symbol == symbol].iloc[0]
                    time_ok = day is not None and day.isoformat() == target
                    price_ok = abs(float(verified.get('price', 0)) / float(row.close) - 1) <= .005
                    analysis_price_ok = abs(float(actual.get('price') or 0) / float(row.close) - 1) <= .005
                    passed = time_ok and price_ok and analysis_price_ok and actual.get('confidence', 0) >= 60 and actual.get('score', 0) >= 70 and actual.get('recommendation') in ['建议买入', '建议小仓位试买']
                    checks[symbol] = {'passed': passed, 'quote_time': verified.get('quote_time'),
                                      'confidence': actual.get('confidence', 0), 'risks': actual.get('risks', []),
                                      'reason': '收盘时间/价格不一致，或线上风险、评分及置信度检查未通过'}
                except Exception:
                    checks[symbol] = {'passed': False, 'reason': '个股核验数据获取失败'}
            items, reasons, market = select_signals(frame, policy, checks, expected)
            old, old_note = [], ''
            try:
                candidates = market_service.opportunities(mode, limit=10)
                verified_old = fetch_verified_quotes([i['code'] for i in candidates])
                for item in candidates:
                    proof = verified_old.get(item['code'], {})
                    day = verified_quote_date(proof, close=True, allow_post_close=True)
                    symbol = ('sh' if item['code'].startswith('6') else 'bj' if item['code'].startswith(('4', '8', '9')) else 'sz') + item['code']
                    daily_close = snapshot['close_prices'].get(symbol)
                    if day is not None and day.isoformat() == target and daily_close and abs(daily_close / proof['price'] - 1) <= .005 and abs(float(item.get('price') or 0) / proof['price'] - 1) <= .005:
                        old.append({**{k: item.get(k) for k in ['code', 'name', 'price', 'score', 'confidence', 'recommendation', 'risks', 'reasons']}, 'quote_time': proof['quote_time']})
                    else:
                        old_note = '部分旧榜单缺少同日收盘核验，未纳入保存'
            except Exception:
                old_note = '旧网站当日榜单获取失败，不能视为旧方案空仓'
            snapshot['modes'][mode] = {'policy': asdict(policy), 'items': items, 'reasons': reasons,
                                       'market': market, 'old_items': old, 'old_note': old_note}
        # 同日快照只写一次；写完临时文件才发布，避免读到半份内容。
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(snapshot, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        temp.replace(path)
        _state['message'] = f'{target} 新旧方案收盘对比已保存'
    except Exception as exc:
        _state.update(error=str(exc)[:240], message='本次更新未完成，保留上次有效记录')
    finally:
        with _lock:
            _state['running'] = False


def start_refresh():
    global _last_started
    with _lock:
        if _state['running'] or time.monotonic() - _last_started < 300:
            return dict(_state)
        _last_started = time.monotonic()
        _state.update(running=True, completed=0, total=0, error=None, message='正在核实收盘日期')
        Thread(target=_run, daemon=True, name='parallel-research').start()
        return dict(_state)


def start_scheduler():
    """本地服务运行时收盘自动检查，关闭页面后仍可积累；随服务停止。"""
    stop = Event()
    def loop():
        while not stop.is_set():
            current = now_cn()
            if current.weekday() < 5 and (current.hour, current.minute) >= (15, 5):
                start_refresh()
            stop.wait(300)
    Thread(target=loop, daemon=True, name='parallel-research-scheduler').start()
    return stop


def parallel_research(mode: str = 'short', period: str = 'holdout'):
    asset = read_asset()
    snapshots = saved_snapshots()
    latest = snapshots[0] if snapshots else None
    history = []
    for saved in snapshots:
        data = saved['modes'][mode]
        tracked = {}
        for key in ['items', 'old_items']:
            items = []
            for item in data[key]:
                code = item['code']
                symbol = item.get('symbol') or ('sh' if code.startswith('6') else 'bj' if code.startswith(('4', '8', '9')) else 'sz') + code
                close = latest['close_prices'].get(symbol) if latest else None
                base = latest.get('tracking_bases', {}).get(symbol, {}).get(saved['date']) if latest else None
                adjusted_close = latest.get('adjusted_closes', {}).get(symbol) if latest else None
                change = None
                if base and adjusted_close and latest['date'] > saved['date']:
                    change = (adjusted_close / base - 1) * 100
                items.append({**item, 'latest_close': close, 'tracking_return_pct': change})
            tracked[key] = items
        history.append({'date': saved['date'], **data, **tracked})
    return {'mode': mode, 'period': period, 'policy': asset['policies'][mode],
            'research': asset['results'][period][mode], 'state': dict(_state),
            'history': history, 'latest_date': latest['date'] if latest else None,
            'today': now_cn().date().isoformat(), 'enabled': True, 'old_version_replaced': False,
            'seed': asset['seed'][mode],
            'limitations': asset['limitations']}
