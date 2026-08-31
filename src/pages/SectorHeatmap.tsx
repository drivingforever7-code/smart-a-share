import { useEffect, useMemo, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import { Alert, Button, Card, Col, Descriptions, Drawer, List, Progress, Row, Segmented, Space, Spin, Statistic, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ReloadOutlined, RobotOutlined } from '@ant-design/icons'
import { api } from '../api'
import type { SectorDetailResponse, SectorHeatmapResponse, SectorItem, SectorKind, SectorStock } from '../sectorTypes'

type Props = { onOpenStock: (code: string) => void }
const red = '#f04f64'
const green = '#19b981'
const cyan = '#26b9d2'
const pct = (v?: number | null) => v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
const money = (v?: number | null) => v == null ? '—' : Math.abs(v) >= 1e8 ? `${(v / 1e8).toFixed(2)} 亿` : Math.abs(v) >= 1e4 ? `${(v / 1e4).toFixed(1)} 万` : `${v.toFixed(0)} 元`
const adviceColor = (v: string) => v.includes('买入') ? 'red' : v.includes('卖出') || v.includes('回避') ? 'green' : 'gold'

export default function SectorHeatmap({ onOpenStock }: Props) {
  const [kind, setKind] = useState<SectorKind>('industry')
  const [data, setData] = useState<SectorHeatmapResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState('')
  const [detail, setDetail] = useState<SectorDetailResponse | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const load = async (force = false) => {
    if (force) setRefreshing(true)
    try {
      setData(await api.sectors(kind, force, true))
      setError('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '板块数据加载失败')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    setData(null)
    setLoading(true)
    void load()
    const timer = window.setInterval(() => void load(), 10_000)
    return () => window.clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind])

  const openSector = async (name: string) => {
    setSelected(name)
    setDetail(null)
    setDetailLoading(true)
    try {
      setDetail(await api.sectorDetail(kind, name, true))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '板块详情加载失败')
      setSelected('')
    } finally {
      setDetailLoading(false)
    }
  }

  const treemap = useMemo(() => ({
    backgroundColor: 'transparent',
    tooltip: { formatter: (p: { name: string; data: { change: number; heat: number; flow: number | null } }) => `${p.name}<br/>涨跌：${pct(p.data.change)}<br/>热度：${p.data.heat}<br/>净流入：${money(p.data.flow)}` },
    series: [{
      type: 'treemap', roam: false, nodeClick: false, breadcrumb: { show: false },
      label: { color: '#fff', formatter: (p: { name: string; data: { change: number } }) => `${p.name}\n${pct(p.data.change)}` },
      itemStyle: { borderColor: '#08111f', borderWidth: 2, gapWidth: 2 },
      data: (data?.items ?? []).slice(0, 40).map((item) => ({
        name: item.name, value: Math.max(1, item.heat), change: item.change_pct ?? 0, heat: item.heat, flow: item.main_net_inflow,
        itemStyle: { color: (item.change_pct ?? 0) > .15 ? red : (item.change_pct ?? 0) < -.15 ? green : '#72829c', opacity: .45 + item.heat / 180 },
      })),
    }],
  }), [data])

  const strength = useMemo(() => {
    const items = (data?.items ?? []).slice(0, 15).reverse()
    return {
      backgroundColor: 'transparent', grid: { left: 80, right: 24, top: 12, bottom: 28 },
      xAxis: { type: 'value', max: 100, axisLabel: { color: '#7f91aa' }, splitLine: { lineStyle: { color: 'rgba(111,142,174,.13)' } } },
      yAxis: { type: 'category', data: items.map(x => x.name), axisLabel: { color: '#c8d6e8' }, axisLine: { show: false }, axisTick: { show: false } },
      tooltip: { trigger: 'axis' },
      series: [{ type: 'bar', barWidth: 12, data: items.map(x => ({ value: x.combined_score ?? x.strength, itemStyle: { color: x.recommendation === '买入关注' ? red : x.recommendation === '卖出/回避' ? green : cyan, borderRadius: [0, 4, 4, 0] } })) }],
    }
  }, [data])

  const flow = useMemo(() => {
    const items = (data?.items ?? []).filter(x => x.main_net_inflow != null).sort((a, b) => Math.abs(b.main_net_inflow ?? 0) - Math.abs(a.main_net_inflow ?? 0)).slice(0, 12).reverse()
    return {
      backgroundColor: 'transparent', grid: { left: 82, right: 24, top: 12, bottom: 28 },
      xAxis: { type: 'value', axisLabel: { color: '#7f91aa', formatter: (v: number) => `${(v / 1e8).toFixed(1)}亿` }, splitLine: { lineStyle: { color: 'rgba(111,142,174,.13)' } } },
      yAxis: { type: 'category', data: items.map(x => x.name), axisLabel: { color: '#c8d6e8' }, axisLine: { show: false }, axisTick: { show: false } },
      tooltip: { trigger: 'axis' },
      series: [{ type: 'bar', barWidth: 12, data: items.map(x => ({ value: x.main_net_inflow, itemStyle: { color: (x.main_net_inflow ?? 0) >= 0 ? red : green, borderRadius: 4 } })) }],
    }
  }, [data])

  const columns: ColumnsType<SectorItem> = [
    { title: '排名', dataIndex: 'rank', width: 60 },
    { title: '板块', dataIndex: 'name', width: 140, render: (name: string) => <Button type="link" onClick={() => void openSector(name)}>{name}</Button> },
    { title: '涨跌', dataIndex: 'change_pct', width: 90, render: (v: number | null) => <span className={(v ?? 0) >= 0 ? 'stock-up' : 'stock-down'}>{pct(v)}</span> },
    { title: '强度 / 热度', width: 155, render: (_, x) => <Space direction="vertical" size={0}><span>{x.combined_score ?? x.strength} / {x.heat}</span><Progress percent={Math.round(x.heat)} showInfo={false} size="small" /></Space> },
    { title: '上涨广度', dataIndex: 'breadth', width: 100, render: (v: number) => `${v.toFixed(1)}%` },
    { title: '主力净流入', dataIndex: 'main_net_inflow', width: 125, render: money },
    { title: '量化建议', dataIndex: 'recommendation', width: 110, render: (v: string) => <Tag color={adviceColor(v)}>{v}</Tag> },
    { title: 'AI 复核', width: 170, render: (_, x) => x.ai_view ? `${x.ai_view.action} · ${x.ai_view.score.toFixed(0)}分` : '量化结果' },
    { title: '领涨股', dataIndex: 'leader', width: 110 },
  ]

  const stockColumns: ColumnsType<SectorStock> = [
    { title: '股票', render: (_, x) => <Button type="link" onClick={() => onOpenStock(x.code)}>{x.name} {x.code}</Button> },
    { title: '涨跌', dataIndex: 'change_pct', width: 90, render: (v: number | null) => <span className={(v ?? 0) >= 0 ? 'stock-up' : 'stock-down'}>{pct(v)}</span> },
    { title: '最新价', dataIndex: 'price', width: 85, render: (v: number | null) => v?.toFixed(2) ?? '—' },
    { title: '成交额', dataIndex: 'amount', width: 105, render: money },
    { title: '换手', dataIndex: 'turnover_rate', width: 82, render: pct },
  ]

  return <Space direction="vertical" size={16} style={{ width: '100%' }}>
    <Card>
      <div className="sector-toolbar-row">
        <Space wrap>
          <Segmented value={kind} options={[{ label: '行业板块', value: 'industry' }, { label: '概念板块', value: 'concept' }]} onChange={v => setKind(v as SectorKind)} />
          <Button icon={<ReloadOutlined spin={refreshing} />} loading={refreshing} onClick={() => void load(true)}>立即刷新</Button>
        </Space>
        <Space wrap>
          <Tag color={data?.ai.configured ? 'purple' : 'default'} icon={<RobotOutlined />}>DeepSeek：{data?.ai.configured ? '已参与复核' : '仅量化'}</Tag>
          <Tag color={data?.meta.is_cached ? 'gold' : 'cyan'}>{data?.meta.is_cached ? '缓存行情' : '实时检查'}</Tag>
        </Space>
      </div>
      {data && <Typography.Text type="secondary">数据：{data.meta.source} · {data.meta.quote_time || data.meta.fetched_at} · 每 10 秒检查</Typography.Text>}
    </Card>
    {error && <Alert type="error" showIcon closable message={error} onClose={() => setError('')} />}
    <Spin spinning={loading}>
      {data && <>
        <Row gutter={[12, 12]}>
          <Col xs={12} md={6}><Card><Statistic title="覆盖板块" value={data.overview.total} /></Card></Col>
          <Col xs={12} md={6}><Card><Statistic title="上涨 / 下跌" value={`${data.overview.rising} / ${data.overview.falling}`} /></Card></Col>
          <Col xs={12} md={6}><Card><Statistic title="最强板块" value={data.overview.strongest ?? '—'} /></Card></Col>
          <Col xs={12} md={6}><Card><Statistic title="主力净流入" value={money(data.overview.net_inflow)} /></Card></Col>
        </Row>
        <div className="sector-chart-grid">
          <Card title="市场板块热力图" extra="红涨绿跌 · 点击下钻"><ReactECharts option={treemap} style={{ height: 410 }} onEvents={{ click: (p: { name?: string }) => p.name && void openSector(p.name) }} /></Card>
          <Card title="综合强度排名"><ReactECharts option={strength} style={{ height: 410 }} /></Card>
          <Card title="资金流入流出"><ReactECharts option={flow} style={{ height: 350 }} /></Card>
          <Card title="市场方向分布"><ReactECharts style={{ height: 350 }} option={{ tooltip: { trigger: 'item' }, legend: { bottom: 8, textStyle: { color: '#9fb0c6' } }, series: [{ type: 'pie', radius: ['42%', '68%'], data: [{ name: '上涨', value: data.overview.rising, itemStyle: { color: red } }, { name: '下跌', value: data.overview.falling, itemStyle: { color: green } }, { name: '平盘', value: Math.max(0, data.overview.total - data.overview.rising - data.overview.falling), itemStyle: { color: '#72829c' } }] }] }} /></Card>
        </div>
        <Card title={`${data.label}实时排名`} extra="点击板块名称查看核心股与情绪标的">
          <Table rowKey={x => `${x.kind}-${x.name}`} columns={columns} dataSource={data.items} pagination={{ pageSize: 15, showSizeChanger: false }} scroll={{ x: 1080 }} size="small" />
        </Card>
        <Alert type="info" showIcon message={data.ifind.message || '当前使用东方财富 / AKShare'} description="同花顺 iFinD 需要独立 QuantAPI access token；DeepSeek 密钥不能替代行情授权。" />
      </>}
    </Spin>
    <Drawer title={selected ? `${selected} · 板块详情` : '板块详情'} open={Boolean(selected)} width={860} onClose={() => setSelected('')}>
      <Spin spinning={detailLoading}>{detail && <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Alert type={detail.sector.recommendation === '买入关注' ? 'success' : 'warning'} showIcon message={`当前建议：${detail.sector.ai_view?.action || detail.sector.recommendation}`} description={detail.sector.ai_view?.reason || detail.sector.reasons.join('；')} />
        <Typography.Paragraph>{detail.description}</Typography.Paragraph>
        <Descriptions bordered size="small" column={{ xs: 1, sm: 2, md: 3 }}>
          <Descriptions.Item label="综合强度">{detail.sector.combined_score ?? detail.sector.strength}</Descriptions.Item><Descriptions.Item label="板块热度">{detail.sector.heat}</Descriptions.Item><Descriptions.Item label="涨跌">{pct(detail.sector.change_pct)}</Descriptions.Item>
          <Descriptions.Item label="上涨广度">{pct(detail.sector.breadth)}</Descriptions.Item><Descriptions.Item label="主力净流入">{money(detail.sector.main_net_inflow)}</Descriptions.Item><Descriptions.Item label="成分股">{detail.breadth.total} 只</Descriptions.Item>
        </Descriptions>
        <Row gutter={[12, 12]}>
          <Col xs={24} md={12}><Card size="small" title="核心股票 · 成交活跃"><List dataSource={detail.core_stocks} renderItem={x => <List.Item actions={[<Button key="d" type="link" onClick={() => onOpenStock(x.code)}>看详情</Button>]}><List.Item.Meta title={`${x.name} ${x.code}`} description={`${pct(x.change_pct)} · ${money(x.amount)}`} /></List.Item>} /></Card></Col>
          <Col xs={24} md={12}><Card size="small" title="情绪标的 · 涨幅领先"><List dataSource={detail.sentiment_stocks} renderItem={x => <List.Item actions={[<Button key="d" type="link" onClick={() => onOpenStock(x.code)}>看详情</Button>]}><List.Item.Meta title={`${x.name} ${x.code}`} description={`${pct(x.change_pct)} · 换手 ${pct(x.turnover_rate)}`} /></List.Item>} /></Card></Col>
        </Row>
        <Card size="small" title="全部可用成分股"><Table rowKey="code" size="small" columns={stockColumns} dataSource={detail.members} pagination={{ pageSize: 10, showSizeChanger: false }} scroll={{ x: 600 }} /></Card>
      </Space>}</Spin>
    </Drawer>
  </Space>
}
