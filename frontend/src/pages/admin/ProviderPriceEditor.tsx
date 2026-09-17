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
    onSuccess: () => client.invalidateQueries({ queryKey: ['admin-providers'] }),
  })
  return (
    <section className="space-y-3">
      <h2 className="font-semibold">AI provider prices</h2>
      {providers.data?.map((provider) => (
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
                ...(provider.service === 'llm'
                  ? {
                      config: {
                        ...provider.config,
                        input_cost_per_1k_usd: String(data.get('input')),
                        output_cost_per_1k_usd: String(data.get('output')),
                      },
                    }
                  : {}),
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
          <Button isLoading={save.isPending}>Save price</Button>
        </form>
      ))}
      {save.isError && <p role="alert">{save.error.message}</p>}
    </section>
  )
}
