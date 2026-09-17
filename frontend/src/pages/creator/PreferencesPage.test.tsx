// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { channelsApi } from '@/api/channels'
import { ApiError } from '@/api/client'
import i18n from '@/i18n'
import { PreferencesPage } from './PreferencesPage'
import type { ContentPreferences, YoutubeChannel } from '@/types/channel'

vi.mock('@/api/channels', () => ({
  channelsApi: {
    list: vi.fn(),
    getPreferences: vi.fn(),
    savePreferences: vi.fn(),
    updatePreferences: vi.fn(),
  },
}))
const existing: ContentPreferences = {
  id: 'pref',
  channel_id: 'channel',
  niche: 'technology',
  language: 'en',
  custom_brief: '',
  brand_voice: '',
  banned_topics: [],
  video_duration_sec: 60,
  frequency: 'daily',
  publish_time_local: '12:00',
  publish_timezone: 'UTC',
  publish_days: null,
  youtube_privacy_status: 'private',
  youtube_category_id: '22',
  made_for_kids: false,
  approval_mode: 'review_required',
  auto_publish_on_timeout: false,
  is_paused: false,
}
function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <PreferencesPage />
    </QueryClientProvider>,
  )
}
beforeEach(async () => {
  vi.resetAllMocks()
  await i18n.changeLanguage('en')
  vi.mocked(channelsApi.list).mockResolvedValue([
    { id: 'channel', channel_title: 'My channel' } as YoutubeChannel,
  ])
})
afterEach(cleanup)

it('sends changed content language through PATCH for existing preferences', async () => {
  vi.mocked(channelsApi.getPreferences).mockResolvedValue(existing)
  vi.mocked(channelsApi.updatePreferences).mockResolvedValue({
    ...existing,
    language: 'ar-EG',
  })
  mount()
  const language = await screen.findByLabelText('Content language')
  fireEvent.change(language, { target: { value: 'ar-EG' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save preferences' }))
  await waitFor(() =>
    expect(channelsApi.updatePreferences).toHaveBeenCalledWith(
      'channel',
      expect.objectContaining({ language: 'ar-EG' }),
    ),
  )
  expect(channelsApi.savePreferences).not.toHaveBeenCalled()
})

it('creates preferences after 404 and includes required schedule fields', async () => {
  vi.mocked(channelsApi.getPreferences).mockRejectedValue(new ApiError(404, null, null))
  vi.mocked(channelsApi.savePreferences).mockResolvedValue(existing)
  mount()
  await screen.findByLabelText('Content language')
  fireEvent.click(screen.getByRole('button', { name: 'Save preferences' }))
  await waitFor(() =>
    expect(channelsApi.savePreferences).toHaveBeenCalledWith(
      'channel',
      expect.objectContaining({
        language: 'ru',
        publish_timezone: expect.any(String),
        approval_mode: 'review_required',
      }),
    ),
  )
})

it('shows API rejection instead of claiming settings were saved', async () => {
  vi.mocked(channelsApi.getPreferences).mockResolvedValue(existing)
  vi.mocked(channelsApi.updatePreferences).mockRejectedValue(
    new Error('Plan duration limit exceeded'),
  )
  mount()
  await screen.findByLabelText('Content language')
  fireEvent.click(screen.getByRole('button', { name: 'Save preferences' }))
  expect((await screen.findByRole('alert')).textContent).toContain(
    'Plan duration limit exceeded',
  )
  expect(screen.queryByText('Preferences saved.')).toBeNull()
})
