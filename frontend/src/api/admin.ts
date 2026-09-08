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
    apiClient.get<FinanceOverview>('/admin/finance/overview').then((r) => r.data),

  financeExportUrl: () => '/api/v1/admin/finance/export',

  listPlans: () => apiClient.get<Plan[]>('/admin/plans').then((r) => r.data),

  updatePlan: (id: string, payload: Partial<Plan>) =>
    apiClient.patch<Plan>(`/admin/plans/${id}`, payload).then((r) => r.data),

  listProviders: () =>
    apiClient.get<ProviderConfig[]>('/admin/providers').then((r) => r.data),

  updateProvider: (id: string, payload: Partial<ProviderConfig>) =>
    apiClient.patch<ProviderConfig>(`/admin/providers/${id}`, payload).then((r) => r.data),
}
