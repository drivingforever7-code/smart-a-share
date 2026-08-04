import { DeleteOutlined, ShoppingOutlined, SyncOutlined } from '@ant-design/icons'
import { Button, Card, Empty, Space, Table, Tag, Typography } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import DataState from '../components/DataState'
import Disclaimer from '../components/Disclaimer'
import { changeClass, formatNumber, formatPercent } from '../format'
import { getPurchasedStocks, removePurchasedStock, type PurchasedStock } from '../storage'
import type { Opportunity } from '../types'

export default function Watchlist({ onOpenStock }: { onOpenStock: (code: string) => void }) {
  const [records, setRecords] = useState<PurchasedStock[]>(getPurchasedStocks)
  const [items, setItems] = useState<Opportunity[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    const current = getPurchasedStocks()
    setRecords(current)
    if (!current.length) { setItems([]); return }
    setLoading(true)
    try {
      const results = await Promise.all(current.map((record) =>
        api.searchStocks(record.code).then((rows) => rows.find((row) => row.code === record.code))))
      setItems(results.filter((item): item is Opportunity => Boolean(item)))
      setError(null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '已购入行情获取失败')
    } finally { setLoading(false) }
  }, [])

  useEffect(() => {
    void load()
    const listener = () => void load()
    window.addEventListener('purchased-change', listener)
    return () => window.removeEventListener('purchased-change', listener)
  }, [load])

  const rows = useMemo(() => records.map((record) => ({
    ...record,
    quote: items.find((item) => item.code === record.code),
  })), [items, records])

  return <div className="page-stack">
    <Card className="content-card" title={`已购入（${records.length}）`}
      extra={<Button icon={<SyncOutlined />} onClick={() => void load()}>刷新行情</Button>}>
      {!records.length ? <Empty image={<ShoppingOutlined className="empty-star" />}
        description="还没有标记已购入股票，可在自动回测列表中点击“已购入”" /> :
        <DataState loading={loading} error={error} empty={!rows.length} onRetry={() => void load()}>
          <Table rowKey="code" size="small" pagination={false} dataSource={rows} columns={[
            { title: '股票', render: (_, row) => <button className="stock-link" onClick={() => onOpenStock(row.code)}><strong>{row.quote?.name || row.name || row.code}</strong><span>{row.code}</span></button> },
            { title: '买入日期', dataIndex: 'buyDate', render: (value) => value || '--' },
            { title: '买入价', dataIndex: 'buyPrice', render: (value) => formatNumber(value) },
            { title: '现价', render: (_, row) => formatNumber(row.quote?.price) },
            { title: '实际收益', render: (_, row) => {
              const value = row.buyPrice && row.quote?.price ? (row.quote.price / row.buyPrice - 1) * 100 : null
              return <strong className={changeClass(value)}>{formatPercent(value, true)}</strong>
            } },
            { title: '当前建议', render: (_, row) => <Tag>{row.quote?.recommendation || '--'}</Tag> },
            { title: '操作', render: (_, row) => <Space><Button type="link" onClick={() => onOpenStock(row.code)}>详情</Button><Button danger type="text" icon={<DeleteOutlined />} onClick={() => removePurchasedStock(row.code)}>取消购入</Button></Space> },
          ]} />
        </DataState>}
    </Card>
    <Typography.Text type="secondary">记录仅保存在当前浏览器，公共网站其他访问者不可见。</Typography.Text>
    <Disclaimer />
  </div>
}
