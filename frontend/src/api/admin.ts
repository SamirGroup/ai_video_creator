import { collectPages } from './pagination'
import { apiClient } from './client'
import type {
  AdminUserFilters,
  AdminUserListItem,
  AdminVideoJobListItem,
  FinanceOverview,
  ModerationDecisionPayload,
  ModerationQueueItem,
  ProviderConfig,
} from '@/types/admin'
import type { CursorPage } from '@/types/common'
import type { Plan } from '@/types/billing'
import type { VideoListFilters } from '@/types/video'

// Endpoint groups: Admin — users/jobs/moderation/finance/config (SPEC 6). TODO: real API.
export const adminApi = {
  allUsers: (filters: AdminUserFilters = {}) =>
    collectPages<AdminUserListItem>('/admin/users', filters),
  allVideos: () => collectPages<AdminVideoJobListItem>('/admin/videos'),
  allModeration: async (): Promise<ModerationQueueItem[]> => {
    const rows = await collectPages<{
      id: string
      title: string
      created_at: string
      latest_log: null | {
        stage: ModerationQueueItem['stage']
        verdict: ModerationQueueItem['verdict']
        categories: Record<string, number>
      }
    }>('/admin/moderation/queue')
    return rows.map((row) => ({
      job_id: row.id,
      video_title: row.title,
      user_email: '',
      created_at: row.created_at,
      stage: row.latest_log?.stage ?? 'final',
      verdict: row.latest_log?.verdict ?? 'flag',
      categories: row.latest_log?.categories ?? {},
    }))
  },
  listUsers: (filters: AdminUserFilters = {}) =>
    apiClient
      .get<CursorPage<AdminUserListItem>>('/admin/users', { params: filters })
      .then((r) => r.data),

  getUser: (id: string) =>
    apiClient.get<AdminUserListItem>(`/admin/users/${id}`).then((r) => r.data),

  suspendUser: (id: string) =>
    apiClient.post<void>(`/admin/users/${id}/suspend`).then((r) => r.data),

  reactivateUser: (id: string) =>
    apiClient.post<void>(`/admin/users/${id}/reactivate`).then((r) => r.data),

  listVideoJobs: (filters: VideoListFilters = {}) =>
    apiClient
      .get<CursorPage<AdminVideoJobListItem>>('/admin/videos', { params: filters })
      .then((r) => r.data),

  retryVideoJob: (id: string) =>
    apiClient.post<void>(`/admin/videos/${id}/retry`).then((r) => r.data),

  cancelVideoJob: (id: string) =>
    apiClient.post<void>(`/admin/videos/${id}/cancel`).then((r) => r.data),

  moderationQueue: () =>
    apiClient
      .get<CursorPage<ModerationQueueItem>>('/admin/moderation/queue')
      .then((r) => r.data),

  decideModerationCase: (jobId: string, payload: ModerationDecisionPayload) =>
    apiClient
      .post<void>(`/admin/moderation/${jobId}/decide`, payload)
      .then((r) => r.data),

  financeOverview: () =>
    apiClient
      .get<{
        mrr_usd: string
        active_subscriptions: number
        revenue_share_platform_total_usd: string
        uncollected_invoices_usd: string
        uncollected_invoices_count: number
      }>('/admin/finance/overview')
      .then(({ data }): FinanceOverview => ({
        mrr: data.mrr_usd,
        currency: 'USD',
        active_subscriptions: data.active_subscriptions,
        revenue_share_total: data.revenue_share_platform_total_usd,
        uncollected_invoices_total: data.uncollected_invoices_usd,
        uncollected_invoices_count: data.uncollected_invoices_count,
      })),

  financeExportUrl: () => '/api/v1/admin/finance/export',

  listPlans: () => collectPages<Plan>('/admin/plans'),

  updatePlan: (id: string, payload: Partial<Plan>) =>
    apiClient.patch<Plan>(`/admin/plans/${id}`, payload).then((r) => r.data),

  listProviders: () => collectPages<ProviderConfig>('/admin/providers'),

  updateProvider: (id: string, payload: Partial<ProviderConfig>) =>
    apiClient
      .patch<ProviderConfig>(`/admin/providers/${id}`, payload)
      .then((r) => r.data),
}
