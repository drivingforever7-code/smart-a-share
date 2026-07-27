import {
  ApiOutlined,
  CheckCircleOutlined,
  CloudDownloadOutlined,
  DatabaseOutlined,
  ExclamationCircleOutlined,
  ReloadOutlined,
  SaveOutlined,
} from '@ant-design/icons'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Form,
  InputNumber,
  List,
  Row,
  Segmented,
  Space,
  Tag,
  Typography,
} from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import DataState from '../components/DataState'
import { formatTime } from '../format'
import { getSettings, saveSettings, type LocalSettings } from '../storage'
import type { DataStatus } from '../types'
import type { AiServiceStatus } from '../aiTypes'

const statusMap = {
  ready: { color: 'success', text: '可用', icon: <CheckCircleOutlined /> },
  stale: { color: 'warning', text: '可能过期', icon: <ExclamationCircleOutlined /> },
  empty: { color: 'default', text: '暂无数据', icon: <DatabaseOutlined /> },
  error: { color: 'error', text: '异常', icon: <ExclamationCircleOutlined /> },
} as const

export default function Settings() {
  const { message } = App.useApp()
  const [form] = Form.useForm<LocalSettings>()
  const [status, setStatus] = useState<DataStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [aiStatus, setAiStatus] = useState<AiServiceStatus | null>(null)
  const [testingAi, setTestingAi] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadStatus = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setStatus(await api.dataStatus())
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '无法读取数据状态')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadStatus()
    api.aiStatus().then(setAiStatus).catch(() => setAiStatus(null))
  }, [loadStatus])

  const refreshQuotes = async () => {
    setRefreshing(true)
    try {
      const result = await api.refreshQuotes()
      message.success(`实时行情已更新，共 ${result.count} 只`)
      await loadStatus()
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : '实时行情更新失败')
    } finally {
      setRefreshing(false)
    }
  }

  const submitSettings = (values: LocalSettings) => {
    saveSettings(values)
    message.success('本地设置已保存')
  }

  return (
    <div className="page-stack">
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={15}>
          <Card
            className="content-card"
            title={<><DatabaseOutlined /> 数据状态</>}
            extra={
              <Space>
                <Button icon={<ReloadOutlined />} onClick={() => void loadStatus()}>
                  检查状态
                </Button>
                <Button
                  type="primary"
                  icon={<CloudDownloadOutlined />}
                  loading={refreshing}
                  onClick={() => void refreshQuotes()}
                >
                  更新实时行情
                </Button>
              </Space>
            }
          >
            <DataState loading={loading} error={error} onRetry={() => void loadStatus()}>
              {status && (
                <>
                  <Alert
                    type={status.akshare_available ? 'success' : 'error'}
                    showIcon
                    message={status.akshare_available ? 'AKShare 数据接口已安装' : 'AKShare 尚未安装'}
                    description={
                      status.akshare_available
                        ? '可以获取公开市场数据；免费接口偶尔会延迟或中断。'
                        : '请先按 README 安装 Python 后端依赖，否则无法获取真实行情。'
                    }
                    className="settings-alert"
                  />
                  <List
                    dataSource={status.items}
                    renderItem={(item) => {
                      const state = statusMap[item.status]
                      return (
                        <List.Item
                          actions={[
                            <Tag key="status" color={state.color} icon={state.icon}>{state.text}</Tag>,
                          ]}
                        >
                          <List.Item.Meta
                            title={item.name}
                            description={
                              <Space direction="vertical" size={1}>
                                <span>{item.description}</span>
                                <Typography.Text type="secondary">
                                  {item.records.toLocaleString()} 条
                                  {item.updated_at ? ` · 更新于 ${formatTime(item.updated_at)}` : ''}
                                </Typography.Text>
                              </Space>
                            }
                          />
                        </List.Item>
                      )
                    }}
                  />
                  <Typography.Text type="secondary">
                    数据库位置：{status.database_path}
                  </Typography.Text>
                </>
              )}
            </DataState>
          </Card>
        </Col>

        <Col xs={24} xl={9}>
          <Card className="content-card" title="本地偏好">
            <Form
              form={form}
              layout="vertical"
              initialValues={getSettings()}
              onFinish={submitSettings}
            >
              <Form.Item
                name="refreshSeconds"
                label="实时行情刷新间隔"
                extra="免费接口不适合过于频繁请求，建议保持 10 秒。"
                rules={[{ required: true }]}
              >
                <InputNumber min={5} max={120} addonAfter="秒" style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="includeSt" label="ST 股票">
                <Segmented
                  block
                  options={[
                    { label: '默认排除', value: false },
                    { label: '允许显示', value: true },
                  ]}
                />
              </Form.Item>
              <Form.Item name="includeNew" label="上市不足 120 天">
                <Segmented
                  block
                  options={[
                    { label: '默认排除', value: false },
                    { label: '允许显示', value: true },
                  ]}
                />
              </Form.Item>
              <Form.Item name="includeSuspended" label="停牌股票">
                <Segmented
                  block
                  options={[
                    { label: '默认排除', value: false },
                    { label: '允许显示', value: true },
                  ]}
                />
              </Form.Item>
              <Button type="primary" htmlType="submit" icon={<SaveOutlined />} block>
                保存设置
              </Button>
            </Form>
          </Card>
          <Card className="content-card" title={<><ApiOutlined /> DeepSeek AI 服务</>} style={{ marginTop: 16 }}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Alert
                type={aiStatus?.configured ? 'success' : 'warning'}
                showIcon
                message={aiStatus?.configured ? '密钥已安全配置' : '尚未配置密钥'}
                description={
                  aiStatus?.configured
                    ? `${aiStatus.provider} · ${aiStatus.model} · ${aiStatus.masked_key ?? ''}`
                    : '普通量化功能仍可使用；AI联合分析暂不可用。'
                }
              />
              {aiStatus?.connection === 'ok' && (
                <Tag color="green">连接正常 · {aiStatus.latency_ms}ms</Tag>
              )}
              {aiStatus?.connection === 'error' && (
                <Tag color="red">连接失败：{aiStatus.error}</Tag>
              )}
              <Button
                icon={<ApiOutlined />}
                loading={testingAi}
                onClick={async () => {
                  setTestingAi(true)
                  try {
                    const next = await api.aiStatus(true)
                    setAiStatus(next)
                    if (next.connection === 'ok') message.success('DeepSeek连接正常')
                    else message.error(next.error ?? 'DeepSeek连接失败')
                  } finally {
                    setTestingAi(false)
                  }
                }}
              >
                测试DeepSeek连接
              </Button>
              <Typography.Text type="secondary">
                完整密钥只由本机后端读取，页面、接口响应和日志不会显示。
              </Typography.Text>
            </Space>
          </Card>
        </Col>
      </Row>

      <Alert
        type="warning"
        showIcon
        message="关于实时行情"
        description="当前使用免费的公开数据接口，交易时间默认每 10 秒更新一次，不是交易所逐笔成交行情。数据源失败时系统会保留最后一次有效缓存，并明确显示获取时间。"
      />
    </div>
  )
}
