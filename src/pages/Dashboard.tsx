import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  ClockCircleOutlined,
  FallOutlined,
  RiseOutlined,
  SyncOutlined,
} from '@ant-design/icons'
import { Button, Card, Col, Row, Segmented, Space, Statistic, Tag, Typography } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import DataState, { DataNotice } from '../components/DataState'
import Disclaimer from '../components/Disclaimer'
import OpportunityTable from '../components/OpportunityTable'
import { formatPercent, formatTime } from '../format'
import { getSettings } from '../storage'
import type { MarketOverview, Opportunity, Preset, ScoreMode } from '../types'

export default function Dashboard({ onOpenStock }: { onOpenStock: (code: string) => void }) {
  const [mode, setMode] = useState<ScoreMode>('short')
  const [overview, setOverview] = useState<MarketOverview | null>(null)
  const [items, setItems] = useState<Opportunity[]>([])
  const [presets, setPresets] = useState<Preset[]>([])
  const [activePreset, setActivePreset] = useState<string>()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    setError(null)
    try {
      const [market, opportunities, presetList] = await Promise.all([
        api.overview(),
        api.opportunities(mode, 20, activePreset),
        api.presets(),
      ])
      setOverview(market)
      setItems(opportunities)
      setPresets(presetList)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '无法连接本地数据服务')
    } finally {
      setLoading(false)
    }
  }, [activePreset, mode])

  useEffect(() => {
    void load()
    const refreshMs = Math.max(5, getSettings().refreshSeconds) * 1000
    const timer = window.setInterval(() => void load(true), refreshMs)
    return () => window.clearInterval(timer)
  }, [load])

  const modePresets = presets.filter((item) => item.mode === mode || item.mode === 'both')

  return (
    <div className="page-stack">
      <div className="page-toolbar">
        <Segmented
          value={mode}
          onChange={(value) => {
            setMode(value as ScoreMode)
            setActivePreset(undefined)
          }}
          options={[
            { label: '短线机会', value: 'short' },
            { label: '波段机会', value: 'swing' },
          ]}
        />
        <Space>
          {overview && (
            <Typography.Text type="secondary">
              <ClockCircleOutlined /> 获取于 {formatTime(overview.meta.fetched_at)}
            </Typography.Text>
          )}
          <Button icon={<SyncOutlined />} onClick={() => void load()} loading={loading}>
            立即刷新
          </Button>
        </Space>
      </div>

      {overview && (
        <Row gutter={[16, 16]}>
          <Col xs={12} lg={6}>
            <Card className="metric-card">
              <Statistic title="市场股票" value={overview.quote_count} suffix="只" />
              <Typography.Text type="secondary">本次实时快照</Typography.Text>
            </Card>
          </Col>
          <Col xs={12} lg={6}>
            <Card className="metric-card metric-up">
              <Statistic
                title="上涨家数"
                value={overview.rising}
                prefix={<ArrowUpOutlined />}
                suffix={<small> / {overview.quote_count}</small>}
              />
              <Typography.Text type="secondary">涨停附近 {overview.limit_up} 只</Typography.Text>
            </Card>
          </Col>
          <Col xs={12} lg={6}>
            <Card className="metric-card metric-down">
              <Statistic
                title="下跌家数"
                value={overview.falling}
                prefix={<ArrowDownOutlined />}
                suffix={<small> / {overview.quote_count}</small>}
              />
              <Typography.Text type="secondary">跌停附近 {overview.limit_down} 只</Typography.Text>
            </Card>
          </Col>
          <Col xs={12} lg={6}>
            <Card className="metric-card">
              <Statistic
                title="全市场平均涨幅"
                value={overview.average_change_pct}
                precision={2}
                suffix="%"
                prefix={overview.average_change_pct >= 0 ? <RiseOutlined /> : <FallOutlined />}
                valueStyle={{ color: overview.average_change_pct >= 0 ? '#d92d20' : '#039855' }}
              />
              <Typography.Text type="secondary">
                中位数 {formatPercent(overview.median_change_pct, true)}
              </Typography.Text>
            </Card>
          </Col>
        </Row>
      )}

      <Card className="preset-strip" title="快速策略">
        <Space size={[8, 8]} wrap>
          <Button
            type={activePreset ? 'default' : 'primary'}
            onClick={() => setActivePreset(undefined)}
          >
            综合机会
          </Button>
          {modePresets.map((preset) => (
            <Button
              key={preset.id}
              type={activePreset === preset.id ? 'primary' : 'default'}
              onClick={() => setActivePreset(preset.id)}
              title={preset.description}
            >
              <span className="preset-icon">{preset.icon}</span>
              {preset.name}
            </Button>
          ))}
        </Space>
      </Card>

      {overview && (
        <DataNotice
          cached={overview.meta.is_cached}
          text={
            overview.meta.quote_time
              ? `行情时间 ${formatTime(overview.meta.quote_time)} · 来源 ${overview.meta.source}`
              : `数据源未提供逐条行情时间，本次获取于 ${formatTime(overview.meta.fetched_at)} · 来源 ${overview.meta.source}`
          }
        />
      )}

      <Card
        className="content-card"
        title={
          <Space>
            <span>{mode === 'short' ? '短线机会榜' : '波段机会榜'}</span>
            <Tag color="blue">前 {items.length} 只</Tag>
          </Space>
        }
        extra={<Typography.Text type="secondary">每 10 秒自动更新价格</Typography.Text>}
      >
        <DataState
          loading={loading}
          error={error}
          empty={!loading && !error && items.length === 0}
          onRetry={() => void load()}
        >
          <OpportunityTable
            items={items}
            onOpenStock={onOpenStock}
            scoreLabel={mode === 'short' ? '短线分' : '波段分'}
          />
        </DataState>
      </Card>
      <Disclaimer />
    </div>
  )
}
