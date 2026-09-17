import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { apiClient } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { ErrorState } from './StateViews'
import type { AuthSession, TwoFactorSession } from '@/types/auth'
export function TwoFactorChallenge({
  challenge,
  onComplete,
}: {
  challenge: TwoFactorSession
  onComplete: (session: AuthSession) => void
}) {
  const { t } = useTranslation()
  const [code, setCode] = useState('')
  const setup = useMutation({
    mutationFn: () =>
      apiClient
        .post<{ secret: string; otpauth_uri: string }>('/auth/2fa/enable', {
          challenge_token: challenge.challenge_token,
        })
        .then((r) => r.data),
  })
  const verify = useMutation({
    mutationFn: () =>
      apiClient
        .post<AuthSession>(
          challenge.setup_required ? '/auth/2fa/verify' : '/auth/2fa/login',
          { challenge_token: challenge.challenge_token, code },
        )
        .then((r) => r.data),
    onSuccess: onComplete,
  })
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault()
        verify.mutate()
      }}
    >
      <p>{t('auth.twoFactor')}</p>
      {challenge.setup_required && (
        <>
          <Button
            type="button"
            onClick={() => setup.mutate()}
            disabled={setup.isSuccess}
            isLoading={setup.isPending}
          >
            {t('auth.setupAuthenticator')}
          </Button>
          {setup.data && (
            <div>
              <p className="text-sm">{t('auth.authenticatorSecret')}</p>
              <code className="block break-all rounded border p-3 select-all">
                {setup.data.secret}
              </code>
            </div>
          )}
        </>
      )}
      <Input
        label={t('auth.verificationCode')}
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={6}
        value={code}
        onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
      />
      {(setup.isError || verify.isError) && <ErrorState />}
      <Button type="submit" disabled={code.length !== 6} isLoading={verify.isPending}>
        {t('common.confirm')}
      </Button>
    </form>
  )
}
