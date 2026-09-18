import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { homePath } from '@/routes/homePath'
import type { AuthSession } from '@/types/auth'

declare global {
  interface Window {
    Telegram?: {
      WebApp: {
        initData: string
        ready: () => void
        expand: () => void
        openInvoice: (url: string, callback?: (status: string) => void) => void
        colorScheme: string
      }
    }
  }
}
export function isTelegram() {
  return Boolean(window.Telegram?.WebApp.initData)
}
export function TelegramBridge() {
  const client = useQueryClient()
  const navigate = useNavigate()
  useEffect(() => {
    const tg = window.Telegram?.WebApp
    if (!tg?.initData) return
    tg.ready()
    tg.expand()
    if (!useAuthStore.getState().accessToken)
      void apiClient
        .post<AuthSession>('/telegram/login', { init_data: tg.initData })
        .then(({ data }) => {
          useAuthStore.getState().setSession(data.user, data.access)
          void client.invalidateQueries()
          if (['/', '/login', '/register', '/signup'].includes(window.location.pathname))
            navigate(homePath(data.user), { replace: true })
        })
        .catch(() => {})
  }, [client, navigate])
  return null
}
