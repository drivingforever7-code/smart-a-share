import { DeleteOutlined, RobotOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Col, DatePicker, Empty, Form, Input, InputNumber, List, Row, Segmented, Space, Statistic, Tag, Typography } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import { api } from '../api'
import StockSearchInput from '../components/StockSearchInput'
import Disclaimer from '../components/Disclaimer'
import { deleteTradeJournal, getTradeJournal, saveTradeJournal, type TradeJournalEntry } from '../storage'
import type { TradeReviewPayload, TradeReviewResult } from '../tradeReviewTypes'

export default function TradeReview() {
  const [form] = Form.useForm()
  const [code, setCode] = useState('')
  const [entries, setEntries] = useState<TradeJournalEntry[]>(getTradeJournal)
  const [result, setResult] = useState<TradeReviewResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const submit = async (values: Record<string, unknown>) => {
    const payload: TradeReviewPayload = { description: String(values.description), code: code || undefined, trade_date: values.trade_date ? dayjs(values.trade_date as string).format('YYYY-MM-DD') : undefined, action: (values.action as TradeReviewPayload['action']) || '其他', price: values.price as number | undefined, position_pct: values.position_pct as number | undefined }
    setLoading(true)
    try { const review = await api.tradeReview(payload); setResult(review); setEntries(saveTradeJournal({ payload, review: review.review })); setError(null) }
    catch (reason) { setEntries(saveTradeJournal({ payload })); setError(reason instanceof Error ? reason.message : 'AI 锐评失败，记录已保存在本地') }
    finally { setLoading(false) }
  }
  return <div className="page-stack trade-review-page">
    <Row gutter={[16, 16]}><Col xs={24} xl={14}><Card className="content-card" title="描述你今天做了什么"><Form form={form} layout="vertical" onFinish={submit} initialValues={{ action: '买入' }}>
      <Row gutter={12}><Col span={12}><Form.Item label="股票（可选）"><StockSearchInput value={code} onChange={setCode} onSelect={setCode} /></Form.Item></Col><Col span={12}><Form.Item name="trade_date" label="交易日期"><DatePicker style={{ width: '100%' }} /></Form.Item></Col></Row>
      <Form.Item name="action" label="操作"><Segmented options={['买入', '卖出', '加仓', '清仓', '其他']} /></Form.Item>
      <Row gutter={12}><Col span={12}><Form.Item name="price" label="成交价格"><InputNumber min={0.01} precision={3} style={{ width: '100%' }} /></Form.Item></Col><Col span={12}><Form.Item name="position_pct" label="仓位 %"><InputNumber min={0} max={100} style={{ width: '100%' }} /></Form.Item></Col></Row>
      <Form.Item name="description" label="交易想法与经过" rules={[{ required: true, min: 5 }]}><Input.TextArea rows={7} placeholder="例如：今天 10:15 看到放量突破，以 12.35 元买入半仓，担心错过所以没有等回踩……" /></Form.Item>
      <Alert type="info" showIcon message="记录只保存在当前浏览器；点击后才会把本次内容发送给 DeepSeek。" style={{ marginBottom: 16 }} />
      <Button type="primary" htmlType="submit" icon={<RobotOutlined />} loading={loading}>让 AI 锐评</Button>
    </Form></Card></Col><Col xs={24} xl={10}><Card className="content-card" title="本次锐评">{error && <Alert type="error" showIcon closable message={error} />}{result ? <Space direction="vertical" size={12} style={{ width: '100%' }}><Statistic title="执行评分" value={result.review.score ?? 0} suffix="/100" /><Typography.Title level={4}>{result.review.verdict}</Typography.Title>{(['entry_review','exit_review','position_review','discipline_review'] as const).map((key) => result.review[key] && <Typography.Paragraph key={key}>{result.review[key]}</Typography.Paragraph>)}<Typography.Text strong>主要问题</Typography.Text><Space wrap>{result.review.mistakes?.map((item) => <Tag color="error" key={item}>{item}</Tag>)}</Space><Typography.Text strong>下一次改进</Typography.Text>{result.review.improvement_actions?.map((item) => <Typography.Paragraph key={item}>· {item}</Typography.Paragraph>)}</Space> : <Empty description="提交一笔交易后显示锐评" />}</Card></Col></Row>
    <Card className="content-card" title="本地复盘记录"><List dataSource={entries} locale={{ emptyText: '暂无记录' }} renderItem={(entry) => <List.Item actions={[<Button key="delete" danger type="text" icon={<DeleteOutlined />} onClick={() => setEntries(deleteTradeJournal(entry.id))} />]}><List.Item.Meta title={`${String(entry.payload.action || '')} ${String(entry.payload.code || '')}`} description={`${new Date(entry.createdAt).toLocaleString()} · ${String(entry.payload.description || '')}`} /></List.Item>} /></Card>
    <Disclaimer />
  </div>
}
