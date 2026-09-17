import { collectPages } from './pagination'
import { apiClient } from './client'
import type { CursorPage } from '@/types/common'
import type {
  RejectVideoPayload,
  RequestChangesPayload,
  UpdateVideoMetadataPayload,
  VideoJob,
  VideoJobStep,
  VideoListFilters,
} from '@/types/video'

// Endpoint group: Video jobs (SPEC 6, status model SPEC 7.2). TODO: real API.
export const videosApi = {
  listAll: (filters: VideoListFilters = {}) => collectPages<VideoJob>('/videos', filters),
  preview: (id: string) =>
    apiClient
      .get<{ preview_url: string; expires_at: string }>(`/videos/${id}/preview`)
      .then((r) => r.data),
  list: (filters: VideoListFilters = {}) =>
    apiClient
      .get<CursorPage<VideoJob>>('/videos', { params: filters })
      .then((r) => r.data),

  get: (id: string) => apiClient.get<VideoJob>(`/videos/${id}`).then((r) => r.data),

  steps: (id: string) => collectPages<VideoJobStep>(`/videos/${id}/steps`),

  generateNow: (channel_id?: string) =>
    apiClient.post<VideoJob>('/videos/generate', { channel_id }).then((r) => r.data),

  cancel: (id: string) =>
    apiClient.post<VideoJob>(`/videos/${id}/cancel`).then((r) => r.data),

  updateMetadata: (id: string, payload: UpdateVideoMetadataPayload) =>
    apiClient.patch<VideoJob>(`/videos/${id}/metadata`, payload).then((r) => r.data),

  approve: (id: string) =>
    apiClient.post<VideoJob>(`/videos/${id}/approve`).then((r) => r.data),

  requestChanges: (id: string, payload: RequestChangesPayload) =>
    apiClient
      .post<VideoJob>(`/videos/${id}/request-changes`, {
        comment: payload.reason,
        restart_stage: payload.regenerate_from,
      })
      .then((r) => r.data),

  reject: (id: string, payload: RejectVideoPayload) =>
    apiClient.post<VideoJob>(`/videos/${id}/reject`, payload).then((r) => r.data),
}
