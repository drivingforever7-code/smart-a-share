import DailyAlert from '../components/DailyAlert'
import {
  CopyOutlined,
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
  SaveOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Empty,
  Input,
  InputNumber,
  List,
  Popconfirm,
  Radio,
  Row,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import type {
  CompositeStrategyConfig,
  RiskConfig,
  RuleStrategyConfig,
  StrategyCatalog,
  StrategyCondition,
  StrategyDefinition,
  StrategyPayload,
} from '../strategyTypes'

const defaultRisk: RiskConfig = {
  stop_loss_pct: 7,
  take_profit_pct: 15,
  max_holding_days: 10,
  commission_pct: 0.1,
  slippage_pct: 0.05,
  stamp_duty_pct: 0.05,
}

const newCondition = (): StrategyCondition => ({
  left: 'close',
  operator: 'gt',
  right_type: 'indicator',
  right: 'ma20',
})

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T

function createDraft(
  category: 'rule' | 'composite',
  ruleStrategies: StrategyDefinition[],
): StrategyPayload {
  if (category === 'rule') {
    return {
      name: '我的新策略',
      category,
      mode: 'short',
      description: '用通俗的话说明这个策略适合什么情况',
      icon: '🧩',
      config: {
        entry_logic: 'all',
        entry_conditions: [newCondition()],
        exit_logic: 'any',
        exit_conditions: [
          { left: 'close', operator: 'cross_below', right_type: 'indicator', right: 'ma20' },
        ],
        risk: clone(defaultRisk),
      },
    }
  }
  const selected = ruleStrategies.slice(0, 2)
  return {
    name: '我的组合策略',
    category,
    mode: 'swing',
    description: '把多个策略按权重组合，达到触发分数才买入',
    icon: '⚖️',
    config: {
      components: selected.map((item) => ({
        strategy_id: item.id,
        weight: 50,
      })),
      trigger_score: 50,
      exit_score: 50,
      risk: clone(defaultRisk),
    },
  }
}

function RiskEditor({
  value,
  onChange,
}: {
  value: RiskConfig
  onChange: (value: RiskConfig) => void
}) {
  const fields: { key: keyof RiskConfig; label: string; suffix: string; min: number; max: number }[] = [
    { key: 'stop_loss_pct', label: '止损', suffix: '%', min: 0.1, max: 50 },
    { key: 'take_profit_pct', label: '止盈', suffix: '%', min: 0.1, max: 200 },
    { key: 'max_holding_days', label: '最长持有', suffix: '天', min: 1, max: 250 },
    { key: 'commission_pct', label: '单边费用', suffix: '%', min: 0, max: 2 },
    { key: 'slippage_pct', label: '单边滑点', suffix: '%', min: 0, max: 2 },
    { key: 'stamp_duty_pct', label: '卖出印花税', suffix: '%', min: 0, max: 2 },
  ]
  return (
    <Row gutter={[12, 12]}>
      {fields.map((field) => (
        <Col xs={12} lg={4} key={field.key}>
          <Typography.Text type="secondary">{field.label}</Typography.Text>
          <InputNumber
            value={value[field.key]}
            min={field.min}
            max={field.max}
            step={field.key === 'max_holding_days' ? 1 : 0.1}
            addonAfter={field.suffix}
            style={{ width: '100%', marginTop: 6 }}
            onChange={(next) =>
              onChange({ ...value, [field.key]: Number(next ?? field.min) })
            }
          />
        </Col>
      ))}
    </Row>
  )
}

function ConditionEditor({
  title,
  logic,
  conditions,
  catalog,
  onLogicChange,
  onChange,
}: {
  title: string
  logic: 'all' | 'any'
  conditions: StrategyCondition[]
  catalog: StrategyCatalog
  onLogicChange: (value: 'all' | 'any') => void
  onChange: (value: StrategyCondition[]) => void
}) {
  const update = (index: number, patch: Partial<StrategyCondition>) => {
    const next = clone(conditions)
    next[index] = { ...next[index], ...patch }
    onChange(next)
  }
  return (
    <div className="condition-editor">
      <div className="section-heading">
        <strong>{title}</strong>
        <Radio.Group
          size="small"
          value={logic}
          onChange={(event) => onLogicChange(event.target.value)}
          options={[
            { label: '全部满足', value: 'all' },
            { label: '任一满足', value: 'any' },
          ]}
        />
      </div>
      <Space direction="vertical" style={{ width: '100%' }} size={10}>
        {conditions.map((condition, index) => {
          const operator = catalog.operators.find((item) => item.id === condition.operator)
          return (
            <div className="condition-row" key={`${index}-${condition.left}`}>
              <span className="condition-index">{index + 1}</span>
              <Select
                showSearch
                value={condition.left}
                optionFilterProp="label"
                options={catalog.indicators.map((item) => ({
                  value: item.id,
                  label: `${item.group} · ${item.name}`,
                }))}
                onChange={(left) => update(index, { left })}
              />
              <Select
                value={condition.operator}
                options={catalog.operators.map((item) => ({
                  value: item.id,
                  label: item.name,
                }))}
                onChange={(nextOperator) => {
                  const isTrue = nextOperator === 'is_true'
                  const between = nextOperator === 'between'
                  update(index, {
                    operator: nextOperator as StrategyCondition['operator'],
                    right_type: between || isTrue ? 'value' : condition.right_type,
                    right: isTrue ? null : between ? [0, 10] : condition.right ?? 0,
                  })
                }}
              />
              {condition.operator !== 'is_true' && condition.operator !== 'between' && (
                <Select
                  value={condition.right_type}
                  options={[
                    { value: 'value', label: '固定数值' },
                    ...(operator?.supports_indicator
                      ? [{ value: 'indicator', label: '另一指标' }]
                      : []),
                  ]}
                  onChange={(rightType) =>
                    update(index, {
                      right_type: rightType,
                      right: rightType === 'indicator' ? 'ma20' : 0,
                    })
                  }
                />
              )}
              {condition.operator === 'between' ? (
                <Space.Compact>
                  <InputNumber
                    value={(condition.right as number[])?.[0]}
                    onChange={(value) =>
                      update(index, {
                        right: [Number(value ?? 0), (condition.right as number[])?.[1] ?? 0],
                      })
                    }
                  />
                  <Input disabled value="至" style={{ width: 44, textAlign: 'center' }} />
                  <InputNumber
                    value={(condition.right as number[])?.[1]}
                    onChange={(value) =>
                      update(index, {
                        right: [(condition.right as number[])?.[0] ?? 0, Number(value ?? 0)],
                      })
                    }
                  />
                </Space.Compact>
              ) : condition.operator === 'is_true' ? (
                <Tag color="blue">条件成立</Tag>
              ) : condition.right_type === 'indicator' ? (
                <Select
                  showSearch
                  optionFilterProp="label"
                  value={String(condition.right)}
                  options={catalog.indicators.map((item) => ({
                    value: item.id,
                    label: item.name,
                  }))}
                  onChange={(right) => update(index, { right })}
                />
              ) : (
                <InputNumber
                  value={Number(condition.right)}
                  onChange={(right) => update(index, { right: Number(right ?? 0) })}
                />
              )}
              <Button
                danger
                type="text"
                icon={<DeleteOutlined />}
                disabled={conditions.length <= (title === '买入条件' ? 1 : 0)}
                onClick={() => onChange(conditions.filter((_, itemIndex) => itemIndex !== index))}
              />
            </div>
          )
        })}
        <Button
          block
          type="dashed"
          icon={<PlusOutlined />}
          onClick={() => onChange([...conditions, newCondition()])}
        >
          添加一条{title}
        </Button>
      </Space>
    </div>
  )
}

export default function StrategyWorkshop() {
  const [strategies, setStrategies] = useState<StrategyDefinition[]>([])
  const [catalog, setCatalog] = useState<StrategyCatalog | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [draft, setDraft] = useState<StrategyPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [notice, contextHolder] = message.useMessage()

  const ruleStrategies = useMemo(
    () => strategies.filter((item) => item.category === 'rule'),
    [strategies],
  )

  const load = async (preferId?: string) => {
    setLoading(true)
    try {
      const [nextStrategies, nextCatalog] = await Promise.all([
        api.strategies(),
        api.strategyCatalog(),
      ])
      setStrategies(nextStrategies)
      setCatalog(nextCatalog)
      const id = preferId ?? selectedId ?? nextStrategies[0]?.id
      const current = nextStrategies.find((item) => item.id === id) ?? nextStrategies[0]
      setSelectedId(current?.id ?? null)
      setDraft(current ? clone(current) : null)
    } catch (reason) {
      notice.error(reason instanceof Error ? reason.message : '策略加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // 首次进入时加载一次。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const selectStrategy = (strategy: StrategyDefinition) => {
    setSelectedId(strategy.id)
    setDraft(clone(strategy))
  }

  const startCreate = (category: 'rule' | 'composite') => {
    setSelectedId(null)
    setDraft(createDraft(category, ruleStrategies))
  }

  const save = async () => {
    if (!draft) return
    setSaving(true)
    try {
      const saved = selectedId
        ? await api.updateStrategy(selectedId, draft)
        : await api.createStrategy(draft)
      notice.success('策略已保存')
      await load(saved.id)
    } catch (reason) {
      notice.error(reason instanceof Error ? reason.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const setRisk = (risk: RiskConfig) => {
    if (!draft) return
    setDraft({ ...draft, config: { ...draft.config, risk } })
  }

  const current = strategies.find((item) => item.id === selectedId)

  return (
    <Spin spinning={loading}>
      {contextHolder}
      <div className="page-stack">
        <DailyAlert noticeKey="strategyworkshop-1"
          type="info"
          showIcon
          message="这里不用写代码"
          description="你可以修改系统策略，也可以新建规则或组合策略。组合权重合计必须为 100%。保存后会立即出现在个股回测的策略选择中。"
        />
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={7} xl={6}>
            <Card
              title="策略库"
              extra={
                <Space>
                  <Button size="small" onClick={() => startCreate('rule')}>新建规则</Button>
                  <Button size="small" onClick={() => startCreate('composite')}>新建组合</Button>
                </Space>
              }
            >
              <List
                dataSource={strategies}
                locale={{ emptyText: <Empty description="还没有策略" /> }}
                renderItem={(item) => (
                  <List.Item
                    className={item.id === selectedId ? 'strategy-list-item active' : 'strategy-list-item'}
                    onClick={() => selectStrategy(item)}
                  >
                    <List.Item.Meta
                      avatar={<span className="strategy-icon">{item.icon}</span>}
                      title={
                        <Space>
                          {item.name}
                          {item.is_builtin && <Tag>内置</Tag>}
                        </Space>
                      }
                      description={`${item.mode === 'short' ? '短线' : '波段'} · ${
                        item.category === 'rule' ? '规则策略' : '组合策略'
                      }`}
                    />
                  </List.Item>
                )}
              />
            </Card>
          </Col>
          <Col xs={24} lg={17} xl={18}>
            {!draft || !catalog ? (
              <Card><Empty description="请选择或新建一个策略" /></Card>
            ) : (
              <Card
                title={selectedId ? `编辑：${draft.name}` : '创建新策略'}
                extra={
                  <Space wrap>
                    {current && (
                      <Button
                        icon={<CopyOutlined />}
                        onClick={async () => {
                          const copied = await api.copyStrategy(current.id)
                          notice.success('已创建副本')
                          await load(copied.id)
                        }}
                      >
                        复制
                      </Button>
                    )}
                    {current?.is_builtin && (
                      <Popconfirm
                        title="恢复默认参数？"
                        description="你对这个内置策略的修改会被覆盖。"
                        onConfirm={async () => {
                          await api.resetStrategy(current.id)
                          notice.success('已恢复默认参数')
                          await load(current.id)
                        }}
                      >
                        <Button icon={<ReloadOutlined />}>恢复默认</Button>
                      </Popconfirm>
                    )}
                    {current && !current.is_builtin && (
                      <Popconfirm
                        title="确定删除这个策略？"
                        onConfirm={async () => {
                          await api.deleteStrategy(current.id)
                          notice.success('策略已删除')
                          setSelectedId(null)
                          await load()
                        }}
                      >
                        <Button danger icon={<DeleteOutlined />}>删除</Button>
                      </Popconfirm>
                    )}
                    <Button
                      type="primary"
                      icon={<SaveOutlined />}
                      loading={saving}
                      onClick={() => void save()}
                    >
                      保存策略
                    </Button>
                  </Space>
                }
              >
                <Row gutter={[16, 16]}>
                  <Col xs={24} md={12}>
                    <Typography.Text type="secondary">策略名称</Typography.Text>
                    <Input
                      value={draft.name}
                      maxLength={60}
                      style={{ marginTop: 6 }}
                      onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                    />
                  </Col>
                  <Col xs={12} md={6}>
                    <Typography.Text type="secondary">适用周期</Typography.Text>
                    <Select
                      value={draft.mode}
                      style={{ width: '100%', marginTop: 6 }}
                      options={[
                        { value: 'short', label: '短线' },
                        { value: 'swing', label: '波段' },
                      ]}
                      onChange={(mode) => setDraft({ ...draft, mode })}
                    />
                  </Col>
                  <Col xs={12} md={6}>
                    <Typography.Text type="secondary">策略类型</Typography.Text>
                    <Select
                      value={draft.category}
                      disabled={Boolean(selectedId)}
                      style={{ width: '100%', marginTop: 6 }}
                      options={[
                        { value: 'rule', label: '规则策略' },
                        { value: 'composite', label: '组合策略' },
                      ]}
                    />
                  </Col>
                  <Col span={24}>
                    <Typography.Text type="secondary">策略说明</Typography.Text>
                    <Input.TextArea
                      value={draft.description}
                      rows={2}
                      maxLength={240}
                      showCount
                      style={{ marginTop: 6 }}
                      onChange={(event) => setDraft({ ...draft, description: event.target.value })}
                    />
                  </Col>
                </Row>

                <Divider />
                {draft.category === 'rule' ? (
                  <>
                    <ConditionEditor
                      title="买入条件"
                      logic={(draft.config as RuleStrategyConfig).entry_logic}
                      conditions={(draft.config as RuleStrategyConfig).entry_conditions}
                      catalog={catalog}
                      onLogicChange={(entry_logic) =>
                        setDraft({
                          ...draft,
                          config: { ...(draft.config as RuleStrategyConfig), entry_logic },
                        })
                      }
                      onChange={(entry_conditions) =>
                        setDraft({
                          ...draft,
                          config: { ...(draft.config as RuleStrategyConfig), entry_conditions },
                        })
                      }
                    />
                    <Divider />
                    <ConditionEditor
                      title="卖出条件"
                      logic={(draft.config as RuleStrategyConfig).exit_logic}
                      conditions={(draft.config as RuleStrategyConfig).exit_conditions}
                      catalog={catalog}
                      onLogicChange={(exit_logic) =>
                        setDraft({
                          ...draft,
                          config: { ...(draft.config as RuleStrategyConfig), exit_logic },
                        })
                      }
                      onChange={(exit_conditions) =>
                        setDraft({
                          ...draft,
                          config: { ...(draft.config as RuleStrategyConfig), exit_conditions },
                        })
                      }
                    />
                  </>
                ) : (
                  <CompositeEditor
                    value={draft.config as CompositeStrategyConfig}
                    strategies={ruleStrategies}
                    onChange={(config) => setDraft({ ...draft, config })}
                  />
                )}
                <Divider orientation="left">风险与交易参数</Divider>
                <RiskEditor value={draft.config.risk} onChange={setRisk} />
              </Card>
            )}
          </Col>
        </Row>
      </div>
    </Spin>
  )
}

function CompositeEditor({
  value,
  strategies,
  onChange,
}: {
  value: CompositeStrategyConfig
  strategies: StrategyDefinition[]
  onChange: (value: CompositeStrategyConfig) => void
}) {
  const total = value.components.reduce((sum, item) => sum + Number(item.weight), 0)
  const equalize = () => {
    const count = value.components.length
    if (!count) return
    const base = Math.floor((100 / count) * 100) / 100
    const components = value.components.map((item, index) => ({
      ...item,
      weight: index === count - 1 ? Number((100 - base * (count - 1)).toFixed(2)) : base,
    }))
    onChange({ ...value, components })
  }
  return (
    <div>
      <div className="section-heading">
        <Space>
          <strong>组合成员与权重</strong>
          <Tag color={Math.abs(total - 100) < 0.01 ? 'green' : 'red'}>
            合计 {total.toFixed(2)}%
          </Tag>
        </Space>
        <Button size="small" onClick={equalize}>自动平均</Button>
      </div>
      <Space direction="vertical" style={{ width: '100%' }}>
        {value.components.map((component, index) => (
          <div className="component-row" key={`${component.strategy_id}-${index}`}>
            <Select
              value={component.strategy_id}
              style={{ flex: 1 }}
              options={strategies.map((item) => ({
                value: item.id,
                label: `${item.icon} ${item.name}`,
                disabled: value.components.some(
                  (current, currentIndex) =>
                    currentIndex !== index && current.strategy_id === item.id,
                ),
              }))}
              onChange={(strategy_id) => {
                const components = clone(value.components)
                components[index].strategy_id = strategy_id
                onChange({ ...value, components })
              }}
            />
            <InputNumber
              value={component.weight}
              min={0.01}
              max={100}
              addonAfter="%"
              onChange={(weight) => {
                const components = clone(value.components)
                components[index].weight = Number(weight ?? 0.01)
                onChange({ ...value, components })
              }}
            />
            <Button
              danger
              type="text"
              icon={<DeleteOutlined />}
              disabled={value.components.length <= 2}
              onClick={() =>
                onChange({
                  ...value,
                  components: value.components.filter((_, itemIndex) => itemIndex !== index),
                })
              }
            />
          </div>
        ))}
        <Button
          type="dashed"
          block
          icon={<PlusOutlined />}
          disabled={value.components.length >= strategies.length}
          onClick={() => {
            const available = strategies.find(
              (item) => !value.components.some((current) => current.strategy_id === item.id),
            )
            if (available) {
              onChange({
                ...value,
                components: [...value.components, { strategy_id: available.id, weight: 1 }],
              })
            }
          }}
        >
          添加一个策略
        </Button>
      </Space>
      <Row gutter={[16, 16]} style={{ marginTop: 20 }}>
        <Col xs={24} md={12}>
          <Typography.Text type="secondary">买入触发分数</Typography.Text>
          <InputNumber
            value={value.trigger_score}
            min={1}
            max={100}
            addonAfter="分"
            style={{ width: '100%', marginTop: 6 }}
            onChange={(trigger_score) =>
              onChange({ ...value, trigger_score: Number(trigger_score ?? 50) })
            }
          />
        </Col>
        <Col xs={24} md={12}>
          <Typography.Text type="secondary">卖出触发分数</Typography.Text>
          <InputNumber
            value={value.exit_score}
            min={1}
            max={100}
            addonAfter="分"
            style={{ width: '100%', marginTop: 6 }}
            onChange={(exit_score) =>
              onChange({ ...value, exit_score: Number(exit_score ?? 50) })
            }
          />
        </Col>
      </Row>
    </div>
  )
}
