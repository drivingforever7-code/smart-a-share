import {
  DeleteOutlined,
  DownloadOutlined,
  FilterOutlined,
  ReloadOutlined,
  SaveOutlined,
} from '@ant-design/icons'
import {
  Button,
  Card,
  Col,
  Collapse,
  Divider,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Segmented,
  Select,
  Slider,
  Space,
  Tag,
  Typography,
} from 'antd'
import { useEffect, useState } from 'react'
import { api } from '../api'
import DataState from '../components/DataState'
import Disclaimer from '../components/Disclaimer'
import OpportunityTable from '../components/OpportunityTable'
import { deleteScheme, getSavedSchemes, saveScheme, type SavedScheme } from '../storage'
import type { Preset, ScoreMode, ScreenerFilters, ScreenerResponse } from '../types'

type FormValues = Omit<
  ScreenerFilters,
  'page' | 'page_size' | 'sort_by' | 'sort_order'
> & {
  change_range?: [number, number]
  pe_range?: [number, number]
  pb_range?: [number, number]
  market_cap_range?: [number, number]
}

const initialValues: FormValues = {
  mode: 'short',
  preset: null,
  boards: [],
  industries: [],
  min_score: 70,
  change_range: [-5, 9.8],
  min_turnover_rate: null,
  min_volume_ratio: null,
  pe_range: undefined,
  pb_range: undefined,
  market_cap_range: undefined,
  include_st: false,
  include_new: false,
}

export default function Screener({ onOpenStock }: { onOpenStock: (code: string) => void }) {
  const [form] = Form.useForm<FormValues>()
  const mode = Form.useWatch('mode', form) ?? 'short'
  const [presets, setPresets] = useState<Preset[]>([])
  const [result, setResult] = useState<ScreenerResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedSchemes, setSavedSchemes] = useState<SavedScheme[]>(getSavedSchemes)
  const [saveOpen, setSaveOpen] = useState(false)
  const [schemeName, setSchemeName] = useState('')

  useEffect(() => {
    api.presets().then(setPresets).catch(() => setPresets([]))
  }, [])

  const normalize = (values: FormValues, page = 1): ScreenerFilters => ({
    mode: values.mode,
    preset: values.preset ?? null,
    boards: values.boards ?? [],
    industries: values.industries ?? [],
    min_score: values.min_score ?? null,
    min_change_pct: values.change_range?.[0] ?? null,
    max_change_pct: values.change_range?.[1] ?? null,
    min_turnover_rate: values.min_turnover_rate ?? null,
    min_volume_ratio: values.min_volume_ratio ?? null,
    min_pe: values.pe_range?.[0] ?? null,
    max_pe: values.pe_range?.[1] ?? null,
    min_pb: values.pb_range?.[0] ?? null,
    max_pb: values.pb_range?.[1] ?? null,
    min_market_cap: values.market_cap_range?.[0]
      ? values.market_cap_range[0] * 1e8
      : null,
    max_market_cap: values.market_cap_range?.[1]
      ? values.market_cap_range[1] * 1e8
      : null,
    include_st: values.include_st ?? false,
    include_new: values.include_new ?? false,
    page,
    page_size: 30,
    sort_by: 'score',
    sort_order: 'desc',
  })

  const runScreen = async (page = 1) => {
    setLoading(true)
    setError(null)
    try {
      const values = await form.validateFields()
      setResult(await api.screen(normalize(values, page)))
    } catch (reason) {
      if (reason instanceof Error) setError(reason.message)
    } finally {
      setLoading(false)
    }
  }

  const reset = () => {
    form.resetFields()
    setResult(null)
    setError(null)
  }

  const exportCsv = () => {
    if (!result?.items.length) return
    const headers = ['代码', '名称', '板块', '最新价', '涨跌幅', '综合评分', '系统建议', '入选依据', '风险']
    const rows = result.items.map((item) => [
      item.code,
      item.name,
      item.board,
      item.price ?? '',
      item.change_pct ?? '',
      item.score,
      item.recommendation,
      item.reasons.join('；'),
      item.risks.join('；'),
    ])
    const escape = (value: unknown) => `"${String(value).replaceAll('"', '""')}"`
    const csv = '\uFEFF' + [headers, ...rows].map((row) => row.map(escape).join(',')).join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `智选A股_筛选结果_${new Date().toISOString().slice(0, 10)}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }

  const confirmSave = () => {
    const name = schemeName.trim()
    if (!name) return
    setSavedSchemes(saveScheme(name, form.getFieldsValue(true) as Record<string, unknown>))
    setSchemeName('')
    setSaveOpen(false)
  }

  const loadScheme = (scheme: SavedScheme) => {
    form.setFieldsValue(scheme.filters as FormValues)
    setResult(null)
  }

  const availablePresets = presets.filter((item) => item.mode === mode || item.mode === 'both')

  return (
    <div className="page-stack">
      <Row gutter={[16, 16]} align="top">
        <Col xs={24} xl={7}>
          <Card className="filter-card" title={<><FilterOutlined /> 筛选条件</>}>
            <Form
              form={form}
              layout="vertical"
              initialValues={initialValues}
              onFinish={() => void runScreen()}
            >
              <Form.Item name="mode" label="交易模式">
                <Segmented
                  block
                  options={[
                    { label: '短线', value: 'short' },
                    { label: '波段', value: 'swing' },
                  ]}
                />
              </Form.Item>

              <Form.Item name="preset" label="系统方案">
                <Select
                  allowClear
                  placeholder="不使用预设，按下方条件筛选"
                  options={availablePresets.map((item) => ({
                    label: `${item.icon} ${item.name}`,
                    value: item.id,
                    title: item.description,
                  }))}
                />
              </Form.Item>

              <Form.Item name="boards" label="交易板块">
                <Select
                  mode="multiple"
                  placeholder="全部板块"
                  options={['主板', '创业板', '科创板', '北交所'].map((value) => ({
                    label: value,
                    value,
                  }))}
                />
              </Form.Item>

              <Collapse
                ghost
                defaultActiveKey={['score', 'trading']}
                items={[
                  {
                    key: 'score',
                    label: '评分与涨跌',
                    children: (
                      <>
                        <Form.Item name="min_score" label="最低综合评分">
                          <Slider min={0} max={100} marks={{ 60: '60', 70: '70', 80: '80' }} />
                        </Form.Item>
                        <Form.Item name="change_range" label="当日涨跌幅范围">
                          <Slider range min={-20} max={20} step={0.1} tooltip={{ formatter: (value) => `${value}%` }} />
                        </Form.Item>
                      </>
                    ),
                  },
                  {
                    key: 'trading',
                    label: '交易活跃度',
                    children: (
                      <Row gutter={12}>
                        <Col span={12}>
                          <Form.Item name="min_turnover_rate" label="最低换手率">
                            <InputNumber min={0} max={100} addonAfter="%" style={{ width: '100%' }} />
                          </Form.Item>
                        </Col>
                        <Col span={12}>
                          <Form.Item name="min_volume_ratio" label="最低量比">
                            <InputNumber min={0} max={20} step={0.1} style={{ width: '100%' }} />
                          </Form.Item>
                        </Col>
                      </Row>
                    ),
                  },
                  {
                    key: 'valuation',
                    label: '估值与市值',
                    children: (
                      <>
                        <Form.Item name="pe_range" label="PE 范围">
                          <Slider range min={0} max={200} />
                        </Form.Item>
                        <Form.Item name="pb_range" label="PB 范围">
                          <Slider range min={0} max={30} step={0.1} />
                        </Form.Item>
                        <Form.Item name="market_cap_range" label="总市值范围（亿元）">
                          <Slider range min={0} max={5000} step={10} />
                        </Form.Item>
                      </>
                    ),
                  },
                  {
                    key: 'risk',
                    label: '风险范围',
                    children: (
                      <>
                        <Form.Item name="include_st" label="ST 股票">
                          <Segmented
                            block
                            options={[
                              { label: '默认排除', value: false },
                              { label: '允许包含', value: true },
                            ]}
                          />
                        </Form.Item>
                        <Form.Item name="include_new" label="上市不足 120 天">
                          <Segmented
                            block
                            options={[
                              { label: '默认排除', value: false },
                              { label: '允许包含', value: true },
                            ]}
                          />
                        </Form.Item>
                      </>
                    ),
                  },
                ]}
              />

              <Space.Compact block>
                <Button type="primary" htmlType="submit" icon={<FilterOutlined />} loading={loading}>
                  开始选股
                </Button>
                <Button icon={<ReloadOutlined />} onClick={reset}>重置</Button>
                <Button icon={<SaveOutlined />} onClick={() => setSaveOpen(true)}>保存</Button>
              </Space.Compact>
            </Form>

            {savedSchemes.length > 0 && (
              <>
                <Divider />
                <Typography.Text strong>我的方案</Typography.Text>
                <div className="saved-schemes">
                  {savedSchemes.map((scheme) => (
                    <Tag
                      key={scheme.id}
                      closable
                      closeIcon={<DeleteOutlined />}
                      onClose={(event) => {
                        event.preventDefault()
                        setSavedSchemes(deleteScheme(scheme.id))
                      }}
                      onClick={() => loadScheme(scheme)}
                    >
                      {scheme.name}
                    </Tag>
                  ))}
                </div>
              </>
            )}
          </Card>
        </Col>

        <Col xs={24} xl={17}>
          <Card
            className="content-card"
            title={
              <Space>
                <span>筛选结果</span>
                {result && <Tag color="blue">{result.total} 只</Tag>}
              </Space>
            }
            extra={
              <Button
                icon={<DownloadOutlined />}
                disabled={!result?.items.length}
                onClick={exportCsv}
              >
                导出当前页
              </Button>
            }
          >
            <DataState
              loading={loading}
              error={error}
              empty={!!result && result.items.length === 0}
              emptyText="没有股票同时满足这些条件，可以适当放宽评分或涨跌幅范围"
              onRetry={() => void runScreen(result?.page ?? 1)}
            >
              {result ? (
                <OpportunityTable
                  items={result.items}
                  onOpenStock={onOpenStock}
                  scoreLabel={mode === 'short' ? '短线分' : '波段分'}
                  pagination={{
                    current: result.page,
                    pageSize: result.page_size,
                    total: result.total,
                    onChange: (page) => void runScreen(page),
                  }}
                />
              ) : (
                <div className="screen-welcome">
                  <FilterOutlined />
                  <Typography.Title level={4}>设置左侧条件后开始选股</Typography.Title>
                  <Typography.Paragraph type="secondary">
                    建议先选择交易模式和一个系统方案，再根据评分、量比或估值缩小范围。
                  </Typography.Paragraph>
                </div>
              )}
            </DataState>
          </Card>
        </Col>
      </Row>

      <Disclaimer />
      <Modal
        title="保存筛选方案"
        open={saveOpen}
        onOk={confirmSave}
        okButtonProps={{ disabled: !schemeName.trim() }}
        onCancel={() => setSaveOpen(false)}
        okText="保存"
        cancelText="取消"
      >
        <Input
          value={schemeName}
          onChange={(event) => setSchemeName(event.target.value)}
          placeholder="例如：短线放量突破"
          maxLength={30}
          onPressEnter={confirmSave}
        />
      </Modal>
    </div>
  )
}
