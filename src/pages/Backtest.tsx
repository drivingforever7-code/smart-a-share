import DailyAlert from '../components/DailyAlert'
import {
  DeleteOutlined,
  ExperimentOutlined,
  FallOutlined,
  LineChartOutlined,
  RiseOutlined,
  SafetyCertificateOutlined,
  TrophyOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { type Dayjs } from 'dayjs'
import ReactECharts from 'echarts-for-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import DataState from '../components/DataState'
import Disclaimer from '../components/Disclaimer'
import { changeClass, formatNumber, formatPercent } from '../format'
import type { BacktestRequest, BacktestResult, BacktestTrade } from '../types'
import type { StrategyDefinition } from '../strategyTypes'

interface BacktestFormValues {
  code: string
  preset: string
  dates?: [Dayjs, Dayjs]
  holding_days: number
  stop_loss_pct: number
  take_profit_pct: number
  commission_pct: number
}

export default function Backtest({ defaultCode }: { defaultCode: string }) {
  const [form] = Form.useForm<BacktestFormValues>()
  const [strategies, setStrategies] = useState<StrategyDefinition[]>([])
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.strategies().then(setStrategies).catch(() => setStrategies([]))
  }, [])

  useEffect(() => {
    form.setFieldValue('code', defaultCode)
  }, [defaultCode, form])

  const run = async (values: BacktestFormValues) => {
    setLoading(true)
    setError(null)
    try {
      const payload: BacktestRequest = {
        code: values.code.trim(),
        strategy_id: values.preset,
        start_date: values.dates?.[0].format('YYYY-MM-DD'),
        end_date: values.dates?.[1].format('YYYY-MM-DD'),
        holding_days: values.holding_days,
        stop_loss_pct: values.stop_loss_pct,
        take_profit_pct: values.take_profit_pct,
        commission_pct: values.commission_pct,
      }
      setResult(await api.backtest(payload))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '策略验证失败')
    } finally {
      setLoading(false)
    }
  }

  const chartOption = useMemo(() => {
    const curve = result?.equity_curve ?? []
    return {
      tooltip: { trigger: 'axis', valueFormatter: (value: number) => `${formatNumber(value)}%` },
      legend: { data: ['策略收益', '同期股票'] },
      grid: { left: 52, right: 24, top: 42, bottom: 42 },
      xAxis: {
        type: 'category',
        data: curve.map((item) => item.date),
        axisLabel: { color: '#667085', hideOverlap: true },
      },
      yAxis: {
        type: 'value',
        axisLabel: { formatter: '{value}%' },
        splitLine: { lineStyle: { color: '#eaecf0', type: 'dashed' } },
      },
      series: [
        {
          name: '策略收益',
          type: 'line',
          data: curve.map((item) => item.strategy),
          showSymbol: false,
          smooth: true,
          lineStyle: { width: 2.5, color: '#175cd3' },
          areaStyle: { color: 'rgba(23,92,211,.08)' },
        },
        {
          name: '同期股票',
          type: 'line',
          data: curve.map((item) => item.benchmark),
          showSymbol: false,
          lineStyle: { width: 1.5, color: '#98a2b3', type: 'dashed' },
        },
      ],
    }
  }, [result])

  const columns: ColumnsType<BacktestTrade> = [
    { title: '信号日', dataIndex: 'signal_date', width: 110 },
    { title: '买入日', dataIndex: 'entry_date', width: 110 },
    { title: '卖出日', dataIndex: 'exit_date', width: 110 },
    {
      title: '买入价',
      dataIndex: 'entry_price',
      align: 'right',
      render: (value) => formatNumber(value),
    },
    {
      title: '卖出价',
      dataIndex: 'exit_price',
      align: 'right',
      render: (value) => formatNumber(value),
    },
    {
      title: '单次收益',
      dataIndex: 'return_pct',
      align: 'right',
      render: (value) => <strong className={changeClass(value)}>{formatPercent(value, true)}</strong>,
    },
    { title: '退出原因', dataIndex: 'exit_reason', render: (value) => <Tag>{value}</Tag> },
  ]



  return (
    <div className="page-stack">
      <Card className="content-card" title={<><ExperimentOutlined /> 验证参数</>}>
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            code: defaultCode,
            preset: 'risk_balanced_short',
            dates: [dayjs().subtract(3, 'year'), dayjs()],
            holding_days: 10,
            stop_loss_pct: 7,
            take_profit_pct: 15,
            commission_pct: 0.1,
          }}
          onFinish={(values) => void run(values)}
        >
          <Row gutter={16} align="bottom">
            <Col xs={24} md={8} xl={4}>
              <Form.Item
                name="code"
                label="股票代码"
                rules={[
                  { required: true, message: '请输入股票代码' },
                  { pattern: /^\d{6}$/, message: '请输入 6 位股票代码' },
                ]}
              >
                <Input placeholder="例如 600519" maxLength={6} />
              </Form.Item>
            </Col>
            <Col xs={24} md={8} xl={5}>
              <Form.Item name="preset" label="新版策略" rules={[{ required: true }]}>
                <Select
                  options={strategies.map((item) => ({
                    label: `${item.icon} ${item.name}`,
                    value: item.id,
                  }))}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={8} xl={6}>
              <Form.Item name="dates" label="验证区间">
                <DatePicker.RangePicker style={{ width: '100%' }} allowClear />
              </Form.Item>
            </Col>
            <Col xs={12} md={6} xl={2}>
              <Form.Item name="holding_days" label="持有天数">
                <InputNumber min={1} max={120} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={12} md={6} xl={2}>
              <Form.Item name="stop_loss_pct" label="止损">
                <InputNumber min={1} max={30} addonAfter="%" style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={12} md={6} xl={2}>
              <Form.Item name="take_profit_pct" label="止盈">
                <InputNumber min={1} max={100} addonAfter="%" style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={12} md={6} xl={2}>
              <Form.Item name="commission_pct" label="单边成本">
                <InputNumber min={0} max={1} step={0.01} addonAfter="%" style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={24} xl={1}>
              <Form.Item>
                <Button type="primary" htmlType="submit" loading={loading} block>
                  运行
                </Button>
              </Form.Item>
            </Col>
          </Row>
        </Form>
        <DailyAlert noticeKey="backtest-1"
          type="info"
          showIcon
          message="信号在收盘后确认，最早使用下一交易日开盘价买入，避免偷看未来数据。"
        />
      </Card>

      <DataState loading={loading} error={error} onRetry={() => form.submit()}>
        {result && (
          <>
            <Row gutter={[16, 16]}>
              <Col xs={12} lg={4}>
                <Card className="metric-card">
                  <Statistic
                    title="累计收益"
                    value={result.total_return}
                    precision={2}
                    suffix="%"
                    prefix={<RiseOutlined />}
                    valueStyle={{ color: result.total_return >= 0 ? '#d92d20' : '#039855' }}
                  />
                </Card>
              </Col>
              <Col xs={12} lg={4}>
                <Card className="metric-card">
                  <Statistic title="年化收益" value={result.annual_return} precision={2} suffix="%" prefix={<LineChartOutlined />} />
                </Card>
              </Col>
              <Col xs={12} lg={4}>
                <Card className="metric-card">
                  <Statistic title="最大回撤" value={result.max_drawdown} precision={2} suffix="%" prefix={<FallOutlined />} valueStyle={{ color: '#039855' }} />
                </Card>
              </Col>
              <Col xs={12} lg={4}>
                <Card className="metric-card">
                  <Statistic title="夏普比率" value={result.sharpe_ratio} precision={2} prefix={<SafetyCertificateOutlined />} />
                </Card>
              </Col>
              <Col xs={12} lg={4}>
                <Card className="metric-card">
                  <Statistic title="胜率" value={result.win_rate} precision={2} suffix="%" prefix={<TrophyOutlined />} />
                </Card>
              </Col>
              <Col xs={12} lg={4}>
                <Card className="metric-card">
                  <Statistic title="盈亏比" value={result.profit_factor} precision={2} />
                  <Typography.Text type="secondary">
                    单笔期望 {formatPercent(result.expectancy, true)}
                  </Typography.Text>
                </Card>
              </Col>
              <Col xs={12} lg={4}>
                <Card className="metric-card">
                  <Statistic title="信号次数" value={result.trade_count} suffix="次" />
                  <Typography.Text type="secondary">
                    同期股票 {formatPercent(result.benchmark_return, true)}
                  </Typography.Text>
                </Card>
              </Col>
            </Row>

            <Card
              className="chart-card"
              title={
                <Space>
                  <span>{result.name}（{result.code}）收益曲线</span>
                  <Tag>{result.start_date} 至 {result.end_date}</Tag>
                </Space>
              }
              extra={
                <Popconfirm
                  title="删除这只股票的回测结果？"
                  okText="删除"
                  cancelText="取消"
                  onConfirm={() => setResult(null)}
                >
                  <Button danger type="text" icon={<DeleteOutlined />}>删除结果</Button>
                </Popconfirm>
              }
            >
              <ReactECharts option={chartOption} style={{ height: 420 }} />
            </Card>

            <Card className="content-card" title="每次信号明细">
              <Table
                rowKey={(item) => `${item.entry_date}-${item.exit_date}`}
                dataSource={result.trades}
                columns={columns}
                pagination={{ pageSize: 20 }}
                scroll={{ x: 800 }}
              />
            </Card>
          </>
        )}
      </DataState>
      <Disclaimer />
    </div>
  )
}
