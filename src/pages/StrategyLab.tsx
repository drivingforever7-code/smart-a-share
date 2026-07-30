import {
  ExperimentOutlined,
  SafetyCertificateOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  DatePicker,
  Form,
  Input,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { type Dayjs } from 'dayjs'
import { useEffect, useState } from 'react'
import { api } from '../api'
import DataState from '../components/DataState'
import { resolveStockQuery } from '../components/StockSearchInput'
import Disclaimer from '../components/Disclaimer'
import type { LabRow, StrategyLabResult } from '../labTypes'
import type { StrategyDefinition } from '../strategyTypes'

interface LabForm {
  codes: string
  strategy_ids: string[]
  dates: [Dayjs, Dayjs]
  split_date: Dayjs
}

const assessmentColor: Record<string, string> = {
  样本外较稳健: 'green',
  样本外有正期望: 'blue',
  需要继续观察: 'orange',
  样本外未通过: 'red',
  样本不足: 'default',
}

export default function StrategyLab() {
  const [form] = Form.useForm<LabForm>()
  const [strategies, setStrategies] = useState<StrategyDefinition[]>([])
  const [result, setResult] = useState<StrategyLabResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const basketText = Form.useWatch('codes', form) || ''
  const basketItems = basketText
    .split(/[\s,，;；]+/)
    .map((item) => item.trim())
    .filter(Boolean)

  useEffect(() => {
    api.strategies().then(setStrategies).catch(() => setStrategies([]))
  }, [])

  const run = async (values: LabForm) => {
    const queries = values.codes
      .split(/[\s,，;；]+/)
      .map((item) => item.trim())
      .filter(Boolean)
    setLoading(true)
    setError(null)
    try {
      const resolved = await Promise.all(
        queries.map(async (query) => {
          if (/^\d{6}$/.test(query)) return query
          const match = await resolveStockQuery(query)
          if (!match) throw new Error(`没有找到股票：${query}`)
          return match.code
        }),
      )
      const codes = [...new Set(resolved)]
      setResult(
        await api.strategyLab({
          codes,
          strategy_ids: values.strategy_ids,
          start_date: values.dates[0].format('YYYY-MM-DD'),
          split_date: values.split_date.format('YYYY-MM-DD'),
          end_date: values.dates[1].format('YYYY-MM-DD'),
        }),
      )
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '策略实验失败')
    } finally {
      setLoading(false)
    }
  }

  const columns: ColumnsType<LabRow> = [
    {
      title: '策略',
      dataIndex: 'strategy_name',
      fixed: 'left',
      width: 160,
      render: (value, row) => (
        <div>
          <strong>{value}</strong>
          <div><Tag>{row.mode === 'short' ? '短线' : '波段'}</Tag></div>
        </div>
      ),
    },
    {
      title: '样本外结论',
      dataIndex: 'assessment',
      width: 145,
      render: (value) => <Tag color={assessmentColor[value]}>{value}</Tag>,
    },
    {
      title: '样本外（真正优先看这里）',
      children: [
        { title: '交易数', dataIndex: ['out_of_sample', 'trade_count'], width: 85 },
        {
          title: '胜率',
          dataIndex: ['out_of_sample', 'win_rate'],
          width: 85,
          render: (value) => `${value}%`,
        },
        {
          title: '盈亏比',
          dataIndex: ['out_of_sample', 'profit_factor'],
          width: 85,
          render: (value) => <strong>{value}</strong>,
        },
        {
          title: '单笔期望',
          dataIndex: ['out_of_sample', 'expectancy'],
          width: 95,
          render: (value) => `${value}%`,
        },
        {
          title: '收益中位数',
          dataIndex: ['out_of_sample', 'median_total_return'],
          width: 105,
          render: (value) => `${value}%`,
        },
        {
          title: '回撤中位数',
          dataIndex: ['out_of_sample', 'median_max_drawdown'],
          width: 105,
          render: (value) => `${value}%`,
        },
      ],
    },
    {
      title: '样本内（只用于对照）',
      children: [
        {
          title: '胜率',
          dataIndex: ['in_sample', 'win_rate'],
          width: 80,
          render: (value) => `${value}%`,
        },
        { title: '盈亏比', dataIndex: ['in_sample', 'profit_factor'], width: 80 },
        {
          title: '单笔期望',
          dataIndex: ['in_sample', 'expectancy'],
          width: 90,
          render: (value) => `${value}%`,
        },
      ],
    },
  ]

  return (
    <div className="page-stack">
      <Alert
        type="info"
        showIcon
        icon={<SafetyCertificateOutlined />}
        message="不再用单只股票和单一胜率判断策略"
        description="实验室把较早时期作为样本内，把较新时期作为样本外。策略排名优先看样本外盈亏比、单笔期望、交易数量和回撤；高胜率但亏一次很大的策略不会被评为优秀。"
      />

      <Card title={<Space><ExperimentOutlined />实验设置</Space>}>
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            codes: '600519, 000858, 600036, 000333',
            strategy_ids: [
              'volatility_adjusted_momentum',
              'trend_mean_reversion',
              'multifactor_resonance',
              'risk_balanced_short',
            ],
            dates: [dayjs('2018-01-01'), dayjs()],
            split_date: dayjs('2023-01-01'),
          }}
          onFinish={(values) => void run(values)}
        >
          <Row gutter={16} align="bottom">
            <Col xs={24} lg={8}>
              <Form.Item
                name="codes"
                label="测试股票篮子（最多12只）"
                rules={[{ required: true, message: '请填写至少一只股票' }]}
              >
                <Input.TextArea rows={2} placeholder="支持代码、名称或拼音，用逗号分隔，例如 600519, 贵州茅台, gzmt" />
              </Form.Item>
              <Space size={[4, 4]} wrap>
                {basketItems.map((item, index) => (
                  <Tag
                    key={`${item}-${index}`}
                    closable
                    onClose={(event) => {
                      event.preventDefault()
                      form.setFieldValue(
                        'codes',
                        basketItems.filter((_, itemIndex) => itemIndex !== index).join(', '),
                      )
                    }}
                  >
                    {item}
                  </Tag>
                ))}
              </Space>
            </Col>
            <Col xs={24} lg={8}>
              <Form.Item
                name="strategy_ids"
                label="对比策略"
                rules={[{ required: true, message: '请选择至少一个策略' }]}
              >
                <Select
                  mode="multiple"
                  maxTagCount="responsive"
                  options={strategies.map((item) => ({
                    value: item.id,
                    label: `${item.icon} ${item.name}`,
                  }))}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={10} lg={4}>
              <Form.Item name="dates" label="完整验证区间" rules={[{ required: true }]}>
                <DatePicker.RangePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={16} md={8} lg={3}>
              <Form.Item name="split_date" label="样本分界日" rules={[{ required: true }]}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={8} md={6} lg={1}>
              <Form.Item>
                <Button type="primary" htmlType="submit" loading={loading} block>
                  运行
                </Button>
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Card>

      <DataState loading={loading} error={error} onRetry={() => form.submit()}>
        {result && (
          <>
            <Card
              title="实验结果"
              extra={<Tag color="blue">样本外：{result.method.out_of_sample}</Tag>}
            >
              <Table
                rowKey="strategy_id"
                dataSource={result.rows}
                columns={columns}
                pagination={false}
                scroll={{ x: 1300 }}
              />
            </Card>
            <Alert
              type="warning"
              showIcon
              icon={<WarningOutlined />}
              message={result.method.ranking}
              description={result.method.limitations.join('；')}
            />
            {result.errors.length > 0 && (
              <Collapse
                items={[
                  {
                    key: 'errors',
                    label: `${result.errors.length} 个组合未能完成`,
                    children: (
                      <Typography.Paragraph>
                        {result.errors.map((item) => (
                          <div key={`${item.strategy_id}-${item.sample_type}-${item.code}`}>
                            {item.code} · {item.strategy_id} · {item.sample_type}：{item.error}
                          </div>
                        ))}
                      </Typography.Paragraph>
                    ),
                  },
                ]}
              />
            )}
          </>
        )}
      </DataState>
      <Disclaimer />
    </div>
  )
}
