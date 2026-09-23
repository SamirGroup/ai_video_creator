import { useEffect, useRef, useState } from 'react'
import { ClaudeConnectionOptions } from './ClaudeConnectionOptions'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'

type Config = {
  configured: boolean
  active: boolean
  primary: boolean
  verified: boolean
  can_manage?: boolean
  model: string
  input_per_million: string
  output_per_million: string
  test_cost_usd?: string
}

export function AnthropicSettings() {
  const apiInput = useRef<HTMLInputElement>(null)
  const [showApi, setShowApi] = useState(false)
  const cache = useQueryClient()
  const query = useQuery({
    queryKey: ['anthropic-config'],
    queryFn: async () => (await apiClient.get<Config>('/admin/anthropic')).data,
  })
  const [key, setKey] = useState('')
  const [model, setModel] = useState('claude-sonnet-4-5')
  const [input, setInput] = useState('3')
  const [output, setOutput] = useState('15')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  useEffect(() => {
    if (query.data) {
      setModel(query.data.model)
      setInput(query.data.input_per_million)
      setOutput(query.data.output_per_million)
    }
  }, [query.data])
  const dirty =
    !!key ||
    model !== query.data?.model ||
    input !== query.data?.input_per_million ||
    output !== query.data?.output_per_million
  async function action(action: 'save' | 'test' | 'activate') {
    setBusy(true)
    setMessage('')
    try {
      const response = await apiClient.post<Config>(
        '/admin/anthropic',
        action === 'save'
          ? {
              action,
              model,
              input_per_million: input,
              output_per_million: output,
              ...(key ? { api_key: key } : {}),
            }
          : { action },
      )
      setMessage(
        action === 'test'
          ? `Ulanish tekshirildi. Taxminiy API xarajati: $${response.data.test_cost_usd}.`
          : action === 'activate'
            ? 'Claude asosiy AI sifatida yoqildi.'
            : 'Saqlandi. Endi ulanishni tekshiring.',
      )
      await Promise.all([
        cache.invalidateQueries({ queryKey: ['anthropic-config'] }),
        cache.invalidateQueries({ queryKey: ['admin-providers'] }),
      ])
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'So‘rov bajarilmadi.')
    } finally {
      setKey('')
      setBusy(false)
    }
  }
  const apiVisible = showApi || !!query.data?.configured
  useEffect(() => {
    if (showApi) apiInput.current?.focus()
  }, [showApi])
  const disabled = busy || !query.data?.can_manage
  const field = 'w-full rounded-md border border-border bg-background px-3 py-2 text-sm'
  return (
    <Card>
      <CardHeader>
        <CardTitle>Claude · Ulanish sozlamalari</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Suhbat, kontent reja va ssenariylar uchun bevosita Anthropic API. Claude
            obunasidan alohida API balans talab qilinadi.{' '}
            <a
              className="text-primary underline"
              href="https://platform.claude.com/"
              target="_blank"
              rel="noreferrer"
            >
              Anthropic konsoli
            </a>
          </p>
          <p className="text-sm" role="status">
            {query.isLoading
              ? 'Yuklanmoqda…'
              : query.isError
                ? 'Sozlamalarni yuklab bo‘lmadi.'
                : query.data?.active && query.data?.primary
                  ? 'Holat: faol, asosiy AI'
                  : query.data?.verified
                    ? 'Holat: tekshirilgan, yoqishga tayyor'
                    : query.data?.configured
                      ? 'Holat: saqlangan, tekshiruv kerak'
                      : 'Holat: kalit kiritilmagan'}
          </p>
          {!query.isLoading && !query.data?.can_manage && (
            <p className="text-sm text-muted-foreground">
              O‘zgartirish uchun ikki bosqichli himoyasi yoqilgan superadmin kerak.
            </p>
          )}
          <ClaudeConnectionOptions
            onApi={() => {
              setShowApi(true)
              requestAnimationFrame(() => apiInput.current?.focus())
            }}
          />
          {apiVisible && (
            <>
              <fieldset disabled={disabled} className="grid gap-4 sm:grid-cols-2">
                <label className="space-y-1 text-sm">
                  API key
                  <input
                    className={field}
                    ref={apiInput}
                    type="password"
                    autoComplete="new-password"
                    spellCheck={false}
                    value={key}
                    onChange={(e) => setKey(e.target.value)}
                    placeholder={
                      query.data?.configured
                        ? 'Saqlangan. Almashtirish uchun yangi kalit'
                        : 'sk-ant-…'
                    }
                  />
                </label>
                <label className="space-y-1 text-sm">
                  Claude model ID
                  <input
                    className={field}
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                  />
                </label>
                <label className="space-y-1 text-sm">
                  Input / 1 million token (USD)
                  <input
                    className={field}
                    type="number"
                    min="0.0001"
                    step="0.0001"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                  />
                </label>
                <label className="space-y-1 text-sm">
                  Output / 1 million token (USD)
                  <input
                    className={field}
                    type="number"
                    min="0.0001"
                    step="0.0001"
                    value={output}
                    onChange={(e) => setOutput(e.target.value)}
                  />
                </label>
              </fieldset>
              <p className="text-xs text-muted-foreground">
                Kalit shifrlanib saqlanadi va qayta ko‘rsatilmaydi. Faol sozlamani saqlash
                Claude’ni qayta tekshirilib yoqilguncha to‘xtatadi. Narxlarni tanlangan
                modelning rasmiy tarifi bilan moslang.
              </p>
              <div className="flex flex-wrap gap-3">
                <button
                  className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-40"
                  disabled={disabled}
                  onClick={() => void action('save')}
                >
                  1. Saqlash
                </button>
                <button
                  className="rounded-md border border-border px-4 py-2 text-sm disabled:opacity-40"
                  disabled={disabled || !query.data?.configured || dirty}
                  onClick={() => void action('test')}
                >
                  2. API sinovi (kichik sarf)
                </button>
                <button
                  className="rounded-md border border-border px-4 py-2 text-sm disabled:opacity-40"
                  disabled={
                    disabled ||
                    !query.data?.verified ||
                    dirty ||
                    (query.data.active && query.data.primary)
                  }
                  onClick={() => void action('activate')}
                >
                  3. Asosiy AI sifatida yoqish
                </button>
              </div>
            </>
          )}
          {message && (
            <p role="status" className="break-words text-sm">
              {message}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
