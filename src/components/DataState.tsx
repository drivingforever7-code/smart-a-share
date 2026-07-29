import { Alert, Button, Empty, Result, Space, Typography } from 'antd'
import LoadingExperience from './LoadingExperience'

interface DataStateProps {
  loading?: boolean
  error?: string | null
  empty?: boolean
  emptyText?: string
  onRetry?: () => void
  children: React.ReactNode
}

export default function DataState({
  loading,
  error,
  empty,
  emptyText = '暂时没有符合条件的数据',
  onRetry,
  children,
}: DataStateProps) {
  if (loading) {
    return (
      <div className="state-card">
        <LoadingExperience
          label="正在读取量化数据"
          detail="正在同步行情、评分与风险状态"
          rows={6}
        />
      </div>
    )
  }

  if (error) {
    return (
      <Result
        status="warning"
        title="数据暂时没有准备好"
        subTitle={error}
        extra={
          <Space direction="vertical">
            {onRetry && (
              <Button type="primary" onClick={onRetry}>
                重新获取
              </Button>
            )}
            <Typography.Text type="secondary">
              免费行情偶尔会延迟或中断，系统不会用模拟数据替代。
            </Typography.Text>
          </Space>
        }
      />
    )
  }

  if (empty) {
    return <Empty description={emptyText} />
  }

  return <>{children}</>
}

export function DataNotice({
  cached,
  text,
}: {
  cached?: boolean
  text: string
}) {
  return (
    <Alert
      type={cached ? 'warning' : 'info'}
      showIcon
      message={cached ? '当前展示缓存数据' : '数据时间'}
      description={text}
      className="data-notice"
    />
  )
}
