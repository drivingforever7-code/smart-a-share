import {
  AimOutlined,
  ClockCircleOutlined,
  DeleteOutlined,
  ExperimentOutlined,
  FireOutlined,
  SafetyCertificateOutlined,
  SyncOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Col,
  Popconfirm,
  Progress,
  Row,
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
import DataState from '../components/DataState'
import Disclaimer from '../components/Disclaimer'
import { changeClass, formatNumber, formatPercent, formatTime } from '../format'
import type { LimitBreakItem, LimitBreakResponse } from '../limitBreakTypes'
import { useDismissedRows } from '../useDismissedRows'

const stageText = {
  midday: '午盘观测',
  afternoon: '尾盘前观测',
  close: '盘后补录',
}

function OutcomeTag({ value }: { value: LimitBreakItem['outcome'] }) {
  if (value === 'resealed') return <Tag color="success">已回封</Tag>
  if (value === 'failed') return <Tag color="error">未回封</Tag>
  return <Tag color="processing">待收盘确认</Tag>
}

export default function LimitBreakResearch({
  onOpenStock,
}: {
  onOpenStock: (code: string) => void
}) {
  const [days, setDays] = useState(5)
  const [data, setData] = useState<LimitBreakResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { dismissed, dismiss } = useDismissedRows('limit-breaks')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await api.limitBreaks(days))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '炸板研究数据暂时不可用')
    } finally {
      setLoading(false)
    }
  }, [days])

  useEffect(() => {
    void load()
  }, [load])

  const columns = useMemo<ColumnsType<LimitBreakItem>>(() => [
    {
      title: '日期 / 排名',
      key: 'date',
      width: 112,
      fixed: 'left',
      render: (_, item) => (
        <Space direction="vertical" size={2}>
          <strong>{item.trade_date.slice(5)}</strong>
          <Tag color={item.probability_rank <= 3 ? 'gold' : 'default'}>
            概率第 {item.probability_rank}
          </Tag>
        </Space>
      ),
    },
    {
      title: '股票',
      key: 'stock',
      width: 150,
      fixed: 'left',
      render: (_, item) => (
        <button className="stock-link" onClick={() => onOpenStock(item.code)}>
          <strong>{item.name}</strong>
          <span>{item.code} · {item.industry || '行业未知'}</span>
        </button>
      ),
    },
    {
      title: '结果',
      dataIndex: 'outcome',
      width: 108,
      render: (value) => <OutcomeTag value={value} />,
    },
    {
      title: '回封概率',
      dataIndex: 'predicted_probability',
      width: 138,
      sorter: (a, b) => a.predicted_probability - b.predicted_probability,
      render: (value: number, item) => (
        <Space direction="vertical" size={1} style={{ width: 105 }}>
          <Progress
            percent={value}
            size="small"
            strokeColor={value >= 70 ? '#f5b942' : value >= 52 ? '#35d0ba' : '#ff5f6d'}
          />
          <Typography.Text type="secondary">
            {stageText[item.prediction_stage]}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '分析建议',
      key: 'advice',
      width: 142,
      render: (_, item) => (
        <Space direction="vertical" size={2}>
          <Tag color={item.recommendation === '建议小仓位试买' ? 'gold' : item.recommendation === '建议回避' ? 'error' : 'cyan'}>
            {item.recommendation}
          </Tag>
          <Typography.Text type="secondary">建议仓位 {item.position_pct}%</Typography.Text>
        </Space>
      ),
    },
    {
      title: '首次封板 / 炸板',
      key: 'break',
      width: 132,
      render: (_, item) => (
        <Space direction="vertical" size={2}>
          <span>{item.first_limit_time || '时间未知'}</span>
          <Typography.Text type="secondary">{item.break_count} 次 · {item.limit_statistics}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '现价 / 涨停价',
      key: 'price',
      width: 126,
      align: 'right',
      render: (_, item) => (
        <Space direction="vertical" size={2}>
          <strong className={changeClass(item.change_pct)}>{formatNumber(item.price)}</strong>
          <Typography.Text type="secondary">{formatNumber(item.limit_price)}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '距涨停',
      dataIndex: 'distance_to_limit_pct',
      width: 92,
      align: 'right',
      render: (value: number) => `${value.toFixed(2)}%`,
    },
    {
      title: '涨跌 / 振幅',
      key: 'movement',
      width: 108,
      align: 'right',
      render: (_, item) => (
        <Space direction="vertical" size={2}>
          <span className={changeClass(item.change_pct)}>{formatPercent(item.change_pct, true)}</span>
          <Typography.Text type="secondary">{formatPercent(item.amplitude)}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '换手 / 成交额',
      key: 'liquidity',
      width: 122,
      align: 'right',
      render: (_, item) => (
        <Space direction="vertical" size={2}>
          <span>{formatPercent(item.turnover_rate)}</span>
          <Typography.Text type="secondary">{formatNumber(item.amount / 1e8)} 亿</Typography.Text>
        </Space>
      ),
    },
    {
      title: '市场封板率',
      dataIndex: 'market_seal_rate',
      width: 110,
      align: 'right',
      render: (value: number) => formatPercent(value),
    },
    {
      title: '操作',
      key: 'actions',
      width: 72,
      fixed: 'right',
      render: (_, item) => (
        <Popconfirm
          title="从炸板列表删除这只股票？"
          description="只在当前浏览器隐藏，历史研究样本仍保留。"
          okText="删除"
          cancelText="取消"
          onConfirm={() => dismiss(item.id)}
        >
          <Button danger type="text" icon={<DeleteOutlined />} aria-label="删除股票" />
        </Popconfirm>
      ),
    },
  ], [dismiss, onOpenStock])

  const latestReview = data?.daily_reviews[0]

  return (
    <div className="page-stack limit-break-page">
      <div className="page-toolbar">
        <Space>
          <Typography.Text strong>研究窗口</Typography.Text>
          <Segmented
            value={days}
            options={[
              { label: '今日', value: 1 },
              { label: '近 3 日', value: 3 },
              { label: '近 5 日', value: 5 },
              { label: '近 10 日', value: 10 },
            ]}
            onChange={(value) => setDays(Number(value))}
          />
        </Space>
        <Button icon={<SyncOutlined />} loading={loading} onClick={() => void load()}>
          刷新并留存
        </Button>
      </div>

      <Alert
        type="warning"
        showIcon
        message="炸板研究是高风险事件研究，不是回封或收益保证"
        description="概率只使用观测时可见字段；午盘和尾盘前预测用于收盘复盘，盘后补录样本不参与准确率。即使回封，也可能无法按显示价格成交或次日出现大幅低开。"
      />

      {data?.warning && <Alert type="error" showIcon message={data.warning} />}

      {data && (
        <Row gutter={[16, 16]}>
          <Col xs={12} lg={6}>
            <Card className="metric-card">
              <Statistic title="有效盘中样本" value={data.model_stats.sample_count} prefix={<ExperimentOutlined />} />
              <Typography.Text type="secondary">{data.model_stats.trading_days} 个交易日</Typography.Text>
            </Card>
          </Col>
          <Col xs={12} lg={6}>
            <Card className="metric-card">
              <Statistic
                title="历史实际回封率"
                value={data.model_stats.reseal_rate ?? 0}
                precision={2}
                suffix="%"
                prefix={<FireOutlined />}
              />
              <Typography.Text type="secondary">
                回封 {data.model_stats.resealed_count} · 未回封 {data.model_stats.failed_count}
              </Typography.Text>
            </Card>
          </Col>
          <Col xs={12} lg={6}>
            <Card className="metric-card">
              <Statistic
                title="方向准确率"
                value={data.model_stats.accuracy ?? 0}
                precision={2}
                suffix="%"
                prefix={<AimOutlined />}
              />
              <Typography.Text type="secondary">以 50% 概率为方向分界</Typography.Text>
            </Card>
          </Col>
          <Col xs={12} lg={6}>
            <Card className="metric-card">
              <Statistic
                title="Brier 分数"
                value={data.model_stats.brier_score ?? 0}
                precision={4}
                prefix={<SafetyCertificateOutlined />}
              />
              <Typography.Text type="secondary">越低代表概率校准越好</Typography.Text>
            </Card>
          </Col>
        </Row>
      )}

      {latestReview && (
        <Card className="content-card limit-review-strip">
          <Space size={[18, 8]} wrap>
            <Typography.Text strong>{latestReview.trade_date} 每日复盘</Typography.Text>
            <Tag>共 {latestReview.total} 只</Tag>
            <Tag color="success">回封 {latestReview.resealed}</Tag>
            <Tag color="error">未回封 {latestReview.failed}</Tag>
            <Tag color="cyan">可评估预测 {latestReview.evaluated}</Tag>
            <Typography.Text type="secondary">
              回封率 {formatPercent(latestReview.reseal_rate)}
            </Typography.Text>
          </Space>
        </Card>
      )}

      <DataState
        loading={loading}
        error={error}
        empty={!loading && !error && (!data || data.items.length === 0)}
        emptyText="当前还没有真实炸板记录。交易日成功抓取后会开始累计，不会伪造启用前历史。"
        onRetry={() => void load()}
      >
        <Card
          className="content-card"
          title={
            <Space>
              <FireOutlined />
              <span>每日炸板与回封概率排名</span>
              <Tag color="cyan">{data?.items.length ?? 0} 条</Tag>
            </Space>
          }
          extra={data?.capture && (
            <Typography.Text type="secondary">
              <ClockCircleOutlined /> {formatTime(data.capture.captured_at)} · {data.capture.source}
            </Typography.Text>
          )}
        >
          <Table
            rowKey={(item) => `${item.trade_date}-${item.code}`}
            columns={columns}
            dataSource={(data?.items ?? []).filter(
              (item) => !dismissed.has(String(item.id)),
            )}
            pagination={false}
            size="middle"
            scroll={{ x: 1390 }}
            expandable={{
              expandedRowRender: (item) => (
                <Row gutter={[20, 14]} className="limit-break-detail">
                  <Col xs={24} lg={8}>
                    <Typography.Text strong>回封依据</Typography.Text>
                    <Space size={[6, 6]} wrap>
                      {item.reasons.map((reason) => <Tag color="cyan" key={reason}>{reason}</Tag>)}
                    </Space>
                  </Col>
                  <Col xs={24} lg={8}>
                    <Typography.Text strong>主要风险</Typography.Text>
                    <Space size={[6, 6]} wrap>
                      {item.risks.map((risk) => <Tag color="warning" key={risk}>{risk}</Tag>)}
                    </Space>
                    <Typography.Paragraph type="secondary">{item.invalidation}</Typography.Paragraph>
                  </Col>
                  <Col xs={24} lg={8}>
                    <Typography.Text strong>收盘复盘</Typography.Text>
                    <Typography.Paragraph type="secondary">
                      {item.review?.summary || '收盘后才会生成回封结果和原因复盘。'}
                    </Typography.Paragraph>
                    {item.review?.strongest_factors.map((factor) => <Tag key={factor}>{factor}</Tag>)}
                    <Typography.Paragraph type="secondary">
                      模型 {item.model_version} · {item.eligible_for_evaluation ? '计入评估' : '盘后补录，不计入评估'}
                    </Typography.Paragraph>
                  </Col>
                </Row>
              ),
            }}
          />
        </Card>
      </DataState>

      {data && (
        <Alert
          type="info"
          showIcon
          message={`当前模型 ${data.model_stats.active_model}`}
          description={`${data.model_stats.upgrade_gate} ${data.methodology.prediction_rule}`}
        />
      )}
      <Disclaimer />
    </div>
  )
}
