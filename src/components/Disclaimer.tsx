import { InfoCircleOutlined } from '@ant-design/icons'

export default function Disclaimer() {
  return (
    <div className="disclaimer">
      <InfoCircleOutlined />
      <span>
        量化结果仅基于历史和当前公开数据，不保证未来表现。建议买入是规则信号，不代表收益承诺，投资决策和风险由用户自行承担。
      </span>
    </div>
  )
}
