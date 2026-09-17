import { adminApi } from '@/api/admin'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ErrorState, TableSkeleton } from '@/components/common/StateViews'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

function useAdminUsers(search: string) {
  return useQuery({
    queryKey: ['admin-users', search],
    queryFn: () => adminApi.allUsers({ search }),
  })
}

export function UsersPage() {
  const { t } = useTranslation()
  const [search, setSearch] = useState('')
  const { data, isLoading, isError, refetch } = useAdminUsers(search)

  const action = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      active ? adminApi.suspendUser(id) : adminApi.reactivateUser(id),
    onSuccess: () => refetch(),
  })

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-foreground">{t('admin.users.title')}</h1>

      <Input
        placeholder={t('admin.users.search')}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="max-w-sm"
      />

      {action.isError && <ErrorState />}
      {isLoading && <TableSkeleton />}
      {isError && <ErrorState onRetry={() => refetch()} />}

      {data && (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[640px] text-start text-sm">
            <thead className="border-b border-border bg-muted/50 text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">{t('common.status')}</th>
                <th className="px-4 py-3 font-medium">Plan</th>
                <th className="px-4 py-3 text-end font-medium">{t('common.actions')}</th>
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
                    <Badge
                      tone={user.status === 'active' ? 'success' : 'destructive'}
                      dot
                    >
                      {user.status}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {user.plan_code ?? '—'}
                  </td>
                  <td className="px-4 py-3 text-end">
                    <Button
                      size="sm"
                      variant="outline"
                      isLoading={action.isPending}
                      onClick={() =>
                        action.mutate({ id: user.id, active: user.status === 'active' })
                      }
                    >
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
