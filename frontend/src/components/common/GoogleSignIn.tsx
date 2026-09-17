import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { apiClient } from '@/api/client'

type GoogleIdentity = {
  initialize: (config: {
    client_id: string
    callback: (response: { credential: string }) => void
  }) => void
  renderButton: (element: HTMLElement, options: object) => void
}
declare global {
  interface Window {
    google?: { accounts: { id: GoogleIdentity } }
  }
}
let sdk: Promise<void> | undefined
function loadSdk() {
  if (window.google) return Promise.resolve()
  sdk ??= new Promise<void>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = 'https://accounts.google.com/gsi/client'
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => {
      sdk = undefined
      script.remove()
      reject(new Error('Google sign-in unavailable'))
    }
    document.head.append(script)
  })
  return sdk
}
export function GoogleSignIn({
  onCredential,
}: {
  onCredential: (token: string) => void
}) {
  const { t, i18n } = useTranslation()
  const node = useRef<HTMLDivElement>(null)
  const callback = useRef(onCredential)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    callback.current = onCredential
  }, [onCredential])
  const config = useQuery({
    queryKey: ['public-config'],
    queryFn: () =>
      apiClient.get<{ google_client_id: string }>('/public/config').then((r) => r.data),
  })
  useEffect(() => {
    let active = true
    if (!config.data?.google_client_id) return
    void loadSdk()
      .then(() => {
        if (!active || !node.current || !window.google) return
        window.google.accounts.id.initialize({
          client_id: config.data.google_client_id,
          callback: (r) => callback.current(r.credential),
        })
        window.google.accounts.id.renderButton(node.current, {
          theme: 'outline',
          size: 'large',
          width: 300,
          locale: i18n.resolvedLanguage,
        })
      })
      .catch(() => {
        if (active) setFailed(true)
      })
    return () => {
      active = false
    }
  }, [config.data?.google_client_id, i18n.resolvedLanguage])
  return (
    <div>
      <div ref={node} />
      {(failed || config.isError || (config.data && !config.data.google_client_id)) && (
        <p className="text-xs text-muted-foreground">{t('auth.googleUnavailable')}</p>
      )}
    </div>
  )
}
