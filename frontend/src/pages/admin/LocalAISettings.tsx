import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'

type Status = {
  configured: boolean
  active: boolean
  verified: boolean
  model: string
  can_manage: boolean
}
export function LocalAISettings() {
  const cache = useQueryClient()
  const [message, setMessage] = useState('')
  const query = useQuery({
    queryKey: ['local-ai'],
    queryFn: async () => (await apiClient.get<Status>('/admin/local-llm')).data,
  })
  const action = useMutation({
    mutationFn: async (action: 'test' | 'activate') =>
      (await apiClient.post('/admin/local-llm', { action })).data,
    onSuccess: async (_, action) => {
      setMessage(
        action === 'test'
          ? 'Model javobi va JSON formati tekshirildi.'
          : 'Ochiq model asosiy AI sifatida yoqildi.',
      )
      await Promise.all([
        cache.invalidateQueries({ queryKey: ['local-ai'] }),
        cache.invalidateQueries({ queryKey: ['admin-providers'] }),
        cache.invalidateQueries({ queryKey: ['anthropic-config'] }),
      ])
    },
    onError: (error) => setMessage(error.message),
  })
  const state = query.data
  const disabled = action.isPending || !state?.can_manage || !state?.configured
  return (
    <Card>
      <CardHeader>
        <CardTitle>Ochiq model · Qwen / Ollama</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3 text-sm">
          <p className="text-muted-foreground">
            O‘z AI serveringizdagi model suhbat, kontent reja va ssenariylar uchun
            ishlaydi. Token uchun tashqi API to‘lovi yo‘q; server xarajatlari alohida.
          </p>
          <p>
            Model: <strong>{state?.model ?? 'Qwen3 4B Instruct'}</strong>
          </p>
          <p role="status">
            {query.isLoading
              ? 'Yuklanmoqda…'
              : query.isError
                ? 'Holatni yuklab bo‘lmadi.'
                : state?.active
                  ? 'Holat: faol, asosiy AI'
                  : state?.configured
                    ? 'Holat: sinovga tayyor'
                    : 'Holat: alohida AI server hali ulanmagan'}
          </p>
          <p className="text-xs text-muted-foreground">
            Model o‘rnatilgan xususiy Ollama xizmatini tizim administratori ulaydi.
            Tekshiruvdan so‘ng superadmin yoqadi. Sinov natijasi 1 soat amal qiladi. Bu
            model video va ovoz generatsiyasini almashtirmaydi.
          </p>
          <div className="flex flex-wrap gap-3">
            <button
              className="rounded-md border border-border px-4 py-2 disabled:opacity-40"
              disabled={disabled}
              onClick={() => action.mutate('test')}
            >
              Modelni tekshirish
            </button>
            <button
              className="rounded-md bg-primary px-4 py-2 text-primary-foreground disabled:opacity-40"
              disabled={disabled || !state?.verified || state.active}
              onClick={() => action.mutate('activate')}
            >
              Asosiy AI sifatida yoqish
            </button>
          </div>
          {message && (
            <p role="status" className="break-words">
              {message}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
