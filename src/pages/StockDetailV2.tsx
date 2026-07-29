import {
  ClearOutlined,
  ExperimentOutlined,
  RobotOutlined,
  SearchOutlined,
  StarFilled,
  StarOutlined,
  SyncOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Descriptions,
  Divider,
  Progress,
  Row,
  Segmented,
  Select,
  Space,
  Statistic,
  Tag,
  Typography,
} from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import StockPriceChart from '../components/StockPriceChart'
import LoadingExperience from '../components/LoadingExperience'
import StockSearchInput from '../components/StockSearchInput'
import DataState, { DataNotice } from '../components/DataState'
import Disclaimer from '../components/Disclaimer'
import { RecommendationTag, ScoreBadge } from '../components/ScoreBadge'
import {
  changeClass,
  formatAmount,
  formatMarketCap,
  formatNumber,
  formatPercent,
  formatTime,
} from '../format'
import { getWatchlist, toggleWatchlist } from '../storage'
import type { IntradayResponse, StrategyDefinition } from '../strategyTypes'
import type {
  BacktestResult,
  BarResponse,
  ScoreMode,
  StockAnalysis,
} from '../types'

const timeframeOptions = [
  { label: '分时', value: 'intraday' },
  { label: '日K', value: 'day' },
  { label: '周K', value: 'week' },
  { label: '月K', value: 'month' },
]

const toDateText = (date: Date) => {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export default function StockDetailV2({
  code,
  onCodeChange,
}: {
  code: string
  onCodeChange: (code: string) => void
}) {
  const [mode, setMode] = useState<ScoreMode>('short')
  const [timeframe, setTimeframe] = useState('day')
  const [visibleMa, setVisibleMa] = useState<number[]>([5, 10, 20, 60])
  const [analysis, setAnalysis] = useState<StockAnalysis | null>(null)
  const [barData, setBarData] = useState<BarResponse | null>(null)
  const [intraday, setIntraday] = useState<IntradayResponse | null>(null)
  const [strategies, setStrategies] = useState<StrategyDefinition[]>([])
  const [strategyId, setStrategyId] = useState('risk_balanced_short')
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [chartLoading, setChartLoading] = useState(false)
  const [backtesting, setBacktesting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searchText, setSearchText] = useState('')
  const [watched, setWatched] = useState(getWatchlist().includes(code))

  const loadChart = useCallback(async () => {
    setChartLoading(true)
    try {
      if (timeframe === 'intraday') {
        setIntraday(await api.intraday(code))
      } else {
        setBarData(await api.bars(code, timeframe, timeframe === 'day' ? 800 : 300))
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '走势图获取失败')
    } finally {
      setChartLoading(false)
    }
  }, [code, timeframe])

  const loadBase = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [nextAnalysis, nextStrategies] = await Promise.all([
        api.stockAnalysis(code, mode),
        api.strategies(),
      ])
      setAnalysis(nextAnalysis)
      setStrategies(nextStrategies)
      if (!nextStrategies.some((item) => item.id === strategyId && item.mode === mode)) {
        setStrategyId(
          mode === 'short'
            ? nextStrategies.find((item) => item.id === 'risk_balanced_short')?.id ?? nextStrategies[0]?.id
            : nextStrategies.find((item) => item.id === 'risk_balanced_swing')?.id ?? nextStrategies[0]?.id,
        )
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '股票数据获取失败')
    } finally {
      setLoading(false)
    }
  }, [code, mode, strategyId])

  useEffect(() => {
    setWatched(getWatchlist().includes(code))
    setBacktestResult(null)
    void loadBase()
  }, [code, mode]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    void loadChart()
  }, [loadChart])

  useEffect(() => {
    if (timeframe !== 'intraday') return
    let active = true
    let refreshing = false
    const refreshTimer = window.setInterval(() => {
      if (refreshing) return
      refreshing = true
      api
        .intraday(code)
        .then((next) => {
          if (active) setIntraday(next)
        })
        .catch(() => undefined)
        .finally(() => {
          refreshing = false
        })
    }, 10_000)
    return () => {
      active = false
      window.clearInterval(refreshTimer)
    }
  }, [code, timeframe])



  const strategyOptions = useMemo(
    () =>
      strategies
        .filter((item) => item.mode === mode)
        .map((item) => ({
          value: item.id,
          label: `${item.icon} ${item.name}${item.category === 'composite' ? '（综合）' : ''}`,
        })),
    [mode, strategies],
  )

  const runBacktest = async () => {
    setBacktesting(true)
    setError(null)
    try {
      const end = new Date()
      const start = new Date()
      start.setFullYear(end.getFullYear() - 3)
      const [result, dailyBars] = await Promise.all([
        api.backtest({
          code,
          strategy_id: strategyId,
          start_date: toDateText(start),
          end_date: toDateText(end),
        }),
        timeframe === 'day' ? Promise.resolve(barData) : api.bars(code, 'day', 800),
      ])
      setBacktestResult(result)
      if (dailyBars) setBarData(dailyBars)
      setTimeframe('day')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '回测失败')
    } finally {
      setBacktesting(false)
    }
  }

  const chartEmpty =
    timeframe === 'intraday'
      ? !(intraday?.points.length)
      : !(barData?.bars.length)

  return (
    <div className="page-stack">
      <div className="page-toolbar detail-toolbar">
        <StockSearchInput
          value={searchText}
          onChange={setSearchText}
          onSelect={(value) => {
            onCodeChange(value)
            setSearchText('')
          }}
          className="stock-autocomplete"
        />
        <Space>
          <Segmented
            value={mode}
            onChange={(value) => {
              const nextMode = value as ScoreMode
              setMode(nextMode)
              setStrategyId(nextMode === 'short' ? 'risk_balanced_short' : 'risk_balanced_swing')
              setBacktestResult(null)
            }}
            options={[
              { label: '短线分析', value: 'short' },
              { label: '波段分析', value: 'swing' },
            ]}
          />
          <Button
            icon={<SyncOutlined />}
            onClick={() => {
              void loadBase()
              void loadChart()
            }}
            loading={loading || chartLoading}
          >
            刷新
          </Button>
        </Space>
      </div>

      <DataState loading={loading} error={error} onRetry={() => void loadBase()}>
        {analysis && (
          <>
            <Card className="stock-hero">
              <Row gutter={[24, 20]} align="middle">
                <Col xs={24} lg={8}>
                  <Space align="start" size={14}>
                    <div>
                      <Space>
                        <Typography.Title level={2}>{analysis.name}</Typography.Title>
                        <Tag>{analysis.code}</Tag>
                        <Tag color="blue">{analysis.board}</Tag>
                      </Space>
                      <div className="stock-price-row">
                        <span className={changeClass(analysis.change_pct)}>
                          {formatNumber(analysis.price)}
                        </span>
                        <strong className={changeClass(analysis.change_pct)}>
                          {formatPercent(analysis.change_pct, true)}
                        </strong>
                      </div>
                    </div>
                  </Space>
                </Col>
                <Col xs={12} sm={6} lg={3}>
                  <Statistic title="成交额" value={formatAmount(analysis.amount)} />
                </Col>
                <Col xs={12} sm={6} lg={3}>
                  <Statistic title="换手率" value={formatPercent(analysis.turnover_rate)} />
                </Col>
                <Col xs={12} sm={6} lg={3}>
                  <Statistic title="量比" value={formatNumber(analysis.volume_ratio)} />
                </Col>
                <Col xs={12} sm={6} lg={3}>
                  <Statistic title="总市值" value={formatMarketCap(analysis.total_market_cap)} />
                </Col>
                <Col xs={24} lg={4} className="hero-actions">
                  <Button
                    icon={watched ? <StarFilled /> : <StarOutlined />}
                    type={watched ? 'primary' : 'default'}
                    onClick={() => {
                      const next = toggleWatchlist(code)
                      setWatched(next.includes(code))
                    }}
                  >
                    {watched ? '已在自选' : '加入自选'}
                  </Button>
                  <Button
                    icon={<RobotOutlined />}
                    style={{ marginLeft: 8 }}
                    onClick={() => {
                      window.location.hash = `#/ai?code=${code}`
                    }}
                  >
                    AI联合分析
                  </Button>
                </Col>
              </Row>
            </Card>

            <DataNotice
              cached={analysis.meta.is_cached}
              text={
                analysis.meta.quote_time
                  ? `行情时间 ${formatTime(analysis.meta.quote_time)} · 来源 ${analysis.meta.source}`
                  : `本次获取于 ${formatTime(analysis.meta.fetched_at)} · 来源 ${analysis.meta.source}`
              }
            />

            <Card className="chart-card">
              <div className="chart-controls">
                <Segmented
                  value={timeframe}
                  onChange={(value) => setTimeframe(String(value))}
                  options={timeframeOptions}
                />
                {timeframe === 'intraday' && intraday && (
                  <Typography.Text type="secondary">
                    分时日期 {intraday.date ?? '未知'} · {intraday.meta.is_cached ? '缓存数据' : '最新获取'}
                    {' · '}来源 {intraday.meta.source}
                  </Typography.Text>
                )}
                {timeframe !== 'intraday' && (
                  <Checkbox.Group
                    value={visibleMa}
                    options={[5, 10, 20, 60].map((days) => ({
                      label: `MA${days}`,
                      value: days,
                    }))}
                    onChange={(values) => setVisibleMa(values as number[])}
                  />
                )}
              </div>
              {chartLoading ? (
                <LoadingExperience
                  compact
                  label="正在同步走势图"
                  detail="正在校验分时价格、均价线与成交量"
                />
              ) : chartEmpty ? (
                <Alert
                  type="warning"
                  showIcon
                  message={timeframe === 'intraday' ? '当前没有可用分时数据' : '当前周期没有K线数据'}
                  description="休市时会显示最近一个交易日；数据源暂不可用时可稍后刷新。"
                />
              ) : (
                <StockPriceChart
                  bars={barData?.bars ?? []}
                  intraday={intraday?.points ?? []}
                  timeframe={timeframe}
                  visibleMa={visibleMa}
                  markers={timeframe === 'day' ? backtestResult?.markers ?? [] : []}
                />
              )}
            </Card>

            <Card
              className="strategy-backtest-card"
              title={
                <Space>
                  <ExperimentOutlined />
                  个股策略回测
                </Space>
              }
            >
              <Row gutter={[16, 16]} align="middle">
                <Col xs={24} lg={10}>
                  <Typography.Text type="secondary">选择策略</Typography.Text>
                  <Select
                    showSearch
                    value={strategyId}
                    options={strategyOptions}
                    style={{ width: '100%', marginTop: 6 }}
                    optionFilterProp="label"
                    onChange={(value) => {
                      setStrategyId(value)
                      setBacktestResult(null)
                    }}
                  />
                </Col>
                <Col xs={24} lg={8}>
                  <Alert
                    type="info"
                    showIcon
                    message="默认验证最近 3 年"
                    description="信号当天收盘后确认，下一交易日开盘买入；买卖点会标在上面的日K图。"
                  />
                </Col>
                <Col xs={24} lg={6}>
                  <Space wrap>
                    <Button
                      type="primary"
                      size="large"
                      icon={<ExperimentOutlined />}
                      loading={backtesting}
                      onClick={() => void runBacktest()}
                    >
                      开始回测
                    </Button>
                    {backtestResult && (
                      <Button
                        icon={<ClearOutlined />}
                        onClick={() => setBacktestResult(null)}
                      >
                        清除买卖点
                      </Button>
                    )}
                  </Space>
                </Col>
              </Row>

              {backtestResult && (
                <>
                  <Divider orientation="left">
                    {backtestResult.strategy_name ?? backtestResult.preset} · 回测结果
                  </Divider>
                  <Row gutter={[12, 12]}>
                    <Col xs={12} md={4}><Statistic title="总收益" value={backtestResult.total_return} suffix="%" valueStyle={{ color: backtestResult.total_return >= 0 ? '#d92d20' : '#039855' }} /></Col>
                    <Col xs={12} md={4}><Statistic title="年化收益" value={backtestResult.annual_return} suffix="%" /></Col>
                    <Col xs={12} md={4}><Statistic title="最大回撤" value={backtestResult.max_drawdown} suffix="%" /></Col>
                    <Col xs={12} md={4}><Statistic title="胜率" value={backtestResult.win_rate} suffix="%" /></Col>
                    <Col xs={12} md={4}><Statistic title="夏普比率" value={backtestResult.sharpe_ratio} /></Col>
                    <Col xs={12} md={4}><Statistic title="交易次数" value={backtestResult.trade_count} /></Col>
                  </Row>
                  <Alert
                    style={{ marginTop: 16 }}
                    type="warning"
                    showIcon
                    message="回测不是收益承诺"
                    description={`${backtestResult.start_date} 至 ${backtestResult.end_date}。${backtestResult.meta.financial_note ?? ''}`}
                  />
                </>
              )}
            </Card>

            <Row gutter={[16, 16]}>
              <Col xs={24} xl={9}>
                <Card className="advice-card">
                  <div className="advice-header">
                    <ScoreBadge score={analysis.score} />
                    <div>
                      <Typography.Text type="secondary">
                        {mode === 'short' ? '短线综合判断' : '波段综合判断'}
                      </Typography.Text>
                      <div className="recommendation-large">
                        <RecommendationTag value={analysis.recommendation} />
                      </div>
                      <Typography.Text type="secondary">
                        置信度 {Math.round(analysis.confidence)}%
                      </Typography.Text>
                    </div>
                  </div>
                  <Divider orientation="left">为什么</Divider>
                  <ul className="reason-list positive">
                    {analysis.reasons.map((reason) => <li key={reason}>{reason}</li>)}
                  </ul>
                  <Divider orientation="left">需要注意</Divider>
                  <ul className="reason-list risk">
                    {analysis.risks.map((risk) => <li key={risk}>{risk}</li>)}
                  </ul>
                </Card>
              </Col>
              <Col xs={24} xl={15}>
                <Card className="content-card" title="评分拆解">
                  <Row gutter={[24, 20]}>
                    {analysis.dimensions.map((dimension) => (
                      <Col xs={24} md={12} key={dimension.key}>
                        <div className="dimension-row">
                          <div className="dimension-title">
                            <strong>{dimension.name}</strong>
                            <span>{formatNumber(dimension.score, 1)} / {dimension.max_score}</span>
                          </div>
                          <Progress
                            percent={(dimension.score / dimension.max_score) * 100}
                            showInfo={false}
                            strokeColor="#175cd3"
                          />
                          <Typography.Text type="secondary">{dimension.summary}</Typography.Text>
                        </div>
                      </Col>
                    ))}
                  </Row>
                  <Divider />
                  <Descriptions column={{ xs: 2, md: 4 }} size="small">
                    <Descriptions.Item label="PE">{formatNumber(analysis.pe)}</Descriptions.Item>
                    <Descriptions.Item label="PB">{formatNumber(analysis.pb)}</Descriptions.Item>
                    <Descriptions.Item label="关注区间">
                      {formatNumber(analysis.entry_low)} – {formatNumber(analysis.entry_high)}
                    </Descriptions.Item>
                    <Descriptions.Item label="止损参考">
                      {formatNumber(analysis.stop_loss)}
                    </Descriptions.Item>
                  </Descriptions>
                </Card>
              </Col>
            </Row>
          </>
        )}
      </DataState>
      <Disclaimer />
    </div>
  )
}
