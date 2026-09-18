import { Outlet } from 'react-router-dom'
import { OfflineBanner } from '@/components/layout/OfflineBanner'
import AuthForm from '@/components/ui/auth-form'

export function AuthLayout() {
  return (
    <>
      <OfflineBanner />
      <AuthForm>
        <Outlet />
      </AuthForm>
    </>
  )
}
