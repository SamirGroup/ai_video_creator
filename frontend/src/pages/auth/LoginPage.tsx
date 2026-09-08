import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { z } from 'zod'

import { authApi } from '@/api/auth'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { useAuthStore } from '@/stores/authStore'

const loginSchema = z.object({
  email: z.string().min(1, 'auth.validation.emailRequired').email('auth.validation.emailInvalid'),
  password: z.string().min(1, 'auth.validation.passwordRequired'),
})

type LoginFormValues = z.infer<typeof loginSchema>

export function LoginPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const setSession = useAuthStore((s) => s.setSession)
  const fromPath = (location.state as { from?: Location })?.from?.pathname ?? '/dashboard'

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({ resolver: zodResolver(loginSchema) })

  const loginMutation = useMutation({
    mutationFn: authApi.login,
    onSuccess: (session) => {
      setSession(session.user, session.access)
      navigate(fromPath, { replace: true })
    },
  })

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1 text-center">
        <h1 className="text-xl font-semibold text-foreground">{t('auth.login.title')}</h1>
        <p className="text-sm text-muted-foreground">{t('auth.login.subtitle')}</p>
      </div>

      <form
        className="flex flex-col gap-4"
        onSubmit={handleSubmit((values) => loginMutation.mutate(values))}
        noValidate
      >
        <Input
          type="email"
          label={t('auth.login.email')}
          autoComplete="email"
          required
          error={errors.email && t(errors.email.message as string)}
          {...register('email')}
        />
        <Input
          type="password"
          label={t('auth.login.password')}
          autoComplete="current-password"
          required
          error={errors.password && t(errors.password.message as string)}
          {...register('password')}
        />

        <div className="flex justify-end">
          <Link
            to="/forgot-password"
            className="text-sm font-medium text-primary-600 hover:underline"
          >
            {t('auth.login.forgotPassword')}
          </Link>
        </div>

        {loginMutation.isError && (
          <p role="alert" className="text-sm text-destructive-600">
            {loginMutation.error instanceof ApiError && loginMutation.error.status === 401
              ? t('auth.login.error')
              : t('common.error.generic')}
          </p>
        )}

        <Button type="submit" className="w-full" isLoading={loginMutation.isPending}>
          {loginMutation.isPending ? t('auth.login.submitting') : t('auth.login.submit')}
        </Button>
      </form>

      <div className="relative text-center text-xs text-muted-foreground">
        <span className="bg-background px-2">{t('auth.login.orGoogle')}</span>
      </div>

      {/* TODO: real API — wire Google Identity Services + POST /auth/google (FR-3) */}
      <Button type="button" variant="outline" className="w-full" disabled>
        {t('auth.login.googleButton')}
      </Button>

      <p className="text-center text-sm text-muted-foreground">
        {t('auth.login.noAccount')}{' '}
        <Link to="/register" className="font-medium text-primary-600 hover:underline">
          {t('auth.login.registerLink')}
        </Link>
      </p>
    </div>
  )
}
