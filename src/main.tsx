import React from 'react'
import ReactDOM from 'react-dom/client'
import { App as AntApp, ConfigProvider } from 'antd'
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
        token: {
          colorPrimary: '#175cd3',
          colorInfo: '#175cd3',
          colorSuccess: '#039855',
          colorError: '#d92d20',
          colorWarning: '#dc6803',
          borderRadius: 10,
          fontFamily:
            '"Inter", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif',
        },
        components: {
          Layout: { bodyBg: '#f5f7fb', siderBg: '#0b1830' },
          Table: { headerBg: '#f8fafc', headerColor: '#475467' },
          Card: { headerBg: 'transparent' },
        },
      }}
    >
      <AntApp>
        <App />
      </AntApp>
    </ConfigProvider>,
)
