import pandas as pd
import pytest

from app.annual_research import ResearchPolicy,backtest,improvement_gate


def frame(day,open_=10,high=10.2,low=9.8,close=10):
    return pd.DataFrame([dict(date=day,symbol='sz000001',open=open_,high=high,low=low,close=close,
        amount=1e9,eligible=True,baseline_short=80,baseline_swing=80,change=1.,above20=1.,
        factor=1.,previous_factor=1.,previous_close=10.,limit=.1,atr_pct=.03,
        lot_min=100,trend_exit=False)])


def test_next_day_entry_and_no_same_day_stop():
    days={'2026-08-03':frame('2026-08-03'),
          '2026-08-04':frame('2026-08-04',high=10.1,low=8,close=9),
          '2026-08-05':frame('2026-08-05',open_=9.2,high=9.5,low=9.1,close=9.3)}
    r=backtest(days,ResearchPolicy('test',stop_atr=2),min(days),max(days))
    assert r['equity'][0]['holdings']==0
    assert r['equity'][1]['holdings']==1
    assert r['trades'][0]['entry_date']=='2026-08-04'
    assert r['trades'][0]['exit_date']=='2026-08-05'
    assert r['trades'][0]['exit_price']==pytest.approx(9.2*.999)


def test_limit_up_order_not_replaced_by_future_winner():
    days={'2026-08-03':frame('2026-08-03'),'2026-08-04':frame('2026-08-04',open_=11,high=11,low=11,close=11)}
    r=backtest(days,ResearchPolicy('test'),min(days),max(days))
    assert r['metrics']['net_return_pct']==0
    assert r['metrics']['open_positions']==0


def test_flat_price_costs_reduce_nav_and_open_position_not_win():
    days={f'2026-08-0{i}':frame(f'2026-08-0{i}') for i in [3,4]}
    r=backtest(days,ResearchPolicy('test'),min(days),max(days))
    assert r['metrics']['net_return_pct']<0
    assert r['metrics']['closed_trades']==0
    assert r['equity'][-1]['cash']>=0


def test_gate_rejects_high_return_with_worse_drawdown():
    b={'metrics':dict(net_return_pct=1,win_rate_pct=40,max_drawdown_pct=-5)}
    c={'metrics':dict(net_return_pct=20,win_rate_pct=70,max_drawdown_pct=-6,closed_trades=50,entry_days=30)}
    assert not improvement_gate(c,b)['passed']


def test_intraday_sale_cannot_free_opening_slots():
    days={}
    for i in range(5):
        day=f'2026-08-{i+3:02d}'
        records=[]
        for j in range(12):
            row=frame(day,low=9.3 if i==4 else 9.8).iloc[0].to_dict()
            row.update(symbol=f'sz{j+1:06d}',baseline_short=90 if i*3<=j<(i+1)*3 else 0)
            records.append(row)
        days[day]=pd.DataFrame(records)
    run=backtest(days,ResearchPolicy('slots',holding=20,stop_atr=2),min(days),max(days))
    # 最后一天开盘只剩一个空位；九笔盘中止损不能倒流改变开盘容量。
    assert run['equity'][-2]['holdings']==9
    assert run['equity'][-1]['holdings']==1
    assert run['metrics']['closed_trades']==9
