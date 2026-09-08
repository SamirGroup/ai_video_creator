import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { videoKeys } from '@/lib/queryKeys'
import { mockFetch } from '@/mocks/mockFetch'
import { mockVideoSteps, mockVideos } from '@/mocks/fixtures'
import type { RejectVideoPayload, RequestChangesPayload, VideoJob } from '@/types/video'

// TODO: real API — swap `mockFetch(...)` for the matching `videosApi.*` call
// (see src/api/videos.ts) once `GET/POST /videos/*` is live. Query keys and
// cache-update logic below already match the real contract.

export function useVideoList() {
  return useQuery({
    queryKey: videoKeys.list({}),
    queryFn: () => mockFetch(mockVideos),
  })
}

export function useVideoDetail(id: string | undefined) {
  return useQuery({
    queryKey: videoKeys.detail(id ?? ''),
    queryFn: () => mockFetch(mockVideos.find((v) => v.id === id) ?? null),
    enabled: Boolean(id),
  })
}

export function useVideoSteps(id: string | undefined) {
  return useQuery({
    queryKey: videoKeys.steps(id ?? ''),
    queryFn: () => mockFetch(mockVideoSteps[id ?? ''] ?? []),
    enabled: Boolean(id),
  })
}

function useUpdateVideoCache(id: string) {
  const queryClient = useQueryClient()
  return (updater: (current: VideoJob) => VideoJob) => {
    const current = queryClient.getQueryData<VideoJob | null>(videoKeys.detail(id))
    if (!current) return
    const updated = updater(current)
    queryClient.setQueryData(videoKeys.detail(id), updated)
    queryClient.setQueryData<VideoJob[]>(videoKeys.list({}), (list) =>
      list?.map((v) => (v.id === id ? updated : v)),
    )
  }
}

export function useApproveVideo(id: string) {
  const applyUpdate = useUpdateVideoCache(id)
  return useMutation({
    mutationFn: () => mockFetch(null, 500),
    onSuccess: () => applyUpdate((v) => ({ ...v, status: 'upload_queued' })),
  })
}

export function useRequestChangesVideo(id: string) {
  const applyUpdate = useUpdateVideoCache(id)
  return useMutation({
    mutationFn: (_payload: RequestChangesPayload) => mockFetch(null, 500),
    onSuccess: () => applyUpdate((v) => ({ ...v, status: 'changes_requested' })),
  })
}

export function useRejectVideo(id: string) {
  const applyUpdate = useUpdateVideoCache(id)
  return useMutation({
    mutationFn: (_payload: RejectVideoPayload) => mockFetch(null, 500),
    onSuccess: () => applyUpdate((v) => ({ ...v, status: 'rejected' })),
  })
}
