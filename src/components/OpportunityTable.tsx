import { EyeOutlined, StarFilled, StarOutlined } from '@ant-design/icons'
import { Button, Space, Table, Tag, Tooltip, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useEffect, useState } from 'react'
import { changeClass, formatAmount, formatNumber, formatPercent } from '../format'
import { getWatchlist, toggleWatchlist } from '../storage'
import type { Opportunity } from '../types'
import { RecommendationTag, ScoreBadge } from './ScoreBadge'

interface OpportunityTableProps {
  items: Opportunity[]
  onOpenStock: (code: string) => void
  loading?: boolean
  pagination?: false | { current: number; pageSize: number; total: number; onChange: (page: number, pageSize: number) => void }
  scoreLabel?: string
}

export default function OpportunityTable({
  items,
  onOpenStock,
  loading,
  pagination = false,
  scoreLabel = '评分',
}: OpportunityTableProps) {
  const [watchlist, setWatchlist] = useState(getWatchlist)

  useEffect(() => {
    const listener = () => setWatchlist(getWatchlist())
    window.addEventListener('watchlist-change', listener)
    return () => window.removeEventListener('watchlist-change', listener)
  }, [])

  const columns: ColumnsType<Opportunity> = [
    {
      title: '股票',
      key: 'stock',
      fixed: 'left',
      width: 150,
      render: (_, item) => (
        <button className="stock-link" onClick={() => onOpenStock(item.code)}>
          <strong>{item.name}</strong>
          <span>{item.code} · {item.board}</span>
        </button>
      ),
    },
    {
      title: '最新价',
      dataIndex: 'price',
      width: 92,
      align: 'right',
      render: (value: number | null, item) => (
        <span className={changeClass(item.change_pct)}>{formatNumber(value)}</span>
      ),
    },
    {
      title: '涨跌幅',
      dataIndex: 'change_pct',
      width: 92,
      align: 'right',
      sorter: (a, b) => (a.change_pct ?? 0) - (b.change_pct ?? 0),
      render: (value: number | null) => (
        <strong className={changeClass(value)}>{formatPercent(value, true)}</strong>
      ),
    },
    {
      title: scoreLabel,
      dataIndex: 'score',
      width: 82,
      align: 'center',
      sorter: (a, b) => a.score - b.score,
      render: (value: number) => <ScoreBadge score={value} compact />,
    },
    {
      title: '系统建议',
      dataIndex: 'recommendation',
      width: 132,
      render: (value) => <RecommendationTag value={value} />,
    },
    {
      title: '量比',
      dataIndex: 'volume_ratio',
      width: 74,
      align: 'right',
      render: (value) => formatNumber(value),
    },
    {
      title: '换手率',
      dataIndex: 'turnover_rate',
      width: 88,
      align: 'right',
      render: (value) => formatPercent(value),
    },
    {
      title: '成交额',
      dataIndex: 'amount',
      width: 105,
      align: 'right',
      render: (value) => formatAmount(value),
    },
    {
      title: '入选依据',
      dataIndex: 'reasons',
      width: 260,
      render: (reasons: string[]) => (
        <Space size={[4, 4]} wrap>
          {reasons.slice(0, 2).map((reason) => (
            <Tag key={reason} className="reason-tag">{reason}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '风险',
      dataIndex: 'risks',
      width: 180,
      render: (risks: string[]) =>
        risks.length ? (
          <Typography.Text type="warning">{risks[0]}</Typography.Text>
        ) : (
          <Typography.Text type="secondary">未发现突出风险</Typography.Text>
        ),
    },
    {
      title: '操作',
      key: 'actions',
      fixed: 'right',
      width: 100,
      render: (_, item) => {
        const watched = watchlist.includes(item.code)
        return (
          <Space>
            <Tooltip title={watched ? '移出自选' : '加入自选'}>
              <Button
                type="text"
                icon={watched ? <StarFilled className="star-active" /> : <StarOutlined />}
                onClick={() => setWatchlist(toggleWatchlist(item.code))}
              />
            </Tooltip>
            <Tooltip title="查看详情">
              <Button type="text" icon={<EyeOutlined />} onClick={() => onOpenStock(item.code)} />
            </Tooltip>
          </Space>
        )
      },
    },
  ]

  return (
    <Table
      rowKey="code"
      columns={columns}
      dataSource={items}
      loading={loading}
      pagination={pagination}
      scroll={{ x: 1500 }}
      size="middle"
      className="opportunity-table"
    />
  )
}
