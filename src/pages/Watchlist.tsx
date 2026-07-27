import { StarOutlined, SyncOutlined } from '@ant-design/icons'
import { Button, Card, Empty, Typography } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import DataState from '../components/DataState'
import Disclaimer from '../components/Disclaimer'
import OpportunityTable from '../components/OpportunityTable'
import { getWatchlist } from '../storage'
import type { Opportunity } from '../types'

export default function Watchlist({ onOpenStock }: { onOpenStock: (code: string) => void }) {
  const [codes, setCodes] = useState(getWatchlist)
  const [items, setItems] = useState<Opportunity[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    const currentCodes = getWatchlist()
    setCodes(currentCodes)
    if (!currentCodes.length) {
      setItems([])
      return
    }
    setLoading(true)
    setError(null)
    try {
      const results = await Promise.all(
        currentCodes.map((code) =>
          api.searchStocks(code).then((matches) => matches.find((item) => item.code === code)),
        ),
      )
      setItems(results.filter((item): item is Opportunity => Boolean(item)))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '自选行情获取失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
    const listener = () => void load()
    window.addEventListener('watchlist-change', listener)
    return () => window.removeEventListener('watchlist-change', listener)
  }, [load])

  return (
    <div className="page-stack">
      <Card
        className="content-card"
        title={`我的自选（${codes.length}）`}
        extra={<Button icon={<SyncOutlined />} onClick={() => void load()}>刷新行情</Button>}
      >
        {!codes.length ? (
          <Empty
            image={<StarOutlined className="empty-star" />}
            description={
              <>
                <Typography.Title level={4}>还没有添加自选股</Typography.Title>
                <Typography.Text type="secondary">
                  在今日机会、筛选结果或股票详情中点击星标即可加入。
                </Typography.Text>
              </>
            }
          />
        ) : (
          <DataState
            loading={loading}
            error={error}
            empty={!items.length}
            onRetry={() => void load()}
          >
            <OpportunityTable items={items} onOpenStock={onOpenStock} scoreLabel="短线分" />
          </DataState>
        )}
      </Card>
      <Disclaimer />
    </div>
  )
}
