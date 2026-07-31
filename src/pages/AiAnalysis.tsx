import DailyAlert from '../components/DailyAlert'
import {
  ApiOutlined,
  HistoryOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Divider,
  List,
  Progress,
  Row,
  Segmented,
  Space,
  Spin,
  Statistic,
  Tag,
  Typography,
  message,
} from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import StockSearchInput, { resolveStockQuery } from '../components/StockSearchInput'
import type {
  AiAnalysisResult,
  AiDepth,
  AiHistoryItem,
  AiServiceStatus,
} from '../aiTypes'

const roleNames: Record<string, string> = {
  joint: '联合研究员',
  technical: '技术与量价分析师',
  fundamental: '基本面与估值分析师',
  risk: '保守风险经理',
  sentiment: '事件与情绪分析师',
}

const ratingColor: Record<string, string> = {
  强烈看多: 'red',
  看多: 'volcano',
  中性: 'default',
  看空: 'green',
  强烈看空: 'cyan',
}

function EvidenceList({ items, empty }: { items?: string[]; empty: string }) {
  return items?.length ? (
    <ul className="reason-list">{items.map((item) => <li key={item}>{item}</li>)}</ul>
  ) : (
    <Typography.Text type="secondary">{empty}</Typography.Text>
  )
}

export default function AiAnalysis({ defaultCode }: { defaultCode: string }) {
  const [code, setCode] = useState(defaultCode)
  const [depth, setDepth] = useState<AiDepth>('standard')
  const [status, setStatus] = useState<AiServiceStatus | null>(null)
  const [result, setResult] = useState<AiAnalysisResult | null>(null)
  const [history, setHistory] = useState<AiHistoryItem[]>([])
  const [loading, setLoading] = useState(false)
  const [testing, setTesting] = useState(false)
  const [notice, contextHolder] = message.useMessage()

  const loadStatus = async (test = false) => {
    if (test) setTesting(true)
    try {
      setStatus(await api.aiStatus(test))
    } catch (reason) {
      notice.error(reason instanceof Error ? reason.message : 'AI状态读取失败')
    } finally {
      if (test) setTesting(false)
    }
  }

  const loadHistory = async (targetCode = code) => {
    if (!/^\d{6}$/.test(targetCode)) {
      setHistory([])
      return
    }
    try {
      setHistory(await api.aiHistory(targetCode, 20))
    } catch {
      setHistory([])
    }
  }

  useEffect(() => {
    setCode(defaultCode)
  }, [defaultCode])

  useEffect(() => {
    void loadStatus()
    void loadHistory()
    // 进入页面和股票变化时读取一次。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code])

  const analyze = async () => {
    setLoading(true)
    try {
      const match = await resolveStockQuery(code)
      if (!match) {
        notice.warning('没有找到这只股票，请输入6位代码、名称或拼音')
        return
      }
      const resolvedCode = match.code
      setCode(resolvedCode)
      const next = await api.aiAnalyze(resolvedCode, depth)
      setResult(next)
      await loadHistory(resolvedCode)
      notice.success('AI联合分析完成')
    } catch (reason) {
      notice.error(reason instanceof Error ? reason.message : 'AI分析失败')
    } finally {
      setLoading(false)
    }
  }

  const roleItems = useMemo(
    () =>
      Object.entries(result?.role_reports ?? {}).map(([key, report]) => ({
        key,
        label: (
          <Space>
            <strong>{roleNames[key] ?? key}</strong>
            <Tag color={report.stance === '看多' ? 'red' : report.stance === '看空' ? 'green' : 'default'}>
              {report.stance} · {report.score}分
            </Tag>
          </Space>
        ),
        children: (
          <Row gutter={[20, 12]}>
            <Col xs={24} lg={12}>
              <Typography.Paragraph>{report.summary}</Typography.Paragraph>
              <strong>主要证据</strong>
              <EvidenceList items={report.evidence} empty="没有足够证据" />
            </Col>
            <Col xs={24} lg={12}>
              <strong>风险与数据限制</strong>
              <EvidenceList items={[...(report.risks ?? []), ...(report.missing ?? [])]} empty="未列出额外限制" />
            </Col>
          </Row>
        ),
      })),
    [result],
  )

  return (
    <div className="page-stack">
      {contextHolder}
      <DailyAlert noticeKey="aianalysis-1"
        type="warning"
        showIcon
        message="AI意见与量化策略分开"
        description="AI报告会变化，不能单独回测，也不保证收益。它只根据页面可核对的数据提出研究意见；固定量化信号请到策略实验室验证。"
      />

      <Card>
        <Row gutter={[16, 16]} align="middle">
          <Col xs={24} md={7}>
            <Typography.Text type="secondary">股票（代码、名称或拼音）</Typography.Text>
            <StockSearchInput
              value={code}
              onChange={setCode}
              onSelect={setCode}
              prefix={<RobotOutlined />}
              enterButton={false}
            />
          </Col>
          <Col xs={24} md={8}>
            <Typography.Text type="secondary">分析深度与成本</Typography.Text>
            <Segmented
              block
              value={depth}
              style={{ marginTop: 6 }}
              onChange={(value) => setDepth(value as AiDepth)}
              options={[
                { label: '快速 · 2次调用', value: 'quick' },
                { label: '标准 · 4次调用', value: 'standard' },
                { label: '深入 · 5次调用', value: 'deep' },
              ]}
            />
          </Col>
          <Col xs={24} md={9}>
            <Space wrap>
              <Button type="primary" size="large" icon={<RobotOutlined />} loading={loading} onClick={() => void analyze()}>
                开始AI联合分析
              </Button>
              <Button icon={<ApiOutlined />} loading={testing} onClick={() => void loadStatus(true)}>
                测试连接
              </Button>
            </Space>
          </Col>
        </Row>
        <Divider />
        <Space wrap>
          <Tag color={status?.configured ? 'green' : 'orange'}>
            {status?.configured ? `密钥已配置 ${status.masked_key ?? ''}` : '尚未配置密钥'}
          </Tag>
          <Tag>{status?.provider ?? 'DeepSeek'} · {status?.model ?? '-'}</Tag>
          {status?.connection === 'ok' && <Tag color="green">连接正常 · {status.latency_ms}ms</Tag>}
          {status?.connection === 'error' && <Tag color="red">连接失败：{status.error}</Tag>}
        </Space>
      </Card>

      <Spin spinning={loading} tip="多个分析角色正在阅读同一份数据并互相复核，通常需要20–60秒">
        {result && (
          <>
            <Card className="ai-verdict-card">
              <Row gutter={[20, 20]} align="middle">
                <Col xs={24} md={6}>
                  <Statistic title={`${result.name} ${result.code}`} value={result.action} />
                  <Tag color={ratingColor[result.rating]} className="ai-rating-tag">{result.rating}</Tag>
                </Col>
                <Col xs={24} md={5}>
                  <Progress type="dashboard" percent={Math.round(result.confidence)} format={(value) => `${value}分`} />
                  <div className="center-text">AI置信度</div>
                </Col>
                <Col xs={24} md={13}>
                  <Typography.Title level={4}>{result.summary}</Typography.Title>
                  <Typography.Paragraph type="secondary">
                    {result.horizon} · {result.method.model} · 用时 {(result.duration_ms / 1000).toFixed(1)} 秒
                  </Typography.Paragraph>
                  <DailyAlert noticeKey="aianalysis-2" type="info" message="角色分歧" description={result.disagreement || '角色意见较为一致'} />
                </Col>
              </Row>
            </Card>

            <Row gutter={[16, 16]}>
              <Col xs={24} lg={12}>
                <Card title="看多证据"><EvidenceList items={result.bull_case} empty="没有形成充分看多证据" /></Card>
              </Col>
              <Col xs={24} lg={12}>
                <Card title="看空证据与风险"><EvidenceList items={[...(result.bear_case ?? []), ...(result.risks ?? [])]} empty="没有列出主要反方证据" /></Card>
              </Col>
              <Col xs={24} lg={12}>
                <Card title="条件式操作计划">
                  <Typography.Paragraph>{result.entry_plan}</Typography.Paragraph>
                  <Typography.Paragraph strong>{result.position_note}</Typography.Paragraph>
                </Card>
              </Col>
              <Col xs={24} lg={12}>
                <Card title="结论失效条件"><EvidenceList items={result.invalidation} empty="没有明确失效条件，不应据此交易" /></Card>
              </Col>
            </Row>

            <Card title="各角色原始意见">
              <Collapse items={roleItems} />
            </Card>

            <Card title={<Space><SafetyCertificateOutlined />操作前检查清单</Space>}>
              <EvidenceList items={result.checklist} empty="没有生成检查清单" />
              {result.data_snapshot.limitations.length > 0 && (
                <DailyAlert noticeKey="aianalysis-3"
                  style={{ marginTop: 16 }}
                  type="warning"
                  showIcon
                  message="本次数据限制"
                  description={result.data_snapshot.limitations.join('；')}
                />
              )}
            </Card>
          </>
        )}
      </Spin>

      <Card title={<Space><HistoryOutlined />这只股票的AI分析历史</Space>}>
        <List
          dataSource={history}
          locale={{ emptyText: '还没有历史分析' }}
          renderItem={(item) => (
            <List.Item>
              <List.Item.Meta
                title={
                  <Space>
                    <strong>{item.created_at.replace('T', ' ')}</strong>
                    {item.rating && <Tag color={ratingColor[item.rating]}>{item.rating}</Tag>}
                    <Tag>{item.depth}</Tag>
                  </Space>
                }
                description={item.summary ?? item.error_message ?? item.status}
              />
              {item.confidence != null && <span>{Math.round(item.confidence)}分</span>}
            </List.Item>
          )}
        />
      </Card>
    </div>
  )
}
