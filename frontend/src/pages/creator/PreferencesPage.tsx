import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { z } from 'zod'

import { CardSkeletonGrid, ErrorState } from '@/components/common/StateViews'
import { Button } from '@/components/ui/Button'
import { Card, CardContent } from '@/components/ui/Card'
import { Checkbox } from '@/components/ui/Checkbox'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { channelsApi } from '@/api/channels'
import { ApiError } from '@/api/client'
import { DEFAULT_LOCALE, LANGUAGES } from '@/i18n/registry'

const preferencesSchema = z.object({
  niche: z.string().min(1),
  language: z
    .string()
    .refine((code) => LANGUAGES.some((language) => language.code === code)),
  publish_timezone: z.string().min(1),
  publish_days: z.string().regex(/^\s*(\d+\s*(,\s*\d+\s*)*)?$/),
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

export function PreferencesPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [selectedChannel, setSelectedChannel] = useState('')
  const channelsQuery = useQuery({ queryKey: ['channels'], queryFn: channelsApi.list })
  const channelId = selectedChannel || channelsQuery.data?.[0]?.id || ''
  const preferencesQuery = useQuery({
    queryKey: ['preferences', channelId],
    enabled: Boolean(channelId),
    retry: false,
    queryFn: async () => {
      try {
        return await channelsApi.getPreferences(channelId)
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null
        throw error
      }
    },
  })

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<PreferencesFormInput, unknown, PreferencesFormValues>({
    resolver: zodResolver(preferencesSchema),
  })

  useEffect(() => {
    const data = preferencesQuery.data
    reset({
      niche: data?.niche ?? 'technology',
      language: data?.language ?? DEFAULT_LOCALE,
      custom_brief: data?.custom_brief ?? '',
      brand_voice: data?.brand_voice ?? '',
      video_duration_sec: data?.video_duration_sec ?? 60,
      frequency: data?.frequency ?? 'daily',
      publish_time_local: data?.publish_time_local ?? '12:00',
      publish_timezone:
        data?.publish_timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone,
      publish_days: data?.publish_days?.join(',') ?? '',
      youtube_privacy_status: data?.youtube_privacy_status ?? 'private',
      approval_mode: data?.approval_mode ?? 'review_required',
    })
  }, [preferencesQuery.data, channelId, reset])

  const saveMutation = useMutation({
    mutationFn: (values: PreferencesFormValues) => {
      const payload = {
        ...values,
        custom_brief: values.custom_brief ?? '',
        brand_voice: values.brand_voice ?? '',
        publish_days:
          values.frequency === 'daily' || !values.publish_days.trim()
            ? null
            : values.publish_days.split(',').map((day) => Number(day.trim())),
      }
      return preferencesQuery.data
        ? channelsApi.updatePreferences(channelId, payload)
        : channelsApi.savePreferences(channelId, {
            ...payload,
            banned_topics: [],
            youtube_category_id: '22',
            made_for_kids: false,
            auto_publish_on_timeout: false,
            is_paused: false,
          })
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(['preferences', channelId], updated)
    },
    onError: (error) => setError('root', { message: error.message }),
  })

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-foreground">{t('preferences.title')}</h1>

      {channelsQuery.isLoading && <CardSkeletonGrid count={1} />}
      {channelsQuery.isError && <ErrorState onRetry={() => channelsQuery.refetch()} />}
      {channelsQuery.data?.length === 0 && <p>{t('dashboard.connectChannel')}</p>}
      {Boolean(channelsQuery.data?.length) && (
        <Select
          label={t('nav.channel')}
          value={channelId}
          disabled={saveMutation.isPending}
          options={(channelsQuery.data ?? []).map((channel) => ({
            value: channel.id,
            label: channel.channel_title,
          }))}
          onChange={(event) => {
            setSelectedChannel(event.target.value)
            saveMutation.reset()
          }}
        />
      )}
      {preferencesQuery.isLoading && <CardSkeletonGrid count={1} />}
      {preferencesQuery.isError && (
        <ErrorState onRetry={() => preferencesQuery.refetch()} />
      )}

      {channelId && preferencesQuery.isSuccess && (
        <Card>
          <CardContent className="pt-5">
            <form
              className="grid grid-cols-1 gap-4 sm:grid-cols-2"
              onSubmit={handleSubmit((values) => saveMutation.mutate(values))}
              noValidate
            >
              <Select
                label={t('preferences.language')}
                options={LANGUAGES.map((language) => ({
                  value: language.code,
                  label: language.native_name,
                }))}
                {...register('language')}
              />
              <Input
                label={t('preferences.niche')}
                error={errors.niche ? t('common.error.generic') : undefined}
                required
                {...register('niche')}
              />
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
              <Input
                label={t('preferences.timezone')}
                {...register('publish_timezone')}
              />
              <Input
                label={t('preferences.publishDays')}
                error={errors.publish_days ? t('common.error.generic') : undefined}
                {...register('publish_days')}
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
                <Checkbox
                  label={t('preferences.paused')}
                  disabled
                  defaultChecked={preferencesQuery.data?.is_paused ?? false}
                />
              </div>

              {errors.root && (
                <p role="alert" className="text-destructive-600 sm:col-span-2">
                  {errors.root.message}
                </p>
              )}
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
