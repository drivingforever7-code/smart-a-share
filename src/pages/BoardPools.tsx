import { DeleteOutlined, ExperimentOutlined, SyncOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Col, Collapse, Progress, Row, Segmented, Space, Statistic, Table, Tag, Typography } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import type { BoardPoolItem, BoardPoolResponse, BoardPoolType } from '../boardPoolTypes'
import DataState from '../components/DataState'
import Disclaimer from '../components/Disclaimer'
import { useDismissedRows } from '../useDismissedRows'

const names: Record<BoardPoolType, string> = { streak: '连板晋级池', down_repair: '跌停修复池' }

export default function BoardPools({ onOpenStock }: { onOpenStock: (code: string) => void }) {
  const [pool, setPool] = useState<BoardPoolType>('streak')
  const [days, setDays] = useState(5)
  const [data, setData] = useState<BoardPoolResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { dismissed, dismiss } = useDismissedRows('board-pools')
  const load = useCallback(async () => {
    setLoading(true)
    try { setData(await api.boardPools(days)); setError(null) }
    catch (reason) { setError(reason instanceof Error ? reason.message : '连板与跌停数据获取失败') }
    finally { setLoading(false) }
  }, [days])
  useEffect(() => { void load() }, [load])
  const stats = data?.stats[pool]
  const grouped = useMemo(() => (data?.available_dates || []).map((date) => ({
    date, items: (data?.items || []).filter((item) => item.pool_type === pool && item.trade_date === date && !dismissed.has(String(item.id))),
  })), [data, dismissed, pool])
  const columns = [
    { title: '排名', dataIndex: 'rank', width: 70, render: (value: number) => <Tag color={value === 1 ? 'gold' : 'default'}>#{value}</Tag> },
    { title: '股票', render: (_: unknown, item: BoardPoolItem) => <button className="stock-link" onClick={() => onOpenStock(item.code)}><strong>{item.name}</strong><span>{item.code} · {item.industry || '行业未知'}</span></button> },
    { title: pool === 'streak' ? '晋级概率' : '修复概率', dataIndex: 'predicted_probability', render: (value: number) => <Progress percent={Math.round(value * 100)} size="small" /> },
    { title: '建议', dataIndex: 'recommendation', render: (value: string) => <Tag color={value.includes('小仓') ? 'gold' : 'blue'}>{value}</Tag> },
    { title: '结果', dataIndex: 'outcome', render: (value: string) => <Tag color={value === 'success' ? 'success' : value === 'failed' ? 'error' : 'processing'}>{value === 'success' ? '成功' : value === 'failed' ? '失败' : '待验证'}</Tag> },
    { title: '版本', dataIndex: 'model_version' },
    { title: '操作', render: (_: unknown, item: BoardPoolItem) => <Space><Button type="link" onClick={() => onOpenStock(item.code)}>详情</Button><Button danger type="text" icon={<DeleteOutlined />} onClick={() => dismiss(item.id)} /></Space> },
  ]
  return <div className="page-stack board-pool-page">
    <div className="page-toolbar"><Segmented value={pool} options={[{ label: '连板池', value: 'streak' }, { label: '跌停池', value: 'down_repair' }]} onChange={(value) => setPool(value as BoardPoolType)} /><Space><Segmented value={days} options={[3, 5, 10]} onChange={(value) => setDays(Number(value))} /><Button icon={<SyncOutlined />} loading={loading} onClick={() => void load()}>刷新</Button></Space></div>
    {data?.warning && <Alert type="warning" showIcon message={data.warning} closable />}
    {stats && <Row gutter={[16, 16]}>
      <Col xs={12} lg={6}><Card className="metric-card"><Statistic title="历史成功率" value={(stats.success_rate ?? 0) * 100} precision={1} suffix="%" /></Card></Col>
      <Col xs={12} lg={6}><Card className="metric-card"><Statistic title="方向准确度" value={(stats.accuracy ?? 0) * 100} precision={1} suffix="%" /></Card></Col>
      <Col xs={12} lg={6}><Card className="metric-card"><Statistic title="Brier 分数" value={stats.brier_score ?? 0} precision={4} /></Card></Col>
      <Col xs={12} lg={6}><Card className="metric-card"><Statistic title="有效样本" value={stats.sample_count} suffix={` / ${stats.trading_days}日`} /></Card></Col>
    </Row>}
    <Collapse items={[{ key: 'method', label: <Space><ExperimentOutlined />模型方法与升级记录</Space>, children: <Space direction="vertical"><Typography.Paragraph>{data?.methodology[pool]}</Typography.Paragraph><Typography.Text>{data?.methodology.validation}</Typography.Text>{data?.versions.filter((row) => row.pool_type === pool).map((row, index) => <Tag key={index}>{String(row.version)} · {row.is_active ? '使用中' : '候选/历史'}</Tag>)}</Space> }]} />
    <DataState loading={loading} error={error} empty={!grouped.some((group) => group.items.length)} emptyText="当前没有通过质量门槛的候选，不会为了凑满 10 只而降低标准。" onRetry={() => void load()}>
      <Collapse defaultActiveKey={grouped[0]?.date} items={grouped.filter((group) => group.items.length).map((group) => ({ key: group.date, label: `${group.date} · ${group.items.length} 只`, children: <Table rowKey="id" size="small" pagination={false} dataSource={group.items} columns={columns} expandable={{ expandedRowRender: (item) => <Space direction="vertical"><Typography.Text>依据：{item.reasons.join('；')}</Typography.Text><Typography.Text type="danger">风险：{item.risks.join('；')}</Typography.Text><Typography.Text type="secondary">特征：{JSON.stringify(item.features)}</Typography.Text>{item.review && <Typography.Text>{item.review.summary}</Typography.Text>}</Space> }} /> }))} />
    </DataState>
    <Disclaimer />
  </div>
}
