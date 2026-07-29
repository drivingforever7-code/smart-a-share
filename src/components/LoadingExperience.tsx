import { Skeleton } from 'antd'

type LoadingExperienceProps = {
  label?: string
  detail?: string
  compact?: boolean
  fullscreen?: boolean
  rows?: number
}

export default function LoadingExperience({
  label = '正在同步市场数据',
  detail = '正在校验数据源、行情时间与缓存状态',
  compact = false,
  fullscreen = false,
  rows = 5,
}: LoadingExperienceProps) {
  const className = [
    'loading-experience',
    compact ? 'loading-experience--compact' : '',
    fullscreen ? 'loading-experience--fullscreen' : '',
  ].filter(Boolean).join(' ')

  return (
    <div className={className} role="status" aria-live="polite">
      <div className="loading-visual" aria-hidden="true">
        <span className="loading-orbit loading-orbit--outer" />
        <span className="loading-orbit loading-orbit--inner" />
        <span className="loading-radar" />
        <span className="loading-core-dot" />
        <span className="loading-ping loading-ping--one" />
        <span className="loading-ping loading-ping--two" />
        <span className="loading-ping loading-ping--three" />
      </div>

      <div className="loading-copy">
        <span className="loading-eyebrow">QUANT DATA LINK</span>
        <strong>{label}</strong>
        <span>{detail}</span>
      </div>

      {!compact && (
        <>
          <div className="loading-traces" aria-hidden="true">
            <span />
            <span />
            <span />
            <span />
          </div>
          <Skeleton active title={false} paragraph={{ rows }} />
        </>
      )}
    </div>
  )
}
