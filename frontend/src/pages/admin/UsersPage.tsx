import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ErrorState, TableSkeleton } from '@/components/common/StateViews'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { mockAdminUsers } from '@/mocks/fixtures'
import { mockFetch } from '@/mocks/mockFetch'

// TODO: real API — replace with adminApi.listUsers (src/api/admin.ts)
function useAdminUsers(search: string) {
  return useQuery({
    queryKey: ['admin-users', search],
    queryFn: () =>
      mockFetch(
        mockAdminUsers.filter(
          (u) =>
            u.email.toLowerCase().includes(search.toLowerCase()) ||
            u.full_name.toLowerCase().includes(search.toLowerCase()),
        ),
      ),
  })
}

export function UsersPage() {
  const { t } = useTranslation()
  const [search, setSearch] = useState('')
  const { data, isLoading, isError, refetch } = useAdminUsers(search)

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-foreground">{t('admin.users.title')}</h1>

      <Input
        placeholder={t('admin.users.search')}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="max-w-sm"
      />

      {isLoading && <TableSkeleton />}
      {isError && <ErrorState onRetry={() => refetch()} />}

      {data && (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="border-b border-border bg-muted/50 text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">{t('common.status')}</th>
                <th className="px-4 py-3 font-medium">Plan</th>
                <th className="px-4 py-3 text-right font-medium">{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.map((user) => (
                <tr key={user.id}>
                  <td className="px-4 py-3">
                    <p className="font-medium text-foreground">{user.full_name}</p>
                    <p className="text-xs text-muted-foreground">{user.email}</p>
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={user.status === 'active' ? 'success' : 'destructive'} dot>
                      {user.status}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{user.plan_code ?? '—'}</td>
                  <td className="px-4 py-3 text-right">
                    {/* TODO: real API — POST /admin/users/{id}/suspend|reactivate */}
                    <Button size="sm" variant="outline">
                      {user.status === 'active'
                        ? t('admin.users.suspend')
                        : t('admin.users.reactivate')}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
