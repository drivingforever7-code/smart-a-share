import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import {
  AreaChartOutlined,
  BarChartOutlined,
  ControlOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  FundOutlined,
  HistoryOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  RadarChartOutlined,
  RobotOutlined,
  SearchOutlined,
  StarOutlined,
} from '@ant-design/icons'
import { Button, Grid, Layout, Menu, Space, Tag, Typography } from 'antd'
import type { MenuProps } from 'antd'
import StockSearchInput from './components/StockSearchInput'
import LoadingExperience from './components/LoadingExperience'
import type { PageKey } from './types'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const AutoBacktest = lazy(() => import('./pages/AutoBacktest'))
const Screener = lazy(() => import('./pages/Screener'))
const Ranking = lazy(() => import('./pages/Ranking'))
const StockDetail = lazy(() => import('./pages/StockDetailV2'))
const Backtest = lazy(() => import('./pages/StrategyLab'))
const AiAnalysis = lazy(() => import('./pages/AiAnalysis'))
const StrategyWorkshop = lazy(() => import('./pages/StrategyWorkshop'))
const Watchlist = lazy(() => import('./pages/Watchlist'))
const Settings = lazy(() => import('./pages/Settings'))

const { Header, Sider, Content } = Layout

const items: MenuProps['items'] = [
  { key: 'dashboard', icon: <RadarChartOutlined />, label: '今日机会' },
  { key: 'autoBacktest', icon: <HistoryOutlined />, label: '自动回测' },
  { key: 'screener', icon: <SearchOutlined />, label: '条件选股' },
  { key: 'ranking', icon: <BarChartOutlined />, label: '评分榜' },
  { key: 'detail', icon: <FundOutlined />, label: '股票详情' },
  { key: 'ai', icon: <RobotOutlined />, label: 'AI联合分析' },
  { key: 'backtest', icon: <ExperimentOutlined />, label: '策略实验室' },
  { key: 'workshop', icon: <ControlOutlined />, label: '策略工坊' },
  { key: 'watchlist', icon: <StarOutlined />, label: '自选股' },
  { type: 'divider' },
  { key: 'settings', icon: <DatabaseOutlined />, label: '数据与设置' },
]

const titles: Record<PageKey, { title: string; subtitle: string }> = {
  dashboard: { title: '今日机会', subtitle: '从全市场信号中发现短线与波段机会' },
  autoBacktest: { title: '自动回测', subtitle: '跟踪每日短线与波段前三从发现至今的真实表现' },
  screener: { title: '条件选股', subtitle: '组合条件，找到符合你交易思路的股票' },
  ranking: { title: '综合评分榜', subtitle: '比较短线强度与波段质量' },
  detail: { title: '股票详情', subtitle: '核对行情、评分依据和风险条件' },
  ai: { title: 'AI联合分析', subtitle: '多角色阅读同一份数据，给出多空证据与风险约束' },
  backtest: { title: '策略实验室', subtitle: '用股票篮子和样本外数据检验策略是否稳健' },
  workshop: { title: '策略工坊', subtitle: '不用写代码，自定义买卖条件与组合权重' },
  watchlist: { title: '我的自选', subtitle: '集中跟踪你真正关心的股票' },
  settings: { title: '数据与设置', subtitle: '检查数据新鲜度和本地偏好' },
}

function parseHash(): { page: PageKey; code: string } {
  const hash = window.location.hash.replace(/^#\/?/, '')
  const [path, query = ''] = hash.split('?')
  const validPages: PageKey[] = [
    'dashboard',
    'autoBacktest',
    'screener',
    'ranking',
    'detail',
    'ai',
    'backtest',
    'workshop',
    'watchlist',
    'settings',
  ]
  const page = validPages.includes(path as PageKey) ? (path as PageKey) : 'dashboard'
  const code = new URLSearchParams(query).get('code') ?? '600519'
  return { page, code }
}

export default function App() {
  const screens = Grid.useBreakpoint()
  const initial = useMemo(parseHash, [])
  const [page, setPage] = useState<PageKey>(initial.page)
  const [selectedCode, setSelectedCode] = useState(initial.code)
  const [collapsed, setCollapsed] = useState(false)
  const [quickCode, setQuickCode] = useState('')

  const mobile = !screens.lg

  useEffect(() => {
    if (mobile) setCollapsed(true)
  }, [mobile])

  useEffect(() => {
    const onHashChange = () => {
      const next = parseHash()
      setPage(next.page)
      setSelectedCode(next.code)
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const navigate = (next: PageKey, code?: string) => {
    const nextCode = code ?? selectedCode
    if (code) setSelectedCode(code)
    setPage(next)
    window.location.hash = ['detail', 'ai'].includes(next)
      ? `#/${next}?code=${nextCode}`
      : `#/${next}`
  }

  const pageContent = {
    dashboard: <Dashboard onOpenStock={(code) => navigate('detail', code)} />,
    autoBacktest: <AutoBacktest onOpenStock={(code) => navigate('detail', code)} />,
    screener: <Screener onOpenStock={(code) => navigate('detail', code)} />,
    ranking: <Ranking onOpenStock={(code) => navigate('detail', code)} />,
    detail: <StockDetail code={selectedCode} onCodeChange={(code) => navigate('detail', code)} />,
    ai: <AiAnalysis defaultCode={selectedCode} />,
    backtest: <Backtest />,
    workshop: <StrategyWorkshop />,
    watchlist: <Watchlist onOpenStock={(code) => navigate('detail', code)} />,
    settings: <Settings />,
  }[page]

  return (
    <Layout className="app-layout">
      <Sider
        width={224}
        collapsedWidth={mobile ? 0 : 76}
        collapsed={collapsed}
        trigger={null}
        className="app-sider"
      >
        <div className={collapsed ? 'brand brand-collapsed' : 'brand'}>
          <div className="brand-mark">
            <AreaChartOutlined />
          </div>
          {!collapsed && (
            <div>
              <div className="brand-name">智选 A 股</div>
              <div className="brand-caption">短线 · 波段</div>
            </div>
          )}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[page]}
          items={items}
          onClick={({ key }) => navigate(key as PageKey)}
          className="main-menu"
        />
        {!collapsed && (
          <div className="sider-footer">
            <Tag color="blue">本地数据</Tag>
            <span>仅在你的电脑运行</span>
          </div>
        )}
      </Sider>

      <Layout>
        <Header className="app-header">
          <Space size={12}>
            <Button
              type="text"
              className="collapse-button"
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed((value) => !value)}
            />
            <div className="header-title">
              <Typography.Title level={4}>{titles[page].title}</Typography.Title>
              <Typography.Text type="secondary">{titles[page].subtitle}</Typography.Text>
            </div>
          </Space>
          <StockSearchInput
            value={quickCode}
            onChange={setQuickCode}
            onSelect={(code) => {
              navigate('detail', code)
              setQuickCode('')
            }}
            className="header-search"
          />
        </Header>
        <Content className="app-content">
          <Suspense
            fallback={(
              <LoadingExperience
                fullscreen
                label="正在加载页面模块"
                detail="正在连接量化引擎与界面组件"
              />
            )}
          >
            <div className="page-transition" key={`${page}-${selectedCode}`}>
              {pageContent}
            </div>
          </Suspense>
        </Content>
      </Layout>
    </Layout>
  )
}
