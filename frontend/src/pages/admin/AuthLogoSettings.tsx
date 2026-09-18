import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { authLogosApi, type AuthLogo } from '@/api/authLogos'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'

const empty = { name: '', image_url: '', link_url: '', sort_order: 0, is_active: true }
export function AuthLogoSettings() {
  const client = useQueryClient()
  const [id, setId] = useState<number>()
  const [draft, setDraft] = useState<Omit<AuthLogo, 'id'>>(empty)
  const logos = useQuery({ queryKey: ['admin-auth-logos'], queryFn: authLogosApi.list })
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ['admin-auth-logos'] })
    void client.invalidateQueries({ queryKey: ['public-auth-logos'] })
  }
  const save = useMutation({
    mutationFn: () => authLogosApi.save(draft, id),
    onSuccess: () => {
      refresh()
      setId(undefined)
      setDraft(empty)
    },
  })
  const remove = useMutation({
    mutationFn: authLogosApi.remove,
    onSuccess: (_, deleted) => {
      refresh()
      if (id === deleted) {
        setId(undefined)
        setDraft(empty)
      }
    },
  })
  return (
    <section className="rounded-xl border border-border bg-surface p-5">
      <h2 className="mb-2 text-lg font-semibold">Animatsiya logotiplari</h2>
      <p className="mb-5 text-sm text-muted-foreground">
        Login va signup fonidagi AI logotiplari. Rasm va sahifa uchun HTTPS havolasini
        kiriting.
      </p>
      {logos.isError && (
        <p role="alert">
          Faqat 2FA yoqilgan superadmin boshqara oladi. Ro‘yxatni yuklab bo‘lmadi.
        </p>
      )}
      <form
        className="grid gap-4 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault()
          save.mutate()
        }}
      >
        <Input
          label="Nomi"
          required
          maxLength={100}
          value={draft.name}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })}
        />
        <Input
          label="Logotip rasmi URL (HTTPS)"
          type="url"
          required
          value={draft.image_url}
          onChange={(e) => setDraft({ ...draft, image_url: e.target.value })}
        />
        <Input
          label="AI sahifasi havolasi (HTTPS)"
          type="url"
          required
          value={draft.link_url}
          onChange={(e) => setDraft({ ...draft, link_url: e.target.value })}
        />
        <Input
          label="Tartib"
          type="number"
          min={0}
          required
          value={draft.sort_order}
          onChange={(e) => setDraft({ ...draft, sort_order: Number(e.target.value) })}
        />
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={draft.is_active}
            onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })}
          />
          Faol
        </label>
        <div className="flex gap-3">
          <Button type="submit" isLoading={save.isPending}>
            {id ? 'Saqlash' : 'Qo‘shish'}
          </Button>
          {id && (
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setId(undefined)
                setDraft(empty)
              }}
            >
              Bekor qilish
            </Button>
          )}
        </div>
      </form>
      {(save.isError || remove.isError) && (
        <p role="alert" className="mt-3 text-destructive-600">
          Saqlanmadi. HTTPS havolalar va superadmin ruxsatini tekshiring.
        </p>
      )}
      <div className="mt-6 grid gap-3">
        {logos.data?.map((logo) => (
          <div
            key={logo.id}
            className="flex flex-wrap items-center gap-3 rounded-lg border border-border p-3"
          >
            <img
              src={logo.image_url}
              alt={logo.name}
              referrerPolicy="no-referrer"
              className="h-10 w-10 object-contain"
            />
            <a
              className="min-w-0 flex-1 break-words text-primary-600"
              href={logo.link_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              {logo.name}
              {!logo.is_active && ' (yashirilgan)'}
            </a>
            <Button
              variant="secondary"
              onClick={() => {
                setId(logo.id)
                setDraft(logo)
              }}
            >
              Tahrirlash / almashtirish
            </Button>
            <Button
              variant="secondary"
              disabled={remove.isPending}
              onClick={() => remove.mutate(logo.id)}
            >
              O‘chirish
            </Button>
          </div>
        ))}
      </div>
    </section>
  )
}
