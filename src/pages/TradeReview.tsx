import { DeleteOutlined, RobotOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Col, DatePicker, Empty, Form, Input, InputNumber, List, Row, Segmented, Space, Statistic, Tag, Typography } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import { api } from '../api'
import Disclaimer from '../components/Disclaimer'
import StockSearchInput from '../components/StockSearchInput'
import { deleteTradeJournal, getTradeJournal, saveTradeJournal, type TradeJournalEntry } from '../storage'
import type { TradeReviewPayload, TradeReviewResult } from '../tradeReviewTypes'

const priceText = (value?: number | null) => value == null ? '--' : `¥${value.toFixed(2)}`

export default function TradeReview() {
  const [form] = Form.useForm()
  const [code, setCode] = useState('')
  const [entries, setEntries] = useState<TradeJournalEntry[]>(getTradeJournal)
  const [result, setResult] = useState<TradeReviewResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (values: Record<string, unknown>) => {
    if (!/^\d{6}$/.test(code)) {
      setError('请先选择一只股票，系统需要真实行情才能给出目标价和止损价。')
      return
    }
    const payload: TradeReviewPayload = {
      description: String(values.description),
      code,
      trade_date: values.trade_date ? dayjs(values.trade_date as string).format('YYYY-MM-DD') : undefined,
      action: (values.action as TradeReviewPayload['action']) || '其他',
      price: values.price as number | undefined,
      position_pct: values.position_pct as number | undefined,
    }
    setLoading(true)
    try {
      const review = await api.tradeReview(payload)
      setResult(review)
      setEntries(saveTradeJournal({ payload, review: review.review }))
      setError(null)
    } catch (reason) {
      setEntries(saveTradeJournal({ payload }))
      setError(reason instanceof Error ? reason.message : 'AI 分析失败，记录已保存在本地')
    } finally { setLoading(false) }
  }

  const plan = result?.review.action_plan
  const actionColor = plan?.recommended_action === '清仓' || plan?.recommended_action === '减仓'
    ? 'error'
    : plan?.recommended_action === '加仓' || plan?.recommended_action === '分批买入'
      ? 'gold'
      : 'cyan'

  return <div className="page-stack trade-review-page">
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={11}>
        <Card className="content-card" title="告诉我你买了什么、卖了什么">
          <Form form={form} layout="vertical" onFinish={submit} initialValues={{ action: '买入' }}>
            <Row gutter={12}>
              <Col span={12}><Form.Item label="股票（必须选择）"><StockSearchInput value={code} onChange={setCode} onSelect={setCode} /></Form.Item></Col>
              <Col span={12}><Form.Item name="trade_date" label="交易日期"><DatePicker style={{ width: '100%' }} /></Form.Item></Col>
            </Row>
            <Form.Item name="action" label="操作"><Segmented options={['买入', '卖出', '加仓', '清仓', '其他']} /></Form.Item>
            <Row gutter={12}>
              <Col span={12}><Form.Item name="price" label="成交价格"><InputNumber min={0.01} precision={3} style={{ width: '100%' }} /></Form.Item></Col>
              <Col span={12}><Form.Item name="position_pct" label="当前仓位 %"><InputNumber min={0} max={100} style={{ width: '100%' }} /></Form.Item></Col>
            </Row>
            <Form.Item name="description" label="交易经过和你的疑问" rules={[{ required: true, min: 5 }]}>
              <Input.TextArea rows={7} placeholder="例如：今天以 12.35 元买入半仓，现在应该继续持有还是卖出？目标价和止损价放在哪里？" />
            </Form.Item>
            <Alert type="info" showIcon message="系统会结合真实日线和当前评分，优先给出措施、目标价、止损价与触发条件。" style={{ marginBottom: 16 }} />
            <Button type="primary" htmlType="submit" icon={<RobotOutlined />} loading={loading}>生成具体操作方案</Button>
          </Form>
        </Card>
      </Col>
      <Col xs={24} xl={13}>
        <Card className="content-card" title="现在具体怎么做">
          {error && <Alert type="error" showIcon closable message={error} style={{ marginBottom: 12 }} />}
          {result ? <Space direction="vertical" size={14} style={{ width: '100%' }}>
            <Alert
              type={actionColor === 'error' ? 'error' : actionColor === 'gold' ? 'warning' : 'info'}
              showIcon
              message={<Space><span>当前措施</span><Tag color={actionColor}>{plan?.recommended_action || '等待'}</Tag></Space>}
              description={plan?.action_summary || '行情依据不足，暂不进行新的交易动作。'}
            />
            <Row gutter={[10, 10]}>
              <Col xs={12} md={6}><Card size="small"><Statistic title="当前参考价" value={priceText(plan?.current_reference_price)} /></Card></Col>
              <Col xs={12} md={6}><Card size="small"><Statistic title="第一目标价" value={priceText(plan?.target_price)} /></Card></Col>
              <Col xs={12} md={6}><Card size="small"><Statistic title="第二目标价" value={priceText(plan?.second_target_price)} /></Card></Col>
              <Col xs={12} md={6}><Card size="small"><Statistic title="止损价" value={priceText(plan?.stop_loss_price)} valueStyle={{ color: '#ff5f6d' }} /></Card></Col>
            </Row>
            <Typography.Text strong>加仓 / 重新买入区间</Typography.Text>
            <Typography.Paragraph>{plan?.add_or_rebuy_range ? `${priceText(plan.add_or_rebuy_range[0])} – ${priceText(plan.add_or_rebuy_range[1])}` : '暂不具备可靠区间'}</Typography.Paragraph>
            <Space wrap>
              <Tag color="purple">建议仓位 {plan?.suggested_position_pct == null ? '--' : `${plan.suggested_position_pct}%`}</Tag>
              <Tag>观察周期 {plan?.holding_period || '--'}</Tag>
            </Space>
            <Typography.Text strong>执行触发条件</Typography.Text>
            {(plan?.trigger_plan?.length ? plan.trigger_plan : ['没有足够数据形成触发条件，先等待。']).map((item) => <Typography.Paragraph key={item}>· {item}</Typography.Paragraph>)}
            <Typography.Text type="secondary">价格依据：{plan?.price_basis || '未提供'}</Typography.Text>
            <Typography.Title level={5}>为什么这样处理</Typography.Title>
            {plan?.action_rationale?.map((item) => <Typography.Paragraph key={item}>· {item}</Typography.Paragraph>)}
            <Typography.Text strong>本次操作复盘</Typography.Text>
            <Typography.Paragraph>{result.review.entry_review || result.review.exit_review || result.review.verdict}</Typography.Paragraph>
            <Space wrap>{result.review.mistakes?.map((item) => <Tag color="error" key={item}>{item}</Tag>)}</Space>
          </Space> : <Empty description="提交交易后显示具体操作、目标价和止损价" />}
        </Card>
      </Col>
    </Row>
    <Card className="content-card" title="本地复盘记录">
      <List dataSource={entries} locale={{ emptyText: '暂无记录' }} renderItem={(entry) => <List.Item actions={[<Button key="delete" danger type="text" icon={<DeleteOutlined />} onClick={() => setEntries(deleteTradeJournal(entry.id))} />]}><List.Item.Meta title={`${String(entry.payload.action || '')} ${String(entry.payload.code || '')}`} description={`${new Date(entry.createdAt).toLocaleString()} · ${String(entry.payload.description || '')}`} /></List.Item>} />
    </Card>
    <Disclaimer />
  </div>
}