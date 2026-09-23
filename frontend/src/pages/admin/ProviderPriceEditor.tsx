import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { adminApi } from '@/api/admin'
import { Button } from '@/components/ui/Button'
import type { ProviderConfig } from '@/types/admin'
import { Input } from '@/components/ui/Input'
export function ProviderPriceEditor() {
  const client = useQueryClient()
  const providers = useQuery({
    queryKey: ['admin-providers'],
    queryFn: adminApi.listProviders,
  })
  const save = useMutation({
    mutationFn: ({ id, values }: { id: string; values: Partial<ProviderConfig> }) =>
      adminApi.updateProvider(id, values),
    onSuccess: () =>
      Promise.all(
        ['admin-providers', 'video-models', 'planning-budget'].map((key) =>
          client.invalidateQueries({ queryKey: [key] }),
        ),
      ),
  })
  return (
    <section className="space-y-3">
      <h2 className="font-semibold">AI provider prices</h2>
      {providers.data
        ?.filter((provider) => !['anthropic', 'ollama'].includes(provider.provider))
        .map((provider) => (
          <form
            key={provider.id}
            className="flex flex-wrap items-end gap-3 rounded border border-border p-3"
            onSubmit={(e) => {
              e.preventDefault()
              const data = new FormData(e.currentTarget)
              save.mutate({
                id: provider.id,
                values: {
                  unit_cost_usd: String(data.get('price')),
                  is_active: data.get('active') === 'on',
                  config: {
                    ...provider.config,
                    pricing_verified_on: String(data.get('verified')),
                    pricing_note: String(data.get('note')),
                    ...(provider.service === 'llm'
                      ? {
                          input_cost_per_1k_usd: String(data.get('input')),
                          output_cost_per_1k_usd: String(data.get('output')),
                        }
                      : {}),
                  },
                },
              })
            }}
          >
            <Input
              name="price"
              label={`${provider.display_name} · USD / ${provider.cost_unit}`}
              type="number"
              min="0"
              step="0.000001"
              defaultValue={provider.unit_cost_usd ?? ''}
              required
            />
            {provider.service === 'llm' && (
              <>
                <Input
                  name="input"
                  label="Input USD / 1,000 tokens"
                  type="number"
                  min="0"
                  step="0.000001"
                  defaultValue={String(provider.config?.input_cost_per_1k_usd ?? '')}
                  required
                />
                <Input
                  name="output"
                  label="Output USD / 1,000 tokens"
                  type="number"
                  min="0"
                  step="0.000001"
                  defaultValue={String(provider.config?.output_cost_per_1k_usd ?? '')}
                  required
                />
              </>
            )}
            <Input
              name="verified"
              label="Price verified on / Narx tekshirilgan sana"
              type="date"
              required
              defaultValue={String(provider.config?.pricing_verified_on ?? '')}
            />
            <Input
              name="note"
              label="Pricing note / Izoh"
              defaultValue={String(provider.config?.pricing_note ?? '')}
            />
            <label className="flex items-center gap-2">
              <input name="active" type="checkbox" defaultChecked={provider.is_active} />
              Active / Faol
            </label>
            <Button isLoading={save.isPending}>Save price</Button>
          </form>
        ))}
      {save.isSuccess && <p role="status">Saved / Saqlandi</p>}
      {save.isError && <p role="alert">{save.error.message}</p>}
    </section>
  )
}
