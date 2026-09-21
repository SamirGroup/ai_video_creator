import { PricingPage } from '@/pages/public/PricingPage'
import { TelegramBridge } from '@/components/common/TelegramBridge'
import { QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { Navigate, Route, BrowserRouter, Routes } from 'react-router-dom'

import { AuthBootstrap } from '@/components/common/AuthBootstrap'
import { ErrorBoundary } from '@/components/common/ErrorBoundary'
import { useApplyTheme } from '@/components/layout/ThemeToggle'
import { queryClient } from '@/lib/queryClient'
import { AppLayout } from '@/layouts/AppLayout'
import { AuthLayout } from '@/layouts/AuthLayout'
import { ForgotPasswordPage } from '@/pages/auth/ForgotPasswordPage'
import { OAuthCallbackPage } from '@/pages/auth/OAuthCallbackPage'
import { LoginPage } from '@/pages/auth/LoginPage'
import { RegisterPage } from '@/pages/auth/RegisterPage'
import { VerifyEmailPage } from '@/pages/auth/VerifyEmailPage'
import { ChannelPage } from '@/pages/creator/ChannelPage'
import { BillingPage } from '@/pages/creator/BillingPage'
import { ContractPage } from '@/pages/creator/ContractPage'
import { LandingPage } from '@/pages/public/LandingPage'
import { ContentPlanPage } from '@/pages/creator/ContentPlanPage'
import { PreferencesPage } from '@/pages/creator/PreferencesPage'
import { RevenuePage } from '@/pages/creator/RevenuePage'
import { VideoDetailPage } from '@/pages/creator/VideoDetailPage'
import { VideosPage } from '@/pages/creator/VideosPage'
import { AdminConfigPage } from '@/pages/admin/AdminConfigPage'
import { AdminFinancePage } from '@/pages/admin/AdminFinancePage'
import { AdminVideosPage } from '@/pages/admin/AdminVideosPage'
import { ModerationPage } from '@/pages/admin/ModerationPage'
import { UsersPage } from '@/pages/admin/UsersPage'
import { ProtectedRoute } from '@/routes/ProtectedRoute'
import { RoleRoute } from '@/routes/RoleRoute'
import { CreatorHomeRoute } from '@/routes/CreatorHomeRoute'
import { AdminDashboardPage } from '@/pages/admin/AdminDashboardPage'
import { useAuthStore } from '@/stores/authStore'
import { homePath } from '@/routes/homePath'

function HomeRedirect() {
  const user = useAuthStore((s) => s.user)
  return <Navigate to={user ? homePath(user) : '/login'} replace />
}

function AppRoutes() {
  return (
    <Routes>
      {/* Public (SPEC 3.1 #1) */}
      <Route element={<AuthLayout />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/signup" element={<RegisterPage />} />
        <Route path="/verify-email" element={<VerifyEmailPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      </Route>

      {/* Creator + admin (auth-guarded, SPEC 6) */}
      <Route element={<ProtectedRoute />}>
        <Route path="/oauth/:kind/callback" element={<OAuthCallbackPage />} />
        <Route element={<AppLayout />}>
          <Route path="/dashboard" element={<HomeRedirect />} />
          <Route path="/creator/:id" element={<CreatorHomeRoute />} />
          <Route element={<RoleRoute allow={['creator']} />}>
          <Route path="/channel" element={<ChannelPage />} />
          <Route path="/content-plan" element={<ContentPlanPage />} />
          <Route path="/preferences" element={<PreferencesPage />} />
          <Route path="/videos" element={<VideosPage />} />
          <Route path="/videos/:videoId" element={<VideoDetailPage />} />
          <Route path="/revenue" element={<RevenuePage />} />
          <Route path="/billing" element={<BillingPage />} />
          <Route path="/billing/success" element={<BillingPage />} />
          <Route path="/billing/cancel" element={<BillingPage />} />
          <Route path="/contract" element={<ContractPage />} />
          </Route>

          {/* Admin (role-guarded on top of auth — client-side UX only, server is
              the real authority; see routes/RoleRoute.tsx) */}
          <Route element={<RoleRoute allow={['admin']} />}>
            <Route path="/admin-dashboard" element={<AdminDashboardPage />} />
          </Route>
          <Route element={<RoleRoute allow={['admin']} />}>
            <Route path="/admin/users" element={<UsersPage />} />
          </Route>
          <Route element={<RoleRoute allow={['admin', 'support']} />}>
            <Route path="/admin/videos" element={<AdminVideosPage />} />
          </Route>
          <Route element={<RoleRoute allow={['admin', 'moderator']} />}>
            <Route path="/admin/moderation" element={<ModerationPage />} />
          </Route>
          <Route element={<RoleRoute allow={['admin', 'finance']} />}>
            <Route path="/admin/finance" element={<AdminFinancePage />} />
          </Route>
          <Route element={<RoleRoute allow={['admin']} />}>
            <Route path="/admin/config" element={<AdminConfigPage />} />
          </Route>
        </Route>
      </Route>

      <Route path="/" element={<LandingPage />} />
      <Route path="/pricing" element={<PricingPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

function App() {
  // Applies the persisted `.dark` class to <html> for the lifetime of the app.
  useApplyTheme()

  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthBootstrap>
            <TelegramBridge />
            <AppRoutes />
          </AuthBootstrap>
        </BrowserRouter>
        {import.meta.env.DEV && <ReactQueryDevtools buttonPosition="bottom-left" />}
      </QueryClientProvider>
    </ErrorBoundary>
  )
}

export default App
