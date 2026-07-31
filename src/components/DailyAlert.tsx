import { Alert } from 'antd'
import type { ComponentProps } from 'react'
import { useMemo, useState } from 'react'

type AlertProps = ComponentProps<typeof Alert>

function localDateKey() {
  const parts = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date())
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return `${value.year}-${value.month}-${value.day}`
}

export default function DailyAlert({ noticeKey, ...props }: AlertProps & { noticeKey: string }) {
  const storageKey = useMemo(
    () => `smart-a-share:closed-notice:${localDateKey()}:${noticeKey}`,
    [noticeKey],
  )
  const [visible, setVisible] = useState(() => localStorage.getItem(storageKey) !== '1')

  if (!visible) return null

  return (
    <Alert
      {...props}
      closable
      afterClose={() => {
        localStorage.setItem(storageKey, '1')
        setVisible(false)
        props.afterClose?.()
      }}
    />
  )
}
