import { ClockCircleOutlined, SyncOutlined } from '@ant-design/icons'
import { Button, Card, Segmented, Space, Typography } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import DataState from '../components/DataState'
import Disclaimer from '../components/Disclaimer'
import OpportunityTable from '../components/OpportunityTable'
import { formatTime } from '../format'
import type { Opportunity, ScoreMode } from '../types'

export default function Ranking({ onOpenStock }: { onOpenStock: (code: string) => void }) {
  const [mode, setMode] = useState<ScoreMode>('short')
  const [items, setItems] = useState<Opportunity[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setItems(await api.opportunities(mode, 100))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '评分榜获取失败')
    } finally {
      setLoading(false)
    }
  }, [mode])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="page-stack">
      <div className="page-toolbar">
        <Segmented
          value={mode}
          onChange={(value) => setMode(value as ScoreMode)}
          options={[
            { label: '短线评分榜', value: 'short' },
            { label: '波段评分榜', value: 'swing' },
          ]}
        />
        <Button icon={<SyncOutlined />} onClick={() => void load()} loading={loading}>
          刷新榜单
        </Button>
      </div>
      <Card
        className="content-card"
        title={mode === 'short' ? '短线综合评分 Top 100' : '波段综合评分 Top 100'}
        extra={
          items[0] && (
            <Typography.Text type="secondary">
              <ClockCircleOutlined /> {formatTime(items[0].meta.fetched_at)}
            </Typography.Text>
          )
        }
      >
        <DataState
          loading={loading}
          error={error}
          empty={!loading && !error && !items.length}
          onRetry={() => void load()}
        >
          <OpportunityTable
            items={items}
            onOpenStock={onOpenStock}
            scoreLabel={mode === 'short' ? '短线分' : '波段分'}
          />
        </DataState>
      </Card>
      <Disclaimer />
    </div>
  )
}
