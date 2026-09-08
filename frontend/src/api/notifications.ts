import { apiClient } from './client'
import type { NotificationItem, NotificationPreference } from '@/types/notification'

// Endpoint group: Notifications (SPEC 6, FR-74..FR-77). TODO: real API.
export const notificationsApi = {
  list: () => apiClient.get<NotificationItem[]>('/notifications').then((r) => r.data),

  markRead: (id: string) =>
    apiClient.post<void>(`/notifications/${id}/read`).then((r) => r.data),

  markAllRead: () => apiClient.post<void>('/notifications/read-all').then((r) => r.data),

  getPreferences: () =>
    apiClient.get<NotificationPreference[]>('/notifications/preferences').then((r) => r.data),

  updatePreferences: (prefs: NotificationPreference[]) =>
    apiClient
      .patch<NotificationPreference[]>('/notifications/preferences', prefs)
      .then((r) => r.data),
}
