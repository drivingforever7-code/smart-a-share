import React from 'react'
import ReactDOM from 'react-dom/client'
import { App as AntApp, ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import App from './App'
import './styles.css'

dayjs.locale('zh-cn')

ReactDOM.createRoot(document.getElementById('root')!).render(
  <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: '#35d9ff',
          colorInfo: '#35d9ff',
          colorSuccess: '#12b76a',
          colorError: '#f04438',
          colorWarning: '#fdb022',
          colorBgBase: '#050914',
          colorBgContainer: '#091323',
          colorBgElevated: '#0c192c',
          colorText: '#e8f3ff',
          colorTextSecondary: '#8fa9c3',
          colorBorder: '#1b3852',
          colorSplit: 'rgba(91, 145, 184, 0.2)',
          borderRadius: 10,
          fontFamily:
            '"Microsoft YaHei UI", "PingFang SC", system-ui, sans-serif',
          boxShadowSecondary: '0 18px 60px rgba(0, 0, 0, 0.38)',
        },
        components: {
          Layout: { bodyBg: '#050914', siderBg: '#060c18', headerBg: '#07101e' },
          Table: {
            headerBg: '#0b192b',
            headerColor: '#9bc6d9',
            rowHoverBg: 'rgba(53, 217, 255, 0.07)',
            borderColor: '#17334d',
          },
          Card: { headerBg: 'transparent' },
          Menu: {
            darkItemBg: 'transparent',
            darkItemSelectedBg: 'rgba(53, 217, 255, 0.13)',
            darkItemSelectedColor: '#7ee8ff',
          },
        },
      }}
    >
      <AntApp>
        <App />
      </AntApp>
    </ConfigProvider>,
)
