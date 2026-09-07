"""独立一年技术研究：可重建基准、候选、次日成交和组合净值。"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import sqrt

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ResearchPolicy:
    name: str
    mode: str = 'short'
    family: str = 'baseline'
    market_filter: bool = False
    max_gap: float = 1.0
    stop_atr: float = 0.0
    trailing_atr: float = 0.0
    take_atr: float = 0.0
    holding: int = 5


def policy_grid():
    """预先固定候选，禁止根据最终留出结果扩大搜索。"""
    result = []
    for mode, holding in [('short', 5), ('swing', 15)]:
        for family in ['baseline', 'trend', 'pullback', 'breakout', 'balanced', 'reversal', 'lowvol']:
            for stage in [0, 1, 2]:
                result.append(ResearchPolicy(f'{mode}-{family}-r{stage+1}', mode, family,
                    market_filter=stage >= 1, max_gap=.03 if stage >= 1 else 1.,
                    stop_atr=2.0 if stage == 2 else 0., trailing_atr=2.5 if stage == 2 else 0.,
                    take_atr=4.0 if stage == 2 else 0., holding=holding))
    return result


def feature_frame(payload: dict) -> pd.DataFrame:
    """所有因子仅用当日及更早日K；量比是日线代理而非历史盘中量比。"""
    raw = {row[0]: row for row in payload['raw']}
    rows = []
    for adj in payload['adjusted']:
        day = adj[0]
        if day not in raw:
            continue
        r = raw[day]
        try:
            rows.append([day, *map(float, r[1:6]), float(r[7]), float(r[8])*10000,
                         *map(float, adj[1:5])])
        except (ValueError, TypeError, IndexError):
            continue
    f = pd.DataFrame(rows, columns=['date','open','close','high','low','volume','turnover','amount','ao','ac','ah','al'])
    if len(f) < 125:
        return pd.DataFrame()
    f = f.drop_duplicates('date').sort_values('date').reset_index(drop=True)
    valid = (f[['open','close','high','low','ao','ac','ah','al']] > 0).all(axis=1)
    valid &= f.high.ge(f[['open','close','low']].max(axis=1)) & f.low.le(f[['open','close']].min(axis=1))
    f.loc[~valid, ['ao','ac','ah','al']] = np.nan
    c = f.ac
    ma5, ma10, ma20, ma60 = [c.rolling(n).mean() for n in [5,10,20,60]]
    change = c.pct_change(fill_method=None)*100
    ret5 = c.pct_change(5, fill_method=None)*100
    ret20 = c.pct_change(20, fill_method=None)*100
    vr = f.volume / f.volume.shift().rolling(5).mean().replace(0,np.nan)
    amp = (f.ah-f.al)/c.shift()*100
    delta=c.diff();gain=delta.clip(lower=0).rolling(14).mean();loss=(-delta.clip(upper=0)).rolling(14).mean()
    rsi=100-100/(1+gain/loss.replace(0,1e-12))
    dif=c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean()
    macd=dif-dif.ewm(span=9,adjust=False).mean()
    position=((c-f.al)/(f.ah-f.al).replace(0,np.nan)).fillna(.5)
    high_distance=(c/f.ah.rolling(20).max()-1)*100
    trend=4+5*(c>ma5)+6*(ma5>ma10)+6*(ma10>ma20)+4*(ma5>ma5.shift(3))
    momentum=7+np.select([change.between(.5,5),change>7,change<-3],[5,1,-3],0)+np.where(macd>0,3,-1)+np.select([rsi.between(45,70),rsi>80],[3,-2],0)
    volume=5+((vr-.8)*5).clip(-2,7)+np.select([f.turnover.between(2,12),f.turnover>20],[5,1],0)+np.select([f.amount>=5e8,f.amount>=1e8,f.amount<3e7],[3,2,-3],0)
    intraday=6+np.where(c>=f.ao,3,-2)+((position-.4)*7).clip(-2,4)
    pattern=4+np.select([high_distance.between(-3,0),high_distance<-12],[5,-1],0)
    risk=10-3*(amp>8)-3*(change.abs()>7)-2*(f.turnover>25)-4*(f.amount<3e7)
    f['baseline_short']=trend.clip(0,25)+momentum.clip(0,20)+volume.clip(0,20)+intraday.clip(0,15)+pattern.clip(0,10)+risk.clip(0,10)
    # 波段仅技术维度重标为100分，历史基本面缺失绝不以当前值回填。
    f['baseline_swing']=((8+7*(c>ma20)+5*(ma20>ma60)+5*(ma20>ma20.shift(5)))+volume.clip(0,20)/2+pattern.clip(0,10)+risk.clip(0,10)/2)*2
    tr=pd.concat([f.ah-f.al,(f.ah-c.shift()).abs(),(f.al-c.shift()).abs()],axis=1).max(axis=1)
    f['atr_pct']=tr.rolling(14).mean()/c
    f['trend']=(ret20/f['atr_pct'].mul(100).clip(lower=.5)).clip(-10,10)
    f['pullback']=-(c/ma10-1).abs()*100 + 2*(ma20>ma60)
    f['breakout']=(c/f.ah.shift().rolling(20).max()-1)*100 + (vr.clip(0,3)-1)*2
    f['quality']=risk/10+1/(1+f['atr_pct']*100)
    f['change']=change
    f['above20']=(c>ma20).astype(float)
    f['trend_exit']=c<ma20
    f['factor']=f.close/f.ac
    f['previous_close']=f.close.shift()
    f['previous_factor']=f.factor.shift()
    f['limit']=.2 if payload['symbol'][2:].startswith(('30','68')) else (.3 if payload['symbol'].startswith('bj') else .1)
    # 只使用当时已经积累的有效交易观察，不能用未来上市状态回填。
    f['eligible']=valid & (f.index>=120) & f.amount.ge(3e7) & change.abs().lt(7) & ret5.lt(25) & f['atr_pct'].between(.003,.1)
    stock=payload['stock']
    if stock.get('is_st') or 'ST' in stock.get('name','').upper() or '退' in stock.get('name',''):
        f['eligible']=False
    f['symbol']=payload['symbol']
    f['name']=stock.get('name',payload['symbol'])
    f['lot_min']=200 if payload['symbol'][2:].startswith('68') else 100
    return f[f.date>='2025-09-04'].drop(columns=['ao','ac','ah','al','volume','turnover'])


def rank_candidates(day: pd.DataFrame, policy: ResearchPolicy) -> list[str]:
    liquid=day[day.eligible].copy()
    if liquid.empty:
        return []
    if policy.market_filter:
        if day.change.gt(0).mean()<.45 or day.above20.mean()<.45:
            return []
    base='baseline_'+policy.mode
    if policy.family=='baseline':
        liquid=liquid[liquid[base]>=70]
        score=liquid[base]
    else:
        ranks=liquid[['trend','pullback','breakout','quality',base]].rank(pct=True)
        if policy.family=='reversal':
            score=(.45*(-liquid.change).rank(pct=True)+.25*ranks['quality']+.30*ranks['trend'])*100
        elif policy.family=='lowvol':
            score=(.60*ranks['quality']+.25*ranks[base]+.15*ranks['trend'])*100
        else:
            weights={'trend': [.45,.10,.15,.15,.15], 'pullback':[.20,.40,.05,.20,.15],
                     'breakout':[.25,.05,.40,.15,.15], 'balanced':[.25,.20,.15,.20,.20]}[policy.family]
            score=(ranks*np.array(weights)).sum(axis=1)*100
        liquid=liquid[score>=70]
        score=score.loc[liquid.index]
    liquid=liquid.assign(selection_score=score)
    return liquid.sort_values(['selection_score','symbol'],ascending=[False,True]).symbol.head(3).tolist()


def backtest(days: dict[str,pd.DataFrame], policy: ResearchPolicy, start: str, end: str, *, friction: float=1.) -> dict:
    """次日开盘、T+1、现金预算；复权因子变化按等值再投资代理处理并披露。"""
    calendar=sorted(d for d in days if start<=d<=end)
    cash=1_000_000.; holdings={}; orders=[]; trades=[]; equity=[]; skipped=0; corporate=0
    for step,day in enumerate(calendar):
        frame=days[day]; quotes={r['symbol']:r for r in frame.to_dict('records')}
        def sell(symbol, price, reason):
            nonlocal cash
            pos=holdings.pop(symbol);exec_price=price*(1-.001*friction)
            proceeds=pos['shares']*exec_price
            fee=max(5.,proceeds*.0003*friction)+proceeds*.00051*friction
            cash+=proceeds-fee
            trades.append({'symbol':symbol,'signal_date':pos['signal_date'],'entry_date':pos['entry_date'],
                'exit_date':day,'entry_price':pos['entry_price'],'exit_price':exec_price,'reason':reason,
                'return_pct':(proceeds-fee-pos['cost'])/pos['cost']*100,'pnl':proceeds-fee-pos['cost'],
                'regime':pos['regime']})
        for symbol,pos in list(holdings.items()):
            q=quotes.get(symbol)
            if not q or q['amount']<=0 or not np.isfinite(q['open']):
                continue
            # 除权调整只在当日发生后使用；不反推或修改历史信号。
            factor=q['factor']
            if np.isfinite(factor) and pos['factor']>0:
                ratio=pos['factor']/factor
                if abs(ratio-1)>.0005:
                    pos['shares']*=ratio;pos['stop']/=ratio;pos['take']/=ratio;pos['peak']/=ratio;corporate+=1
            pos['factor']=factor
            reference=q['previous_close']*q['factor']/q['previous_factor']
            lower=round(reference*(1-q['limit']),2)
            if q['open']<=lower+.011:
                skipped+=1
                continue
            # 先按昨日已经产生的退出信号在开盘处理。
            if pos['exit_next'] or step-pos['entry_step']>=policy.holding:
                sell(symbol,q['open'],'trend_or_time');continue
            if policy.stop_atr and q['open']<=pos['stop']:
                sell(symbol,q['open'],'gap_stop');continue
            if policy.take_atr and q['open']>=pos['take']:
                sell(symbol,q['open'],'gap_take');continue
        # 昨日收盘产生的三个候选，不在当日用最终收益替换失败订单。
        for order in orders:
            symbol=order['symbol'];q=quotes.get(symbol)
            if symbol in holdings or len(holdings)>=10 or not q or q['amount']<=0:
                continue
            ref=q['previous_close']*q['factor']/q['previous_factor']
            upper=round(ref*(1+q['limit']),2)
            if q['open']>=upper-.011 or q['open']/ref-1>policy.max_gap or not np.isfinite(q['open']):
                skipped+=1;continue
            # 开盘预算只能使用当时已知的开盘价，不使用当日收盘净值。
            nav=cash+sum(p['shares']*(quotes[s]['open'] if s in quotes and np.isfinite(quotes[s]['open']) else p['mark']) for s,p in holdings.items())
            price=q['open']*(1+.001*friction)
            budget=min(cash,nav*.1,order['amount']*.001)
            shares=int(max(0,budget-5)/(price*(1+.00031*friction))/100)*100
            if shares<q['lot_min']:
                continue
            gross=shares*price;fee=max(5.,gross*.0003*friction)+gross*.00001*friction
            if gross+fee>cash:
                continue
            cash-=gross+fee
            atr=order['atr_pct']
            holdings[symbol]={'shares':float(shares),'cost':gross+fee,'entry_price':price,'entry_date':day,
                'entry_step':step,'signal_date':order['signal_date'],'factor':q['factor'],'atr_pct':atr,
                'peak':q['high'],'stop':price*(1-policy.stop_atr*atr),'take':price*(1+policy.take_atr*atr),
                'exit_next':False,'mark':q['close'],'regime':order['regime']}
            # 当日新买入严格T+1，不能当日止损/止盈。
        # 盘中退出的回款只能从此时起使用，绝不倒流给当天开盘订单。
        for symbol,pos in list(holdings.items()):
            q=quotes.get(symbol)
            if not q or q['amount']<=0:
                continue
            reference=q['previous_close']*q['factor']/q['previous_factor']
            lower=round(reference*(1-q['limit']),2)
            if pos['entry_step']<step and q['open']>lower+.011:
                if policy.stop_atr and q['low']<=pos['stop']:
                    sell(symbol,max(lower,pos['stop']),'stop');continue
                if policy.take_atr and q['high']>=pos['take']:
                    sell(symbol,pos['take'],'take');continue
            pos['peak']=max(pos['peak'],q['high'])
            if policy.trailing_atr:
                pos['stop']=max(pos['stop'],pos['peak']*(1-policy.trailing_atr*pos['atr_pct']))
            pos['exit_next']=policy.family!='baseline' and q['trend_exit']
        for symbol,pos in holdings.items():
            if symbol in quotes and np.isfinite(quotes[symbol]['close']):pos['mark']=quotes[symbol]['close']
        value=cash+sum(p['shares']*p['mark'] for p in holdings.values())
        equity.append({'date':day,'equity':value,'cash':cash,'holdings':len(holdings)})
        selected=rank_candidates(frame,policy)
        breadth=frame.above20.mean();regime='up' if breadth>.6 else ('down' if breadth<.4 else 'sideways')
        orders=[{'symbol':sym,'signal_date':day,'atr_pct':quotes[sym]['atr_pct'],'amount':quotes[sym]['amount'],'regime':regime} for sym in selected]
    values=np.array([1_000_000.,*[r['equity'] for r in equity]])
    returns=np.diff(values)/values[:-1];drawdown=(values/np.maximum.accumulate(values)-1)*100
    pnl=np.array([r['pnl'] for r in trades]);win=pnl[pnl>0];loss=pnl[pnl<0]
    metrics={'net_return_pct':(values[-1]/values[0]-1)*100,'max_drawdown_pct':float(drawdown.min()),
        'closed_trades':len(trades),'win_rate_pct':float((pnl>0).mean()*100) if len(pnl) else 0.,
        'profit_factor':float(win.sum()/-loss.sum()) if len(loss) else None,
        'expectancy_pct':float(np.mean([r['return_pct'] for r in trades])) if trades else 0.,
        'sharpe':float(returns.mean()/returns.std()*sqrt(252)) if len(returns) and returns.std()>0 else 0.,
        'entry_days':len({r['entry_date'] for r in trades}),'skipped_limit_or_gap':skipped,
        'open_positions':len(holdings),'corporate_action_proxy_events':corporate,
        'invested_days':sum(r['holdings']>0 for r in equity),'days':len(calendar)}
    return {'policy':asdict(policy),'metrics':metrics,'trades':trades,'equity':equity}


def improvement_gate(candidate: dict, baseline: dict) -> dict:
    c,b=candidate['metrics'],baseline['metrics']
    checks={'net_return':c['net_return_pct']-b['net_return_pct']>=5,
            'absolute_profit':c['net_return_pct']>0,
            'win_rate':c['win_rate_pct']-b['win_rate_pct']>=5,
            'drawdown':c['max_drawdown_pct']>=b['max_drawdown_pct'],
            'sample_size':c['closed_trades']>=30 and c['entry_days']>=20}
    return {'passed':all(checks.values()),'checks':checks,
            'return_improvement_pp':c['net_return_pct']-b['net_return_pct'],
            'win_rate_improvement_pp':c['win_rate_pct']-b['win_rate_pct']}
