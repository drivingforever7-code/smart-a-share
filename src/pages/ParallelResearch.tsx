import { useEffect, useRef, useState } from 'react'
import { Alert, Button, Card, Col, Collapse, Empty, Progress, Row, Segmented, Select, Space, Table, Tag, Typography } from 'antd'
import ReactECharts from 'echarts-for-react'
import { api } from '../api'
import type { Opportunity, ScoreMode } from '../types'
import type { ParallelResearchData, ResearchStock } from '../parallelResearchTypes'

const pct = (n: number | null | undefined) => n == null ? '待观察' : `${n > 0 ? '+' : ''}${n.toFixed(2)}%`
const reasonNames: Record<string, string> = { trend_or_time: '持有期满', stop: '止损或移动止损', take: '止盈', gap_stop: '跳空止损', gap_take: '跳空止盈', trailing: '移动止损' }

export default function ParallelResearch({ onOpenStock }: { onOpenStock: (code: string) => void }) {
  const [mode, setMode] = useState<ScoreMode>(() => sessionStorage.getItem('parallel-mode') === 'swing' ? 'swing' : 'short')
  const [period, setPeriod] = useState<'holdout' | 'year'>('holdout')
  const [data, setData] = useState<ParallelResearchData | null>(null)
  const [error, setError] = useState('')
  const [date, setDate] = useState<string>()
  const [old, setOld] = useState<Opportunity[] | null>(null)
  const [oldError, setOldError] = useState('')
  const [oldLoading, setOldLoading] = useState(false)
  const oldRequest = useRef(0)
  const [refreshing, setRefreshing] = useState(false)

  useEffect(() => {
    let active = true
    setData(null); setDate(undefined); setOld(null); setOldError(''); setOldLoading(false); oldRequest.current += 1
    sessionStorage.setItem('parallel-mode', mode)
    const load = () => { void api.parallelResearch(mode, period).then(value => {
      if (active) { setData(value); setError('') }
    }).catch(e => { if (active) setError(String(e.message || e)) }) }
    load()
    const poll = window.setInterval(load, 10000)
    return () => { active = false; window.clearInterval(poll) }
  }, [mode, period])

  useEffect(() => {
    const update = () => { void api.refreshParallelResearch().catch(() => undefined) }
    update()
    const timer = window.setInterval(update, 300000)
    return () => window.clearInterval(timer)
  }, [])

  const refresh = async () => {
    setRefreshing(true)
    try { await api.refreshParallelResearch(); setData(await api.parallelResearch(mode, period)); setError('') }
    catch (e) { setError(String(e)) }
    finally { setRefreshing(false) }
  }
  const loadOld = async () => {
    const request = ++oldRequest.current
    setOldLoading(true); setOldError('')
    try { const result = await api.opportunities(mode); if (request === oldRequest.current) setOld(result) }
    catch (e) { if (request === oldRequest.current) setOldError(String(e)) }
    finally { if (request === oldRequest.current) setOldLoading(false) }
  }
  const columns = [
    { title: '股票', key: 'stock', render: (_: unknown, row: ResearchStock) => <Button type="link" onClick={() => onOpenStock(row.code)}>{row.name} {row.code}</Button> },
    { title: '信号价格', dataIndex: 'price', render: (v: number) => v?.toFixed(2) ?? '—' },
    { title: '评分', dataIndex: 'score', render: (v: number) => v?.toFixed(1) ?? '—' },
  ]
  const table = (items: ResearchStock[], tracking = false) => <Table size="small" rowKey="code" dataSource={items}
    columns={tracking ? [...columns, { title: '收盘跟踪涨跌', dataIndex: 'tracking_return_pct', render: pct }] : columns}
    pagination={false} scroll={{ x: 500 }} locale={{ emptyText: '没有符合条件的候选，不补足数量' }}
    expandable={tracking ? { expandedRowRender: (row: ResearchStock) => <Space direction="vertical">
      <span>行情时间：{row.quote_time} · 置信度：{row.confidence}</span>
      <span>依据：{row.reasons?.join('；')}</span><span>风险：{row.risks?.join('；') || '仍存在市场波动与执行风险'}</span>
    </Space> } : undefined} />
  const selected = data?.history.find(item => item.date === date) ?? data?.history[0]
  const candidate = data?.research.candidate
  const baseline = data?.research.baseline

  return <Space direction="vertical" size={20} style={{ width: '100%' }}>
    <Alert type="info" showIcon message="新方案已独立试运行 · 旧方案继续保留" description="没有最低推荐数量。市场、个股或数据不达标时允许空榜；最多三只是研究上限，不是每日任务。这里不执行真实交易。" />
    <Space wrap>
      <Segmented value={mode} onChange={v => setMode(v as ScoreMode)} options={[{ label: '短线', value: 'short' }, { label: '波段', value: 'swing' }]} />
      <Button onClick={refresh} loading={refreshing || data?.state.running}>更新收盘研究</Button>
      <Tag color="cyan">{data?.policy.name ?? '加载方案'}</Tag>
    </Space>
    {error && <Alert type="error" showIcon message="研究数据读取失败" description={error} />}
    {!data && !error && <Card loading />}
    {data && <>
      <Card title="收盘信号与后续观察" extra={data.latest_date ? <Tag>{data.latest_date}</Tag> : <Tag>等待首个收盘快照</Tag>}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Typography.Text>{data.state.message}</Typography.Text>
          {data.state.running && <Progress percent={data.state.total ? Math.round(100 * data.state.completed / data.state.total) : 0} status="active" />}
          {data.state.error && <Alert type="warning" message={data.state.error} />}
          {selected ? <>
            <Select aria-label="研究日期" value={selected.date} onChange={setDate} style={{ width: 180 }} options={data.history.map(h => ({ label: h.date, value: h.date }))} />
            <Alert type="info" message={`${selected.date} 收盘信号${selected.date !== data.today ? '（历史记录，不是当前买入建议）' : '，仅供下一交易日条件核验'}`} />
            <Typography.Text>同日日线覆盖 {(selected.market.coverage * 100).toFixed(1)}% · 上涨占比 {(selected.market.rising_ratio * 100).toFixed(1)}% · 站上20日均线 {(selected.market.above20_ratio * 100).toFixed(1)}%</Typography.Text>
            <Row gutter={[16, 16]} style={{ width: '100%' }}>
              <Col xs={24} xl={12}><Card size="small" title={`新方案 · ${selected.items.length} 只`}>{table(selected.items, true)}
                {selected.reasons.map(r => <Typography.Paragraph key={r} type="secondary">{r}</Typography.Paragraph>)}
              </Card></Col>
              <Col xs={24} xl={12}><Card size="small" title="旧网站 · 同次保存的实际机会榜">{table(selected.old_items, true)}
                {selected.old_note && <Alert type="warning" message={selected.old_note} />}
              </Card></Col>
            </Row>
            <Typography.Text type="secondary">跟踪涨跌使用信号收盘至最新已保存收盘，复权等值处理公司行动；未假设成交、未扣费用。首次收盘尚无后续结果时显示待观察。</Typography.Text>
          </> : <Empty description="还没有启用后的收盘候选。盘中不冻结排名，15:05后核验；没有合格股票也会保存空榜原因。" />}
          <Collapse items={[{ key: 'seed', label: `查看 ${data.seed.date} 历史重建信号`, children: <Space direction="vertical" style={{ width: '100%' }}>
            <Alert type="warning" message={data.seed.note} />{table(data.seed.items)}
          </Space> }]} />
        </Space>
      </Card>
      <Card title="旧网站当前机会榜" extra={<Button onClick={loadOld} loading={oldLoading}>读取旧方案</Button>}>
        <Typography.Paragraph type="secondary">直接读取原今日机会。盘中结果与新方案收盘信号时间可能不同，不能当作同一时点的收益对比。</Typography.Paragraph>
        {oldError && <Alert type="error" message={oldError} />}
        {old ? <>{table(old)}<Typography.Text type="secondary">行情时间：{[...new Set(old.map(i => i.meta.quote_time || '未提供'))].join('、') || '无合格候选'}</Typography.Text></> : <Typography.Text>点击“读取旧方案”查看原榜单。</Typography.Text>}
      </Card>
      <Card title="历史组合表现对比" extra={<Segmented value={period} onChange={v => setPeriod(v as 'holdout' | 'year')} options={[{ label: '最后验证期', value: 'holdout' }, { label: '全年回放', value: 'year' }]} />}>
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Alert type={period === 'year' ? 'warning' : 'info'} message={period === 'year' ? '2025-09-05 至 2026-09-04 · 包含调参区间，不能视为全部样本外收益' : '2026-06-01 至 2026-09-04 · 选择参数时保留的最后验证期'} description="这里的旧基准为日线技术重建，并非旧网站完整荐股。收益为含费用组合收益，不是个股平均涨幅。" />
          <Table size="small" pagination={false} scroll={{ x: 660 }} rowKey="name" dataSource={[
            { name: '旧技术基准', ...baseline!.metrics }, { name: '新研究方案', ...candidate!.metrics },
          ]} columns={[
            { title: '方案', dataIndex: 'name' }, { title: '扣费组合收益', dataIndex: 'net_return_pct', render: pct },
            { title: '最大回撤', dataIndex: 'max_drawdown_pct', render: pct }, { title: '平仓胜率', dataIndex: 'win_rate_pct', render: (v: number) => `${v.toFixed(2)}%` },
            { title: '已平仓笔数', dataIndex: 'closed_trades' },
            { title: '持仓天数', key: 'exposure', render: (_, r) => `${r.invested_days}/${r.days}` },
          ]} />
          <Typography.Text>同期沪深300价格指数：{pct(data.research.benchmark.price_return_pct)}。新方案减少交易也是回撤下降的原因。</Typography.Text>
          <ReactECharts style={{ height: 320 }} option={{ tooltip: { trigger: 'axis', valueFormatter: (v: number) => pct(v) }, legend: { data: ['新研究方案', '旧技术基准'], textStyle: { color: '#9caec5' } },
            grid: { left: 60, right: 24, top: 40, bottom: 40 }, xAxis: { type: 'category', data: candidate!.equity.map(e => e.date) }, yAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
            series: [{ name: '新研究方案', type: 'line', showSymbol: false, data: candidate!.equity.map(e => +(100 * (e.equity / 1000000 - 1)).toFixed(3)), itemStyle: { color: '#27b8c8' } },
              { name: '旧技术基准', type: 'line', showSymbol: false, data: baseline!.equity.map(e => +(100 * (e.equity / 1000000 - 1)).toFixed(3)), itemStyle: { color: '#e5a75b' } }] }} />
          <Collapse items={[{ key: 'trades', label: '查看新方案已平仓交易', children: <Table size="small" rowKey={r => `${r.symbol}-${r.entry_date}`} dataSource={candidate!.trades} pagination={{ pageSize: 10 }} scroll={{ x: 760 }} columns={[
            { title: '股票', dataIndex: 'symbol', render: (v: string) => <Button type="link" onClick={() => onOpenStock(v.slice(2))}>{v.slice(2)}</Button> },
            { title: '信号日期', dataIndex: 'signal_date' }, { title: '买入日期', dataIndex: 'entry_date' }, { title: '卖出日期', dataIndex: 'exit_date' },
            { title: '买入价', dataIndex: 'entry_price', render: (v: number) => v.toFixed(3) }, { title: '卖出价', dataIndex: 'exit_price', render: (v: number) => v.toFixed(3) },
            { title: '扣费收益', dataIndex: 'return_pct', render: pct }, { title: '退出原因', dataIndex: 'reason', render: (v: string) => reasonNames[v] || v },
          ]} /> }]} />
        </Space>
      </Card>
      <Card title="入选与失效条件">
        <Typography.Paragraph>两项市场广度均不低于45%，技术分不低于70，成交额至少3000万元，日涨跌幅绝对值小于7%，历史与波动数据合格；同日收盘价格需核对一致，并通过现有线上风险、评分及置信度检查。</Typography.Paragraph>
        <Typography.Paragraph>按下一交易日开盘研究，高开超过信号收盘价3%、停牌或涨停无法买入时跳过；遵守T+1。参考单股仓位上限10%，组合最多10个持仓，不要求满仓。</Typography.Paragraph>
        <Typography.Paragraph>{mode === 'short' ? '短线持有期上限5个交易日；初始止损为入场价下方2倍ATR、移动止损距离2.5倍ATR、止盈距离4倍ATR，持有期满亦退出。ATR代表近期价格波动幅度。遇到无法成交时可能延迟退出。' : '波段持有期上限15个交易日，到期退出；冻结的波段方案未设置ATR止损或趋势转弱提前退出，不应把短线止损规则视为波段回测的一部分。遇到无法成交时可能延迟退出。'}</Typography.Paragraph>
        {data.limitations.map(note => <Typography.Paragraph key={note} type="secondary">{note}</Typography.Paragraph>)}
        <Typography.Text type="secondary">量化结果仅基于历史和当前公开数据，不保证未来表现，投资决策和风险由用户自行承担。</Typography.Text>
      </Card>
    </>}
  </Space>
}
