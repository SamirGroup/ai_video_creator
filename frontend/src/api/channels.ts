import { apiClient } from './client'
import type {
  AdSenseAccount,
  ContentPreferences,
  ContentPreferencesInput,
  YoutubeChannel,
} from '@/types/channel'

// Endpoint groups: OAuth (Google), Channels, Preferences (SPEC 6). TODO: real API.
export const channelsApi = {
  list: () => apiClient.get<YoutubeChannel[]>('/channels').then((r) => r.data),

  get: (id: string) => apiClient.get<YoutubeChannel>(`/channels/${id}`).then((r) => r.data),

  sync: (id: string) =>
    apiClient.post<YoutubeChannel>(`/channels/${id}/sync`).then((r) => r.data),

  disconnect: (id: string) => apiClient.delete<void>(`/channels/${id}`).then((r) => r.data),

  /** Kicks off Google OAuth authorization-code + PKCE flow (FR-10). */
  getYoutubeAuthorizeUrl: () =>
    apiClient
      .get<{ authorize_url: string }>('/oauth/youtube/authorize')
      .then((r) => r.data),

  getAdsenseAuthorizeUrl: () =>
    apiClient
      .get<{ authorize_url: string }>('/oauth/adsense/authorize')
      .then((r) => r.data),

  getAdsenseAccount: () =>
    apiClient.get<AdSenseAccount | null>('/adsense-accounts/current').then((r) => r.data),

  disconnectAdsense: () =>
    apiClient.post<void>('/oauth/adsense/revoke').then((r) => r.data),

  getPreferences: (channelId: string) =>
    apiClient
      .get<ContentPreferences>(`/channels/${channelId}/preferences`)
      .then((r) => r.data),

  savePreferences: (channelId: string, input: ContentPreferencesInput) =>
    apiClient
      .post<ContentPreferences>(`/channels/${channelId}/preferences`, input)
      .then((r) => r.data),

  pausePreferences: (channelId: string) =>
    apiClient
      .post<ContentPreferences>(`/channels/${channelId}/preferences/pause`)
      .then((r) => r.data),

  resumePreferences: (channelId: string) =>
    apiClient
      .post<ContentPreferences>(`/channels/${channelId}/preferences/resume`)
      .then((r) => r.data),
}
