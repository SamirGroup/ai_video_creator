import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { GoogleSignIn } from '@/components/common/GoogleSignIn'
import { TwoFactorChallenge } from '@/components/common/TwoFactorChallenge'
import { useAuthStore } from '@/stores/authStore'
import { homePath } from '@/routes/homePath'
import type { AuthSession, TwoFactorSession } from '@/types/auth'
import { z } from 'zod'

import { authApi } from '@/api/auth'
import { Button } from '@/components/ui/Button'
import { Checkbox } from '@/components/ui/Checkbox'
import { Input } from '@/components/ui/Input'

const registerSchema = z.object({
  full_name: z.string().min(1, 'auth.validation.fullNameRequired'),
  email: z
    .string()
    .min(1, 'auth.validation.emailRequired')
    .email('auth.validation.emailInvalid'),
  password: z.string().min(10, 'auth.validation.passwordMinLength'),
  marketing_opt_in: z.boolean().optional(),
})

type RegisterFormValues = z.infer<typeof registerSchema>

export function RegisterPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const setSession = useAuthStore((s) => s.setSession)
  const [challenge, setChallenge] = useState<TwoFactorSession | null>(null)
  const finish = (session: AuthSession) => {
    setSession(session.user, session.access)
    navigate(homePath(session.user), { replace: true })
  }
  const google = useMutation({
    mutationFn: (id_token: string) => authApi.loginWithGoogle({ id_token }),
    onSuccess: (session) => {
      if ('requires_2fa' in session) setChallenge(session)
      else finish(session)
    },
  })

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { marketing_opt_in: false },
  })

  const registerMutation = useMutation({ mutationFn: authApi.register })

  if (challenge) return <TwoFactorChallenge challenge={challenge} onComplete={finish} />

  if (registerMutation.isSuccess) {
    return (
      <div className="flex flex-col items-center gap-3 text-center">
        <h1 className="text-xl font-semibold text-foreground">
          {t('auth.register.title')}
        </h1>
        <p className="text-sm text-muted-foreground">{t('auth.register.success')}</p>
        <Link
          to="/login"
          className="text-sm font-medium text-primary-600 hover:underline"
        >
          {t('auth.verifyEmail.goToLogin')}
        </Link>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1 text-center">
        <h1 className="text-xl font-semibold text-foreground">
          {t('auth.register.title')}
        </h1>
        <p className="text-sm text-muted-foreground">{t('auth.register.subtitle')}</p>
      </div>

      <GoogleSignIn onCredential={(token) => google.mutate(token)} />
      {google.isError && <p role="alert">{t('common.error.generic')}</p>}
      <div className="auth-divider text-center text-xs text-muted-foreground">
        <span>{t('auth.register.email')}</span>
      </div>
      <form
        className="flex flex-col gap-4"
        onSubmit={handleSubmit((values) => registerMutation.mutate(values))}
        noValidate
      >
        <Input
          label={t('auth.register.fullName')}
          autoComplete="name"
          required
          error={errors.full_name && t(errors.full_name.message as string)}
          {...register('full_name')}
        />
        <Input
          type="email"
          label={t('auth.register.email')}
          autoComplete="email"
          required
          error={errors.email && t(errors.email.message as string)}
          {...register('email')}
        />
        <Input
          type="password"
          label={t('auth.register.password')}
          autoComplete="new-password"
          required
          hint={!errors.password ? t('auth.register.passwordHint') : undefined}
          error={errors.password && t(errors.password.message as string)}
          {...register('password')}
        />
        <Checkbox
          label={t('auth.register.marketingOptIn')}
          {...register('marketing_opt_in')}
        />

        {registerMutation.isError && (
          <p role="alert" className="text-sm text-destructive-600">
            {t('common.error.generic')}
          </p>
        )}

        <Button type="submit" className="w-full" isLoading={registerMutation.isPending}>
          {registerMutation.isPending
            ? t('auth.register.submitting')
            : t('auth.register.submit')}
        </Button>
      </form>

      <p className="text-center text-sm text-muted-foreground">
        {t('auth.register.hasAccount')}{' '}
        <Link to="/login" className="font-medium text-primary-600 hover:underline">
          {t('auth.register.loginLink')}
        </Link>
      </p>
    </div>
  )
}
