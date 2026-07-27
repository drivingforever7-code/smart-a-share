import { Progress, Tag, Tooltip } from 'antd'
import { recommendationColor } from '../format'
import type { Recommendation } from '../types'

export function ScoreBadge({ score, compact = false }: { score: number; compact?: boolean }) {
  const strokeColor = score >= 80 ? '#d92d20' : score >= 70 ? '#f79009' : score >= 60 ? '#175cd3' : '#98a2b3'
  if (compact) {
    return (
      <span className="score-compact" style={{ color: strokeColor }}>
        {Math.round(score)}
      </span>
    )
  }
  return (
    <Tooltip title="综合评分满分 100，分数越高表示当前规则匹配度越高">
      <Progress
        type="circle"
        size={56}
        percent={Math.round(score)}
        strokeColor={strokeColor}
        format={(value) => <strong>{value}</strong>}
      />
    </Tooltip>
  )
}

export function RecommendationTag({ value }: { value: Recommendation }) {
  return <Tag color={recommendationColor(value)}>{value}</Tag>
}
