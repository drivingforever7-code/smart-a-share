import {
  CalendarOutlined,
  ClockCircleOutlined,
  DeleteOutlined,
  EyeOutlined,
  FallOutlined,
  RiseOutlined,
  SyncOutlined,
  TrophyOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Col,
  Popconfirm,
  Row,
  Progress,
  Segmented,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import type {
  AutoBacktestItem,
  AutoBacktestResponse,
  AutoBacktestSummary,
  RankingStrategyStatus,
} from '../autoBacktestTypes'
import DataState, { DataNotice } from '../components/DataState'
import Disclaimer from '../components/Disclaimer'
import { RecommendationTag, ScoreBadge } from '../components/ScoreBadge'
import { changeClass, formatNumber, formatPercent, formatTime } from '../format'
import { getSettings } from '../storage'
import type { ScoreMode } from '../types'
import { useDismissedRows } from '../useDismissedRows'

function strategyVersionLabel(value: string) {
  return value.replace('short-', '短线 ').replace('swing-', '波段 ')
}

function ActionTag({ value }: { value: string }) {
  const color = value === '加仓'
    ? 'gold'
    : value === '继续持有'
      ? 'success'
      : value === '减仓'
        ? 'warning'
        : value === '清仓'
          ? 'error'
          : 'default'
  return <Tag color={color}>{value}</Tag>
}

const modeText: Record<ScoreMode, string> = {
  short: '短线前三',
  swing: '波段前三',
}

function EvolutionCard({
  mode,
  status,
}: {
  mode: ScoreMode
  status: RankingStrategyStatus
}) {
  const latest = status.recent_runs[0]
  const modeName = mode === 'short' ? '短线' : '波段'
  return (
    <Card className={`content-card strategy-evolution strategy-evolution--${mode}`}>
      <Space direction="vertical" size={10} style={{ width: '100%' }}>
        <Space wrap>
          <Typography.Text strong>{modeName}策略进化</Typography.Text>
          <Tag color={mode === 'short' ? 'cyan' : 'purple'}>{strategyVersionLabel(status.active_version)}</Tag>
          <Tag color={status.ready_for_optimization ? 'processing' : 'default'}>
            {status.ready_for_optimization ? '已达到训练门槛' : '积累中'}
          </Tag>
        </Space>
        <div>
          <Space style={{ width: '100%', justifyContent: 'space-between' }}>
            <Typography.Text type="secondary">成熟样本</Typography.Text>
            <Typography.Text>{status.matured_samples}/{status.required_samples}</Typography.Text>
          </Space>
          <Progress percent={status.sample_progress_pct} size="small" showInfo={false} />
        </div>
        <div>
          <Space style={{ width: '100%', justifyContent: 'space-between' }}>
            <Typography.Text type="secondary">交易日</Typography.Text>
            <Typography.Text>{status.trading_days}/{status.required_days}</Typography.Text>
          </Space>
          <Progress
            percent={status.day_progress_pct}
            size="small"
            showInfo={false}
            strokeColor={mode === 'short' ? '#35d0ba' : '#8b7cff'}
          />
        </div>
        <Typography.Text type="secondary">
          每日留存前 20 · 后续 {status.horizon_observations} 个有效观察日成熟 · 待成熟 {status.pending_samples}
        </Typography.Text>
        {latest && (
          <Alert closable
            type={latest.status === 'activated' ? 'success' : latest.status === 'rejected' ? 'warning' : 'info'}
            showIcon
            message={
              latest.status === 'activated'
                ? `已升级到 ${latest.candidate_version}`
                : latest.status === 'rejected'
                  ? `候选 ${latest.candidate_version || ''} 未通过`
                  : '尚在积累训练样本'
            }
            description={latest.reason}
          />
        )}
        <Space size={[6, 6]} wrap>
          {status.versions.slice(0, 5).map((version) => (
            <Tag key={version.version} color={version.is_active ? 'success' : version.status === 'rejected' ? 'error' : 'default'}>
              {strategyVersionLabel(version.version)} · {version.is_active ? '使用中' : version.status === 'rejected' ? '未通过' : '历史'}
            </Tag>
          ))}
        </Space>
      </Space>
    </Card>
  )
}

function SummaryCard({
  mode,
  summary,
}: {
  mode: ScoreMode
  summary: AutoBacktestSummary
}) {
  return (
    <Card className={`metric-card auto-summary auto-summary--${mode}`}>
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Space>
          <TrophyOutlined />
          <Typography.Text strong>{modeText[mode]}</Typography.Text>
          <Tag color={mode === 'short' ? 'cyan' : 'purple'}>
            {summary.priced_count}/{summary.count} 只有现价
          </Tag>
        </Space>
        <Statistic
          title="平均累计涨跌"
          value={summary.average_return_pct ?? 0}
          precision={2}
          suffix="%"
          prefix={(summary.average_return_pct ?? 0) >= 0 ? <RiseOutlined /> : <FallOutlined />}
          valueStyle={{ color: (summary.average_return_pct ?? 0) >= 0 ? '#f04438' : '#12b76a' }}
        />
        <Typography.Text type="secondary">
          上涨 {summary.positive_count} 只
          {summary.best && ` · 最佳 ${summary.best.name} ${formatPercent(summary.best.return_pct, true)}`}
        </Typography.Text>
      </Space>
    </Card>
  )
}

export default function AutoBacktest({
  onOpenStock,
}: {
  onOpenStock: (code: string) => void
}) {
  const [days, setDays] = useState(5)
  const [data, setData] = useState<AutoBacktestResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { dismissed, dismiss } = useDismissedRows('auto-backtest')

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    setError(null)
    try {
      setData(await api.autoBacktest(days))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '自动回测数据暂时不可用')
    } finally {
      setLoading(false)
    }
  }, [days])

  useEffect(() => {
    void load()
    const refreshMs = Math.max(10, getSettings().refreshSeconds) * 1000
    const timer = window.setInterval(() => void load(true), refreshMs)
    return () => window.clearInterval(timer)
  }, [load])

  const columns = useMemo<ColumnsType<AutoBacktestItem>>(() => [
    {
      title: '发现日期',
      dataIndex: 'discovery_date',
      width: 112,
      fixed: 'left',
      render: (value: string) => (
        <Space size={5}>
          <CalendarOutlined />
          <strong>{value.slice(5)}</strong>
        </Space>
      ),
    },
    {
      title: '排名',
      dataIndex: 'rank',
      width: 72,
      align: 'center',
      render: (value: number) => <Tag color={value === 1 ? 'gold' : 'default'}>第 {value} 名</Tag>,
    },
    {
      title: '股票',
      key: 'stock',
      width: 150,
      render: (_, item) => (
        <button className="stock-link" onClick={() => onOpenStock(item.code)}>
          <strong>{item.name}</strong>
          <span>{item.code} · {item.industry || '行业未知'}</span>
        </button>
      ),
    },
    {
      title: '发现价',
      dataIndex: 'discovery_price',
      width: 92,
      align: 'right',
      render: (value: number) => formatNumber(value),
    },
    {
      title: '当前价',
      dataIndex: 'current_price',
      width: 92,
      align: 'right',
      render: (value: number | null, item) => (
        <span className={changeClass(item.return_pct)}>{formatNumber(value)}</span>
      ),
    },
    {
      title: '累计涨跌',
      dataIndex: 'return_pct',
      width: 108,
      align: 'right',
      sorter: (a, b) => (a.return_pct ?? -999) - (b.return_pct ?? -999),
      render: (value: number | null) => (
        <strong className={changeClass(value)}>{formatPercent(value, true)}</strong>
      ),
    },
    {
      title: '当前操作',
      key: 'dailyAction',
      width: 148,
      fixed: 'right',
      render: (_, item) => (
        <Space direction="vertical" size={2}>
          <ActionTag value={item.action_advice} />
          <Typography.Text type="secondary">
            仓位 {item.action_position_pct}% · 现评分 {item.current_score?.toFixed(1) ?? '--'}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      fixed: 'right',
      render: (_, item) => (
        <Space>
          <Button type="text" icon={<EyeOutlined />} onClick={() => onOpenStock(item.code)}>
            详情
          </Button>
          <Popconfirm
            title="隐藏这条发现记录？"
            description="不会删除历史审计和训练样本，其他记录保持原顺序。"
            okText="删除"
            cancelText="取消"
            onConfirm={() => dismiss(item.id)}
          >
            <Button danger type="text" icon={<DeleteOutlined />} aria-label="删除股票" />
          </Popconfirm>
        </Space>
      ),
    },
  ], [dismiss, onOpenStock])

  return (
    <div className="page-stack auto-backtest-page">
      <div className="page-toolbar">
        <Space>
          <Typography.Text strong>观察窗口</Typography.Text>
          <Segmented
            value={days}
            options={[
              { label: '近 3 日', value: 3 },
              { label: '近 5 日', value: 5 },
              { label: '近 10 日', value: 10 },
            ]}
            onChange={(value) => setDays(Number(value))}
          />
        </Space>
        <Space>
          {data && (
            <Typography.Text type="secondary">
              <ClockCircleOutlined /> 更新于 {formatTime(data.meta.fetched_at)}
            </Typography.Text>
          )}
          <Button icon={<SyncOutlined />} loading={loading} onClick={() => void load()}>
            刷新表现
          </Button>
        </Space>
      </div>

      <Alert closable
        type="info"
        showIcon
        message="每日自动记录两个榜单的前三名"
        description={`${data?.history_note || '只记录真实发现快照，不使用今天的结果伪造过去排名。'} 这里跟踪榜单发现价到现价，不假设真实成交，也不扣交易成本；完整成交验证请使用策略实验室。`}
      />
      {data && (
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12}><SummaryCard mode="short" summary={data.summaries.short} /></Col>
          <Col xs={24} lg={12}><SummaryCard mode="swing" summary={data.summaries.swing} /></Col>
        </Row>
      )}

      {data && (
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12}><EvolutionCard mode="short" status={data.strategy_optimization.short} /></Col>
          <Col xs={24} lg={12}><EvolutionCard mode="swing" status={data.strategy_optimization.swing} /></Col>
        </Row>
      )}
      {data && (
        <Alert closable
          type="success"
          showIcon
          message={`短线 ${strategyVersionLabel(data.strategy_optimization.short.active_version)} · 波段 ${strategyVersionLabel(data.strategy_optimization.swing.active_version)}`}
          description={`每日持续登记与验证；达到样本外升级门槛才自动升级。连续清仓 3 个交易日后主列表隐藏，本次已归档 ${data.training_cycle.archived_after_clear ?? 0} 条。`}
        />
      )}

      {data && (
        <DataNotice
          cached={data.meta.is_cached}
          text={`当前价格时间 ${formatTime(data.meta.quote_time || data.meta.fetched_at)} · 来源 ${data.meta.source} · 已保存 ${data.available_dates.length} 个真实发现日`}
        />
      )}

      <DataState
        loading={loading}
        error={error}
        empty={!loading && !error && (!data || data.items.length === 0)}
        emptyText="还没有真实发现记录。首次成功读取榜单后会自动保存当天短线与波段前三。"
        onRetry={() => void load()}
      >
        {(['short', 'swing'] as ScoreMode[]).map((mode) => {
          const items = data?.items.filter(
            (item) => item.mode === mode && !dismissed.has(String(item.id)),
          ) ?? []
          return (
            <Card
              key={mode}
              className="content-card auto-result-card"
              title={
                <Space>
                  <span>{modeText[mode]}</span>
                  <Tag color={mode === 'short' ? 'cyan' : 'purple'}>
                    {items.length} 条真实记录
                  </Tag>
                </Space>
              }
            >
              <Table
                rowKey="id"
                columns={columns}
                dataSource={items}
                pagination={false}
                scroll={{ x: 900 }}
                size="small"
                expandable={{
                  expandedRowRender: (item) => (
                    <Row gutter={[24, 12]} className="auto-detail-row">
                      <Col xs={24} lg={10}>
                        <Typography.Text strong>发现依据</Typography.Text>
                        <Space size={[6, 6]} wrap>
                          {item.reasons.map((reason) => (
                            <Tag key={reason} color="cyan">{reason}</Tag>
                          ))}
                        </Space>
                      </Col>
                      <Col xs={24} lg={8}>
                        <Typography.Text strong>当时风险</Typography.Text>
                        <Space size={[6, 6]} wrap>
                          {item.risks.length
                            ? item.risks.map((risk) => <Tag key={risk} color="warning">{risk}</Tag>)
                            : <Typography.Text type="secondary">未记录突出风险</Typography.Text>}
                        </Space>
                      </Col>
                      <Col xs={24} lg={6}>
                        <Typography.Text strong>今日操作依据</Typography.Text>
                        <Typography.Paragraph>
                          <ActionTag value={item.action_advice} /> 建议仓位 {item.action_position_pct}%
                        </Typography.Paragraph>
                        {item.action_reasons.map((reason) => (
                          <Typography.Paragraph key={reason} type="secondary">· {reason}</Typography.Paragraph>
                        ))}
                        <Typography.Text type="danger">{item.action_invalidation}</Typography.Text>
                      </Col>
                      <Col xs={24}>
                        <Typography.Text strong>逐日操作记录</Typography.Text>
                        <Space size={[8, 8]} wrap style={{ marginTop: 8 }}>
                          {item.advice_history.length
                            ? item.advice_history.map((history) => (
                              <Card key={history.advice_date} size="small" className="daily-advice-card">
                                <Space direction="vertical" size={3}>
                                  <Typography.Text strong>{history.advice_date}</Typography.Text>
                                  <ActionTag value={history.action} />
                                  <Typography.Text type="secondary">
                                    仓位 {history.position_pct}% · 涨跌 {formatPercent(history.return_pct, true)}
                                  </Typography.Text>
                                  <Typography.Text type="secondary">
                                    评分 {history.current_score?.toFixed(1) ?? '--'}
                                  </Typography.Text>
                                </Space>
                              </Card>
                            ))
                            : <Typography.Text type="secondary">下一交易日起开始记录每日操作建议</Typography.Text>}
                        </Space>
                      </Col>
                    </Row>
                  ),
                }}
              />
            </Card>
          )
        })}
      </DataState>
      <Disclaimer />
    </div>
  )
}
