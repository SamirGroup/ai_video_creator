import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { z } from 'zod'

import { authApi } from '@/api/auth'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

const forgotPasswordSchema = z.object({
  email: z.string().min(1, 'auth.validation.emailRequired').email('auth.validation.emailInvalid'),
})

type ForgotPasswordFormValues = z.infer<typeof forgotPasswordSchema>

export function ForgotPasswordPage() {
  const { t } = useTranslation()
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ForgotPasswordFormValues>({ resolver: zodResolver(forgotPasswordSchema) })

  const mutation = useMutation({ mutationFn: authApi.requestPasswordReset })

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1 text-center">
        <h1 className="text-xl font-semibold text-foreground">{t('auth.forgotPassword.title')}</h1>
        <p className="text-sm text-muted-foreground">{t('auth.forgotPassword.subtitle')}</p>
      </div>

      {mutation.isSuccess ? (
        <p role="status" className="text-center text-sm text-success-700">
          {t('auth.forgotPassword.success')}
        </p>
      ) : (
        <form
          className="flex flex-col gap-4"
          onSubmit={handleSubmit((values) => mutation.mutate(values))}
          noValidate
        >
          <Input
            type="email"
            label={t('auth.forgotPassword.email')}
            autoComplete="email"
            required
            error={errors.email && t(errors.email.message as string)}
            {...register('email')}
          />
          <Button type="submit" className="w-full" isLoading={mutation.isPending}>
            {mutation.isPending
              ? t('auth.forgotPassword.submitting')
              : t('auth.forgotPassword.submit')}
          </Button>
        </form>
      )}

      <p className="text-center text-sm">
        <Link to="/login" className="font-medium text-primary-600 hover:underline">
          {t('auth.forgotPassword.backToLogin')}
        </Link>
      </p>
    </div>
  )
}
