import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, Handshake, ImageIcon } from 'lucide-react'
import { partnersApi, type Partner, type PartnerBanner } from '@/api/partners'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'

const empty: Omit<Partner, 'id'> = {
  name: '',
  image_url: '',
  link_url: '',
  caption: '',
  sort_order: 0,
  is_active: true,
  is_affiliate: false,
}
const defaults: PartnerBanner = {
  enabled: true,
  title: 'Hamkorlarimiz',
  subtitle: 'Biz bilan hamkorlik qilayotgan tashkilotlar va xizmatlar',
  animation_enabled: true,
  animation_seconds: 35,
}

function Logo({ url, name }: { url: string; name: string }) {
  const [failedUrl, setFailedUrl] = useState('')
  return (
    <div className="flex h-16 w-32 shrink-0 items-center justify-center rounded-lg bg-white p-3">
      {url && failedUrl !== url ? (
        <img
          src={url}
          alt={name || 'Logotip namunasi'}
          className="max-h-full max-w-full object-contain"
          referrerPolicy="no-referrer"
          onError={() => setFailedUrl(url)}
        />
      ) : (
        <ImageIcon className="text-neutral-400" />
      )}
    </div>
  )
}

export function PartnersPage() {
  const cache = useQueryClient()
  const partners = useQuery({ queryKey: ['admin-partners'], queryFn: partnersApi.list })
  const settings = useQuery({ queryKey: ['partner-banner'], queryFn: partnersApi.banner })
  const [bannerDraft, setBanner] = useState<PartnerBanner | null>(null)
  const banner = bannerDraft ?? settings.data ?? defaults
  const [draft, setDraft] = useState(empty)
  const [id, setId] = useState<number>()
  const [notice, setNotice] = useState('')
  const [deleting, setDeleting] = useState<number>()
  const refresh = () => cache.invalidateQueries({ queryKey: ['admin-partners'] })
  const save = useMutation({
    mutationFn: () => partnersApi.save(draft, id),
    onSuccess: async () => {
      setDraft(empty)
      setId(undefined)
      setNotice('Hamkor saqlandi. Bosh sahifani yangilab ko‘ring.')
      await refresh()
    },
  })
  const remove = useMutation({
    mutationFn: partnersApi.remove,
    onSuccess: async (_, deleted) => {
      setDeleting(undefined)
      if (id === deleted) {
        setId(undefined)
        setDraft(empty)
      }
      setNotice('Hamkor o‘chirildi.')
      await refresh()
    },
  })
  const saveBanner = useMutation({
    mutationFn: () => partnersApi.saveBanner(banner),
    onSuccess: async () => {
      setNotice('Banner sozlamalari saqlandi.')
      await cache.invalidateQueries({ queryKey: ['partner-banner'] })
      setBanner(null)
    },
  })
  const loading = partners.isLoading || settings.isLoading
  const unavailable = partners.isError || settings.isError
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-2 flex items-center gap-2 text-sm text-primary">
            <Handshake size={18} />
            Hamkorlik va reklama
          </p>
          <h1 className="text-2xl font-semibold">Hamkorlar</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            Bosh sahifadagi hamkorlar banneri, logotiplar va referral havolalarini
            boshqaring.
          </p>
        </div>
        <a
          href="/"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm"
        >
          Saytni ko‘rish
          <ExternalLink size={16} />
        </a>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {[
          ['Jami hamkorlar', partners.data?.length ?? 0],
          ['Faol', partners.data?.filter((p) => p.is_active).length ?? 0],
          [
            'Referral havolalar',
            partners.data?.filter((p) => p.is_affiliate).length ?? 0,
          ],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border border-border bg-card p-4">
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className="mt-1 text-2xl font-semibold">{value}</p>
          </div>
        ))}
      </div>
      {loading && <p role="status">Yuklanmoqda…</p>}
      {unavailable && (
        <p role="alert">
          Sozlamalarni yuklab bo‘lmadi. Admin ruxsati va ikki bosqichli himoyani
          tekshiring.
        </p>
      )}
      {notice && (
        <p
          role="status"
          className="rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm"
        >
          {notice}
        </p>
      )}
      {(save.isError || remove.isError || saveBanner.isError) && (
        <p role="alert" className="text-sm text-red-500">
          Amal bajarilmadi. Maydonlarni, HTTPS havolalarni va kirish ruxsatini tekshiring.
        </p>
      )}
      <div className="grid items-start gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Banner ko‘rinishi</CardTitle>
          </CardHeader>
          <CardContent>
            <form
              className="space-y-4"
              onSubmit={(e) => {
                e.preventDefault()
                setNotice('')
                saveBanner.mutate()
              }}
            >
              <fieldset
                disabled={loading || unavailable || saveBanner.isPending}
                className="space-y-4"
              >
                <Input
                  label="Banner sarlavhasi"
                  required
                  maxLength={120}
                  value={banner.title}
                  onChange={(e) => setBanner({ ...banner, title: e.target.value })}
                />
                <Input
                  label="Banner tavsifi"
                  maxLength={240}
                  value={banner.subtitle}
                  onChange={(e) => setBanner({ ...banner, subtitle: e.target.value })}
                />
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={banner.enabled}
                    onChange={(e) => setBanner({ ...banner, enabled: e.target.checked })}
                  />
                  Bosh sahifada ko‘rsatish
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={banner.animation_enabled}
                    onChange={(e) =>
                      setBanner({ ...banner, animation_enabled: e.target.checked })
                    }
                  />
                  Logotiplar animatsiyasi
                </label>
                <Input
                  label="Bir aylanish vaqti (soniya)"
                  type="number"
                  min={15}
                  max={120}
                  required
                  value={banner.animation_seconds}
                  onChange={(e) =>
                    setBanner({ ...banner, animation_seconds: Number(e.target.value) })
                  }
                />
                <p className="text-xs text-muted-foreground">
                  Katta qiymat — sekinroq harakat. Tashrifchi animatsiyani to‘xtata oladi;
                  kamaytirilgan harakat sozlamasi ham hisobga olinadi.
                </p>
                <Button type="submit" isLoading={saveBanner.isPending}>
                  Banner sozlamalarini saqlash
                </Button>
              </fieldset>
            </form>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{id ? 'Hamkorni tahrirlash' : 'Yangi hamkor'}</CardTitle>
          </CardHeader>
          <CardContent>
            <form
              className="space-y-4"
              onSubmit={(e) => {
                e.preventDefault()
                setNotice('')
                save.mutate()
              }}
            >
              <fieldset
                disabled={loading || unavailable || save.isPending}
                className="space-y-4"
              >
                <Input
                  label="Tashkilot nomi"
                  required
                  maxLength={100}
                  value={draft.name}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                />
                <Input
                  label="Logotip URL (HTTPS)"
                  type="url"
                  required
                  maxLength={2000}
                  value={draft.image_url}
                  onChange={(e) => setDraft({ ...draft, image_url: e.target.value })}
                />
                <Input
                  label="Sayt yoki referral URL (HTTPS)"
                  type="url"
                  required
                  maxLength={2000}
                  value={draft.link_url}
                  onChange={(e) => setDraft({ ...draft, link_url: e.target.value })}
                />
                <Input
                  label="Qisqa tavsif"
                  maxLength={160}
                  value={draft.caption}
                  onChange={(e) => setDraft({ ...draft, caption: e.target.value })}
                />
                <Input
                  label="Tartib"
                  type="number"
                  min={0}
                  required
                  value={draft.sort_order}
                  onChange={(e) =>
                    setDraft({ ...draft, sort_order: Number(e.target.value) })
                  }
                />
                <div className="flex flex-wrap gap-4">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={draft.is_active}
                      onChange={(e) =>
                        setDraft({ ...draft, is_active: e.target.checked })
                      }
                    />
                    Faol
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={draft.is_affiliate}
                      onChange={(e) =>
                        setDraft({ ...draft, is_affiliate: e.target.checked })
                      }
                    />
                    Referral / komissiyali havola
                  </label>
                </div>
                <div className="flex items-center gap-3 rounded-xl border border-border p-3">
                  <Logo url={draft.image_url} name={draft.name} />
                  <div className="min-w-0">
                    <p className="break-words font-medium">
                      {draft.name || 'Logotip ko‘rinishi'}
                    </p>
                    <p className="break-words text-xs text-muted-foreground">
                      {draft.caption || 'Rasm yuklanmasa tashkilot nomi ko‘rsatiladi.'}
                    </p>
                  </div>
                </div>
                <p className="text-xs text-muted-foreground">
                  Referral URL’ni hamkor dasturidan oling. Havoladagi barcha parametrlar
                  saqlanadi; komissiya hamkor dasturi shartlariga bog‘liq.
                </p>
                <div className="flex gap-3">
                  <Button type="submit" isLoading={save.isPending}>
                    {id ? 'O‘zgarishlarni saqlash' : 'Hamkor qo‘shish'}
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
              </fieldset>
            </form>
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Hamkorlar ro‘yxati</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {partners.data?.length === 0 && (
              <p className="py-8 text-center text-sm text-muted-foreground">
                Hali hamkor qo‘shilmagan. Birinchi faol hamkor saqlangach, banner bosh
                sahifada paydo bo‘ladi.
              </p>
            )}
            {partners.data?.map((p) => (
              <div
                key={p.id}
                className="flex flex-wrap items-center gap-4 rounded-xl border border-border p-4"
              >
                <Logo url={p.image_url} name={p.name} />
                <div className="min-w-0 flex-1">
                  <a
                    href={p.link_url}
                    target="_blank"
                    rel="sponsored noopener noreferrer"
                    className="break-words font-medium underline decoration-border underline-offset-4"
                  >
                    {p.name} ↗
                  </a>
                  <p className="mt-1 break-words text-sm text-muted-foreground">
                    {p.caption}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    #{p.sort_order} · {p.is_active ? 'Faol' : 'Yashirilgan'}
                    {p.is_affiliate ? ' · Referral' : ''}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setId(p.id)
                      setDraft({ ...p })
                      setNotice('')
                      window.scrollTo({ top: 0, behavior: 'smooth' })
                    }}
                  >
                    Tahrirlash
                  </Button>
                  {deleting === p.id ? (
                    <>
                      <Button
                        variant="secondary"
                        disabled={remove.isPending}
                        onClick={() => remove.mutate(p.id)}
                      >
                        O‘chirishni tasdiqlash
                      </Button>
                      <Button variant="secondary" onClick={() => setDeleting(undefined)}>
                        Bekor qilish
                      </Button>
                    </>
                  ) : (
                    <Button variant="secondary" onClick={() => setDeleting(p.id)}>
                      O‘chirish
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
