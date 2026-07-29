import ReactECharts from 'echarts-for-react'
import { useMemo } from 'react'
import type { Bar, BacktestMarker } from '../types'
import type { IntradayPoint } from '../strategyTypes'

const maColors: Record<number, string> = {
  5: '#7f56d9',
  10: '#175cd3',
  20: '#f79009',
  60: '#12b76a',
}

function movingAverage(bars: Bar[], days: number) {
  return bars.map((_, index) => {
    if (index < days - 1) return null
    const slice = bars.slice(index - days + 1, index + 1)
    return Number((slice.reduce((sum, item) => sum + item.close, 0) / days).toFixed(3))
  })
}

export default function StockPriceChart({
  bars,
  intraday,
  timeframe,
  visibleMa,
  markers = [],
  height = 500,
}: {
  bars: Bar[]
  intraday: IntradayPoint[]
  timeframe: string
  visibleMa: number[]
  markers?: BacktestMarker[]
  height?: number
}) {
  const option = useMemo(() => {
    if (timeframe === 'intraday') {
      const times = intraday.map((item) => item.time.slice(11, 16))
      const intradayVolumes = intraday.map((item, index) => ({
        value: item.volume,
        itemStyle: {
          color: item.price >= (intraday[index - 1]?.price ?? item.price) ? '#d92d20' : '#039855',
        },
      }))
      return {
        animation: false,
        legend: { top: 0, data: ['分时价格', '均价'], textStyle: { color: '#9fb8cc' } },
        tooltip: { trigger: 'axis', axisPointer: { type: 'cross' }, backgroundColor: 'rgba(7, 16, 30, .94)', borderColor: '#24506f', textStyle: { color: '#e8f3ff' } },
        axisPointer: { link: [{ xAxisIndex: 'all' }] },
        grid: [
          { left: 58, right: 26, top: 42, height: '60%' },
          { left: 58, right: 26, top: '73%', height: '14%' },
        ],
        xAxis: [
          { type: 'category', data: times, boundaryGap: false, axisLabel: { color: '#7894aa', hideOverlap: true }, axisLine: { lineStyle: { color: '#24445e' } } },
          {
            type: 'category',
            gridIndex: 1,
            data: times,
            boundaryGap: true,
            axisLabel: { show: false },
            axisTick: { show: false },
          },
        ],
        yAxis: [
          {
            scale: true,
            axisLabel: { color: '#7894aa', formatter: (value: number) => value.toFixed(2) },
            splitLine: { lineStyle: { color: 'rgba(91, 145, 184, .2)', type: 'dashed' } },
          },
          { scale: true, gridIndex: 1, splitLine: { show: false }, axisLabel: { show: false } },
        ],
        series: [
          {
            name: '分时价格',
            type: 'line',
            showSymbol: false,
            smooth: false,
            lineStyle: { width: 2, color: '#175cd3' },
            areaStyle: { color: 'rgba(23, 92, 211, .08)' },
            data: intraday.map((item) => item.price),
          },
          {
            name: '均价',
            type: 'line',
            showSymbol: false,
            lineStyle: { width: 1.5, color: '#f79009' },
            data: intraday.map((item) => item.average_price),
          },
          {
            name: '成交量',
            type: 'bar',
            xAxisIndex: 1,
            yAxisIndex: 1,
            itemStyle: { color: '#98a2b3' },
            data: intradayVolumes,
          },
        ],
      }
    }

    const dates = bars.map((item) => item.time.slice(0, 10))
    const volumes = bars.map((item) => ({
      value: item.volume,
      itemStyle: { color: item.close >= item.open ? '#d92d20' : '#039855' },
    }))
    const markData = markers.map((item) => ({
      name: item.label,
      coord: [item.date, item.price],
      value: item.type === 'buy' ? '买' : '卖',
      symbol: item.type === 'buy' ? 'pin' : 'pin',
      symbolSize: 42,
      itemStyle: { color: item.type === 'buy' ? '#d92d20' : '#039855' },
      label: { color: '#fff', fontWeight: 700 },
      tooltip: { formatter: `${item.label}<br/>${item.date} · ${item.price}<br/>${item.detail}` },
    }))
    const maSeries = visibleMa.map((days) => ({
      name: `MA${days}`,
      type: 'line',
      showSymbol: false,
      smooth: true,
      connectNulls: false,
      lineStyle: { width: 1.3, color: maColors[days] },
      data: movingAverage(bars, days),
    }))
    return {
      animation: false,
      legend: { top: 0, data: ['K线', ...visibleMa.map((days) => `MA${days}`)], textStyle: { color: '#9fb8cc' } },
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross' }, backgroundColor: 'rgba(7, 16, 30, .94)', borderColor: '#24506f', textStyle: { color: '#e8f3ff' } },
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      grid: [
        { left: 58, right: 26, top: 42, height: '58%' },
        { left: 58, right: 26, top: '72%', height: '15%' },
      ],
      xAxis: [
        { type: 'category', data: dates, boundaryGap: true, axisLabel: { color: '#7894aa', hideOverlap: true }, axisLine: { lineStyle: { color: '#24445e' } } },
        {
          type: 'category',
          gridIndex: 1,
          data: dates,
          boundaryGap: true,
          axisLabel: { show: false },
          axisTick: { show: false },
        },
      ],
      yAxis: [
        { scale: true, axisLabel: { color: '#7894aa' }, splitLine: { lineStyle: { color: 'rgba(91, 145, 184, .2)', type: 'dashed' } } },
        { scale: true, gridIndex: 1, splitLine: { show: false }, axisLabel: { show: false } },
      ],
      dataZoom: [
        {
          type: 'inside',
          xAxisIndex: [0, 1],
          start: Math.max(0, 100 - (100 / Math.max(1, bars.length)) * 100),
          end: 100,
        },
        { type: 'slider', xAxisIndex: [0, 1], bottom: 4, height: 18, start: 65, end: 100 },
      ],
      series: [
        {
          name: 'K线',
          type: 'candlestick',
          data: bars.map((item) => [item.open, item.close, item.low, item.high]),
          itemStyle: {
            color: '#d92d20',
            color0: '#039855',
            borderColor: '#d92d20',
            borderColor0: '#039855',
          },
          markPoint: { data: markData },
        },
        ...maSeries,
        {
          name: '成交量',
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: volumes,
        },
      ],
    }
  }, [bars, intraday, timeframe, visibleMa, markers])

  return <ReactECharts option={option} style={{ height }} notMerge />
}
