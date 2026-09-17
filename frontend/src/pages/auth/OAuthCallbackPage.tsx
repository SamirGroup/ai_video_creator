import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { apiClient } from '@/api/client'
import { ErrorState, PageLoading } from '@/components/common/StateViews'
export function OAuthCallbackPage() {
  const { kind } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const client = useQueryClient()
  const started = useRef(false)
  const [failed, setFailed] = useState(false)
  const { t } = useTranslation()
  const invalid =
    !['youtube', 'adsense'].includes(kind ?? '') ||
    params.has('error') ||
    !params.get('code') ||
    !params.get('state')
  useEffect(() => {
    if (started.current) return
    started.current = true
    if (invalid) return
    void apiClient
      .get(`/oauth/${kind}/callback`, {
        params: { code: params.get('code'), state: params.get('state') },
      })
      .then(async () => {
        await client.invalidateQueries({ queryKey: ['channels'] })
        await client.invalidateQueries({ queryKey: ['channel'] })
        navigate('/channel', { replace: true })
      })
      .catch(() => setFailed(true))
  }, [kind, params, navigate, client, invalid])
  return invalid || failed ? (
    <div>
      <ErrorState />
      <Link to="/channel">{t('common.back')}</Link>
    </div>
  ) : (
    <PageLoading />
  )
}
