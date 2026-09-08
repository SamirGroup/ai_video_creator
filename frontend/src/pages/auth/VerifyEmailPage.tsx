import { useEffect } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router-dom'

import { authApi } from '@/api/auth'
import { PageLoading } from '@/components/common/StateViews'

export function VerifyEmailPage() {
  const { t } = useTranslation()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')

  const mutation = useMutation({ mutationFn: authApi.verifyEmail })

  useEffect(() => {
    if (token) mutation.mutate({ token })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  return (
    <div className="flex flex-col items-center gap-3 text-center">
      <h1 className="text-xl font-semibold text-foreground">{t('auth.verifyEmail.title')}</h1>

      {!token || mutation.isError ? (
        <p role="alert" className="text-sm text-destructive-600">
          {t('auth.verifyEmail.error')}
        </p>
      ) : mutation.isSuccess ? (
        <p role="status" className="text-sm text-success-700">
          {t('auth.verifyEmail.success')}
        </p>
      ) : (
        <PageLoading label={t('auth.verifyEmail.pending')} />
      )}

      <Link to="/login" className="text-sm font-medium text-primary-600 hover:underline">
        {t('auth.verifyEmail.goToLogin')}
      </Link>
    </div>
  )
}
