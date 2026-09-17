import { Outlet } from 'react-router-dom'

import { OfflineBanner } from '@/components/layout/OfflineBanner'
import { Sidebar } from '@/components/layout/Sidebar'
import { Topbar } from '@/components/layout/Topbar'

/** Shell for every authenticated screen (creator + admin): sidebar + topbar. */
export function AppLayout() {
  return (
    <div className="dashboard-shell flex min-h-svh bg-background">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <OfflineBanner />
        <Topbar />
        <main className="mx-auto w-full max-w-6xl flex-1 p-4 sm:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
