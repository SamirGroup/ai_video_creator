import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { z } from 'zod'

import { CardSkeletonGrid, ErrorState } from '@/components/common/StateViews'
import { Button } from '@/components/ui/Button'
import { Card, CardContent } from '@/components/ui/Card'
import { Checkbox } from '@/components/ui/Checkbox'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { mockPreferences } from '@/mocks/fixtures'
import { mockFetch } from '@/mocks/mockFetch'
import type { ContentPreferences } from '@/types/channel'

const preferencesSchema = z.object({
  niche: z.string().min(1),
  custom_brief: z.string().nullable().optional(),
  brand_voice: z.string().nullable().optional(),
  video_duration_sec: z.coerce.number().min(30).max(600),
  frequency: z.enum(['daily', 'weekly', 'monthly']),
  publish_time_local: z.string().min(1),
  youtube_privacy_status: z.enum(['public', 'unlisted', 'private']),
  approval_mode: z.enum(['review_required', 'auto']),
})

// `video_duration_sec` uses `z.coerce`, so the schema's *input* type (raw form
// values, e.g. a string from an <input type="number">) differs from its
// *output* type (validated `number`) — useForm's 3rd generic tells
// `handleSubmit` to hand the callback the coerced output.
type PreferencesFormInput = z.input<typeof preferencesSchema>
type PreferencesFormValues = z.output<typeof preferencesSchema>

// TODO: real API — replace with channelsApi.getPreferences/savePreferences (src/api/channels.ts)
function usePreferences() {
  return useQuery({ queryKey: ['preferences'], queryFn: () => mockFetch(mockPreferences) })
}

export function PreferencesPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const preferencesQuery = usePreferences()

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<PreferencesFormInput, unknown, PreferencesFormValues>({
    resolver: zodResolver(preferencesSchema),
  })

  useEffect(() => {
    if (preferencesQuery.data) reset(preferencesQuery.data)
  }, [preferencesQuery.data, reset])

  const saveMutation = useMutation({
    mutationFn: (values: PreferencesFormValues) =>
      mockFetch({ ...preferencesQuery.data, ...values } as ContentPreferences, 500),
    onSuccess: (updated) => queryClient.setQueryData(['preferences'], updated),
  })

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-foreground">{t('preferences.title')}</h1>

      {preferencesQuery.isLoading && <CardSkeletonGrid count={1} />}
      {preferencesQuery.isError && <ErrorState onRetry={() => preferencesQuery.refetch()} />}

      {preferencesQuery.data && (
        <Card>
          <CardContent className="pt-5">
            <form
              className="grid grid-cols-1 gap-4 sm:grid-cols-2"
              onSubmit={handleSubmit((values) => saveMutation.mutate(values))}
              noValidate
            >
              <Input label={t('preferences.niche')} required {...register('niche')} />
              <Input
                type="number"
                label={t('preferences.videoDuration')}
                min={30}
                max={600}
                required
                error={errors.video_duration_sec?.message}
                {...register('video_duration_sec')}
              />
              <Select
                label={t('preferences.frequency')}
                options={[
                  { value: 'daily', label: t('preferences.frequencyOptions.daily') },
                  { value: 'weekly', label: t('preferences.frequencyOptions.weekly') },
                  { value: 'monthly', label: t('preferences.frequencyOptions.monthly') },
                ]}
                {...register('frequency')}
              />
              <Input
                type="time"
                label={t('preferences.publishTime')}
                required
                {...register('publish_time_local')}
              />
              <Select
                label={t('preferences.privacyStatus')}
                options={[
                  { value: 'public', label: t('preferences.privacyOptions.public') },
                  { value: 'unlisted', label: t('preferences.privacyOptions.unlisted') },
                  { value: 'private', label: t('preferences.privacyOptions.private') },
                ]}
                {...register('youtube_privacy_status')}
              />
              <Select
                label={t('preferences.approvalMode')}
                options={[
                  {
                    value: 'review_required',
                    label: t('preferences.approvalModeOptions.review_required'),
                  },
                  { value: 'auto', label: t('preferences.approvalModeOptions.auto') },
                ]}
                {...register('approval_mode')}
              />

              <div className="sm:col-span-2">
                <label
                  htmlFor="custom_brief"
                  className="mb-1.5 block text-sm font-medium text-foreground"
                >
                  {t('preferences.customBrief')}
                </label>
                <textarea
                  id="custom_brief"
                  rows={2}
                  className="w-full rounded-md border border-border bg-surface p-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  {...register('custom_brief')}
                />
              </div>

              <div className="sm:col-span-2">
                <label
                  htmlFor="brand_voice"
                  className="mb-1.5 block text-sm font-medium text-foreground"
                >
                  {t('preferences.brandVoice')}
                </label>
                <textarea
                  id="brand_voice"
                  rows={2}
                  className="w-full rounded-md border border-border bg-surface p-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  {...register('brand_voice')}
                />
              </div>

              <div className="sm:col-span-2">
                <Checkbox label={t('preferences.paused')} disabled defaultChecked={preferencesQuery.data.is_paused} />
              </div>

              <div className="sm:col-span-2 flex items-center gap-3">
                <Button type="submit" isLoading={saveMutation.isPending}>
                  {t('preferences.save')}
                </Button>
                {saveMutation.isSuccess && (
                  <p role="status" className="text-sm text-success-700">
                    {t('preferences.saved')}
                  </p>
                )}
              </div>
            </form>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
