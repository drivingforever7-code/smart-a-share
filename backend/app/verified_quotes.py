"""为跟踪股票补充腾讯原始行情中的实际时间，不用抓取时间代替。"""
from __future__ import annotations

import re
import time
from datetime import datetime
from threading import Lock

import requests

from .research_quality import verified_quote_date

_lock=Lock()
_cache: dict[str,tuple[float,dict]]={}


def parse_tencent_quotes(text: str) -> dict[str,dict]:
    result={}
    for code,body in re.findall(r'v_(?:sh|sz|bj)(\d{6})="([^"]*)"',text):
        fields=body.split('~')
        try:
            stamp=datetime.strptime(fields[30],'%Y%m%d%H%M%S').strftime('%Y-%m-%d %H:%M:%S')
            price=float(fields[3])
            if price<=0 or verified_quote_date({'quote_time':stamp}) is None:continue
            result[code]={'code':code,'price':price,'quote_time':stamp,'source':'腾讯原始盘口时间'}
        except (IndexError,ValueError):
            continue
    return result


def fetch_verified_quotes(codes: list[str]) -> dict[str,dict]:
    codes=sorted({c for c in codes if re.fullmatch(r'\d{6}',c)})
    now=time.monotonic();result={}
    with _lock:
        missing=[c for c in codes if c not in _cache or now-_cache[c][0]>60]
        for i in range(0,len(missing),80):
            batch=missing[i:i+80]
            symbols=[('sh' if c.startswith('6') else 'bj' if c.startswith(('4','8','9')) else 'sz')+c for c in batch]
            try:
                response=requests.get('https://qt.gtimg.cn/q='+','.join(symbols),timeout=8)
                response.raise_for_status();response.encoding='gbk'
                parsed=parse_tencent_quotes(response.text)
                for c in batch:_cache[c]=(now,parsed.get(c,{}))
            except requests.RequestException:
                for c in batch:_cache[c]=(now,{})
        for code in codes:
            if code in _cache and _cache[code][1]:result[code]=dict(_cache[code][1])
    return result
