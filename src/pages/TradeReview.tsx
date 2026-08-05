import { DeleteOutlined, RobotOutlined, SendOutlined, UserOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Col, Empty, Input, Row, Space, Statistic, Tag, Typography } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import Disclaimer from '../components/Disclaimer'
import type { TradeActionPlan, TradeReviewMessage, TradeReviewResult } from '../tradeReviewTypes'

const CHAT_KEY = 'smart-a-share:trade-review-chat'
interface ChatItem extends TradeReviewMessage { id: string; review?: TradeReviewResult['review'] }
const priceText = (value?: number | null) => value == null ? '--' : `¥${value.toFixed(2)}`

function loadChat(): ChatItem[] {
  try { return JSON.parse(localStorage.getItem(CHAT_KEY) || '[]') as ChatItem[] }
  catch { return [] }
}

function ActionPlan({ plan }: { plan?: TradeActionPlan }) {
  if (!plan) return null
  const color = plan.recommended_action === '清仓' || plan.recommended_action === '减仓' ? 'error' : plan.recommended_action === '加仓' || plan.recommended_action === '分批买入' ? 'gold' : 'cyan'
  return <Card size="small" className="trade-action-plan" title={<Space><span>具体操作</span><Tag color={color}>{plan.recommended_action || '等待'}</Tag></Space>}>
    <Typography.Paragraph>{plan.action_summary}</Typography.Paragraph>
    <Row gutter={[8, 8]}>
      <Col xs={12} md={6}><Statistic title="当前参考价" value={priceText(plan.current_reference_price)} /></Col>
      <Col xs={12} md={6}><Statistic title="第一目标价" value={priceText(plan.target_price)} /></Col>
      <Col xs={12} md={6}><Statistic title="第二目标价" value={priceText(plan.second_target_price)} /></Col>
      <Col xs={12} md={6}><Statistic title="止损价" value={priceText(plan.stop_loss_price)} valueStyle={{ color: '#ff5f6d' }} /></Col>
    </Row>
    <Space size={[8, 8]} wrap style={{ marginTop: 10 }}>
      <Tag color="purple">建议仓位 {plan.suggested_position_pct == null ? '--' : `${plan.suggested_position_pct}%`}</Tag>
      <Tag>观察周期 {plan.holding_period || '--'}</Tag>
      <Tag>加仓区间 {plan.add_or_rebuy_range ? `${priceText(plan.add_or_rebuy_range[0])}–${priceText(plan.add_or_rebuy_range[1])}` : '--'}</Tag>
    </Space>
    {!!plan.trigger_plan?.length && <><Typography.Text strong>触发条件</Typography.Text>{plan.trigger_plan.map((item) => <Typography.Paragraph key={item}>· {item}</Typography.Paragraph>)}</>}
    <Typography.Text type="secondary">依据：{plan.price_basis || '等待有效行情'}</Typography.Text>
  </Card>
}

export default function TradeReview() {
  const [messages, setMessages] = useState<ChatItem[]>(loadChat)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => { localStorage.setItem(CHAT_KEY, JSON.stringify(messages)); endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const send = async () => {
    const content = input.trim()
    if (content.length < 2 || loading) return
    const previous = messages
    const userItem: ChatItem = { id: crypto.randomUUID(), role: 'user', content }
    setMessages([...previous, userItem])
    setInput('')
    setLoading(true)
    setError(null)
    try {
      const history = previous.slice(-10).map(({ role, content: text }) => ({ role, content: text }))
      const result = await api.tradeReview({ description: content, history })
      const reply = result.review.reply || result.review.action_plan?.action_summary || '请继续告诉我你的交易情况。'
      setMessages((items) => [...items, { id: crypto.randomUUID(), role: 'assistant', content: reply, review: result.review }])
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'AI 暂时无法回答，请稍后重试。')
    } finally { setLoading(false) }
  }

  const clear = () => { setMessages([]); localStorage.removeItem(CHAT_KEY); setError(null) }

  return <div className="page-stack trade-review-page">
    <Card
      className="content-card trade-chat-card"
      title={<Space><RobotOutlined /><span>交易复盘对话</span></Space>}
      extra={<Button type="text" danger icon={<DeleteOutlined />} disabled={!messages.length} onClick={clear}>清空对话</Button>}
    >
      <Alert type="info" showIcon message="直接告诉我你买了或卖了什么，例如：今天 12.35 买了贵州茅台半仓，现在怎么办？" description="系统会自动识别股票；如果名称不明确会先追问，不会凭空生成目标价。" />
      <div className="trade-chat-history">
        {!messages.length && <Empty description="直接在下面输入你的交易情况" />}
        {messages.map((item) => <div key={item.id} className={`trade-chat-row trade-chat-row--${item.role}`}>
          <div className="trade-chat-avatar">{item.role === 'user' ? <UserOutlined /> : <RobotOutlined />}</div>
          <div className="trade-chat-bubble">
            <Typography.Paragraph>{item.content}</Typography.Paragraph>
            {item.role === 'assistant' && <ActionPlan plan={item.review?.action_plan} />}
          </div>
        </div>)}
        {loading && <div className="trade-chat-row trade-chat-row--assistant"><div className="trade-chat-avatar"><RobotOutlined /></div><div className="trade-chat-bubble"><Typography.Text type="secondary">正在读取行情并整理具体措施…</Typography.Text></div></div>}
        <div ref={endRef} />
      </div>
      {error && <Alert type="error" closable showIcon message={error} onClose={() => setError(null)} style={{ marginBottom: 12 }} />}
      <div className="trade-chat-composer">
        <Input.TextArea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onPressEnter={(event) => { if (!event.shiftKey) { event.preventDefault(); void send() } }}
          autoSize={{ minRows: 3, maxRows: 7 }}
          placeholder="直接说：我今天以什么价格买了/卖了什么，现在应该怎么操作？"
        />
        <Button type="primary" size="large" icon={<SendOutlined />} loading={loading} onClick={() => void send()}>发送</Button>
      </div>
      <Typography.Text type="secondary">Enter 发送，Shift + Enter 换行；对话只保存在当前浏览器。</Typography.Text>
    </Card>
    <Disclaimer />
  </div>
}