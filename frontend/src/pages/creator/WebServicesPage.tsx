import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, FileText, Globe2, ShieldCheck, Sparkles } from 'lucide-react'
import {
  webServicesApi as api,
  type ContractType,
  type CustomerDetails,
  type ProjectBrief,
  type ServiceOrder,
  type ServicePackage,
} from '@/api/webServices'
import { ContractDocument } from '@/components/common/ContractDocument'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { cn } from '@/lib/cn'

const card = 'rounded-xl border border-border bg-surface p-5'

const emptyCustomer: CustomerDetails = {
  full_name: '',
  date_of_birth: '',
  passport_number: '',
  passport_issued_by: '',
  passport_issued_at: '',
  address: '',
  city: '',
  phone: '',
  email: '',
  pinfl: '',
  citizenship_code: '',
  country_code: '',
  tax_id: '',
}
const emptyProject: ProjectBrief = { name: '', description: '', reference_url: '' }

/** Every ISO region the browser can name, for the citizenship pickers. */
function useRegions(locale: string) {
  return useMemo(() => {
    const local = new Intl.DisplayNames([locale], { type: 'region' })
    const english = new Intl.DisplayNames(['en'], { type: 'region' })
    const skip = new Set(['EU', 'EZ', 'UN', 'QO', 'XA', 'XB', 'ZZ'])
    const codes: string[] = []
    for (let a = 65; a <= 90; a++)
      for (let b = 65; b <= 90; b++) {
        const code = String.fromCharCode(a, b)
        if (!skip.has(code) && english.of(code) !== code) codes.push(code)
      }
    return codes
      .map((code) => ({
        code,
        label: local.of(code) ?? code,
        english: english.of(code) ?? code,
      }))
      .sort((x, y) => x.label.localeCompare(y.label, locale))
  }, [locale])
}

/** 1–2 hours, or whole days from 24 hours up. */
function deliveryLabel(
  t: (key: string, options?: Record<string, unknown>) => string,
  pkg: Pick<ServicePackage, 'delivery_hours_min' | 'delivery_hours'>,
) {
  const { delivery_hours_min: low, delivery_hours: high } = pkg
  if (!low && high % 24 === 0) return t('webServices.metric.withinDays', { n: high / 24 })
  if (low) return t('webServices.metric.hoursRange', { min: low, max: high })
  return t('webServices.metric.hours', { n: high })
}

function PackageCard({
  pkg,
  selected,
  onSelect,
}: {
  pkg: ServicePackage
  selected: boolean
  onSelect: () => void
}) {
  const { t } = useTranslation()
  const features = t(`webServices.packages.${pkg.code}.features`, {
    returnObjects: true,
    defaultValue: [],
  }) as string[]
  return (
    <article
      className={cn(
        card,
        'flex flex-col transition-shadow',
        selected && 'border-primary-600 ring-2 ring-primary-600/30',
      )}
    >
      <p className="text-xs font-semibold uppercase tracking-widest text-primary-600">
        {t(`webServices.packages.${pkg.code}.name`)}
      </p>
      <h3 className="mt-1 font-semibold">
        {t(`webServices.packages.${pkg.code}.tagline`)}
      </h3>
      <p className="mt-3 text-3xl font-semibold tracking-tight">
        ${Number(pkg.price_usd).toLocaleString('en-US')}
      </p>
      <p className="mt-3 flex items-center gap-1.5 text-xs font-medium text-primary-600">
        <Sparkles size={14} aria-hidden />
        {t('webServices.aiCard')}
      </p>
      <ul className="mt-4 flex-1 space-y-2 text-sm">
        {features.map((feature) => (
          <li key={feature} className="flex gap-2">
            <Check size={16} className="mt-0.5 shrink-0 text-primary-600" aria-hidden />
            <span>{feature}</span>
          </li>
        ))}
      </ul>
      <dl className="mt-4 grid grid-cols-2 gap-2 border-t border-border pt-4 text-xs text-muted-foreground">
        <div>
          <dt>{t('webServices.metric.delivery')}</dt>
          <dd className="font-medium text-foreground">{deliveryLabel(t, pkg)}</dd>
        </div>
        <div>
          <dt>{t('webServices.metric.revisions')}</dt>
          <dd className="font-medium text-foreground">{pkg.revision_rounds}</dd>
        </div>
        <div>
          <dt>{t('webServices.metric.pages')}</dt>
          <dd className="font-medium text-foreground">
            {pkg.page_limit || t('webServices.metric.bySpec')}
          </dd>
        </div>
        <div>
          <dt>{t('webServices.metric.support')}</dt>
          <dd className="font-medium text-foreground">
            {t('webServices.metric.months', { n: pkg.support_months })}
          </dd>
        </div>
      </dl>
      <Button
        className="mt-4"
        variant={selected ? 'primary' : 'outline'}
        onClick={onSelect}
        aria-pressed={selected}
      >
        {selected ? t('webServices.selected') : t('webServices.choose')}
      </Button>
    </article>
  )
}

function OrderRow({ order }: { order: ServiceOrder }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const refresh = () => client.invalidateQueries({ queryKey: ['web-service-orders'] })
  const pay = useMutation({
    mutationFn: () => api.pay(order.id),
    onSuccess: (next) => {
      void refresh()
      if (next.status === 'pending_payment' && next.checkout_url)
        window.location.assign(next.checkout_url)
    },
  })
  const check = useMutation({
    mutationFn: () => api.confirm(order.id),
    onSuccess: refresh,
  })
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div>
        <p className="font-medium">
          {order.number} · {t(`webServices.packages.${order.package}.name`)} · $
          {order.price_usd}
        </p>
        <p className="text-sm text-muted-foreground">
          {order.project_name} · {t(`webServices.status.${order.status}`, order.status)} ·{' '}
          {new Date(order.created_at).toLocaleDateString()}
        </p>
        {(pay.isError || check.isError) && (
          <p role="alert" className="text-sm text-destructive-600">
            {(pay.error ?? check.error)?.message}
          </p>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        <Link
          to={`/web-services/orders/${order.id}/contract`}
          className="inline-flex h-9 items-center gap-1.5 rounded-md border border-border px-3 text-sm hover:bg-muted"
        >
          <FileText size={15} aria-hidden />
          {t('webServices.contract.open')}
        </Link>
        {order.status === 'pending_payment' && (
          <>
            <Button size="sm" isLoading={pay.isPending} onClick={() => pay.mutate()}>
              {t('webServices.orders.pay')}
            </Button>
            <Button
              size="sm"
              variant="outline"
              isLoading={check.isPending}
              onClick={() => check.mutate()}
            >
              {t('webServices.orders.check')}
            </Button>
          </>
        )}
      </div>
    </li>
  )
}

export function WebServicesPage() {
  const { t, i18n } = useTranslation()
  const [params, setParams] = useSearchParams()
  const client = useQueryClient()
  const catalog = useQuery({ queryKey: ['web-service-catalog'], queryFn: api.catalog })
  const orders = useQuery({ queryKey: ['web-service-orders'], queryFn: api.orders })
  const regions = useRegions(i18n.language)

  const [code, setCode] = useState(params.get('package') ?? '')
  const [kind, setKind] = useState<ContractType>('resident')
  const [customer, setCustomer] = useState(emptyCustomer)
  const [project, setProject] = useState(emptyProject)
  const [accepted, setAccepted] = useState(false)
  const requestKey = useRef<string>(crypto.randomUUID())
  const formRef = useRef<HTMLFormElement>(null)

  const pkg = catalog.data?.packages.find((p) => p.code === code)
  const draft = useMemo(() => {
    if (!pkg) return null
    const english = (c?: string) => regions.find((r) => r.code === c)?.english ?? ''
    const details: CustomerDetails =
      kind === 'resident'
        ? { ...customer, citizenship_code: '', country_code: '', tax_id: '' }
        : {
            ...customer,
            pinfl: '',
            citizenship: english(customer.citizenship_code),
            country: english(customer.country_code),
          }
    return { package: pkg.code, contract_type: kind, customer: details, project }
  }, [pkg, kind, customer, project, regions])

  const preview = useMutation({ mutationFn: api.preview })
  // The draft a preview was made from; editing the form afterwards makes it stale.
  const [reviewedFor, setReviewedFor] = useState('')
  const stale = !!preview.data && reviewedFor !== JSON.stringify(draft)

  const place = useMutation({
    mutationFn: () =>
      api.place({
        ...draft!,
        request_key: requestKey.current,
        quoted_total: pkg!.price_usd,
        preview_checksum: preview.data!.checksum,
        accept_terms: accepted,
      }),
    onSuccess: (order) => {
      requestKey.current = crypto.randomUUID()
      if (order.checkout_url) window.location.assign(order.checkout_url)
    },
    // The contract is saved before Payoneer is called, so a payment-page
    // failure still leaves an unpaid order the customer can retry from the list.
    onSettled: () => client.invalidateQueries({ queryKey: ['web-service-orders'] }),
  })

  // Back from Payoneer: only the server's check against Payoneer counts.
  const returned = params.get('order')
  const outcome = params.get('payment')
  const confirm = useMutation({
    mutationFn: api.confirm,
    onSuccess: () => client.invalidateQueries({ queryKey: ['web-service-orders'] }),
  })
  const confirmed = useRef(false)
  useEffect(() => {
    if (returned && outcome === 'return' && !confirmed.current) {
      confirmed.current = true
      confirm.mutate(returned)
    }
  }, [returned, outcome, confirm])

  const setField = (name: keyof CustomerDetails) => (e: { target: { value: string } }) =>
    setCustomer((c) => ({ ...c, [name]: e.target.value }))

  const choose = (next: string) => {
    setCode(next)
    setParams((p) => {
      p.set('package', next)
      return p
    })
    requestAnimationFrame(() => formRef.current?.scrollIntoView({ behavior: 'smooth' }))
  }

  const regionOptions = [
    { value: '', label: '—' },
    ...regions.map((r) => ({ value: r.code, label: r.label })),
  ]
  const salesReady = catalog.data?.sales_ready ?? false

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <header>
        <div className="mb-2 flex items-center gap-3">
          <Globe2 className="text-primary-600" />
          <h1 className="text-2xl font-semibold">{t('webServices.title')}</h1>
        </div>
        <p className="mb-2 inline-flex items-center gap-1.5 rounded-full bg-primary-600/10 px-3 py-1 text-xs font-semibold text-primary-600">
          <Sparkles size={14} aria-hidden />
          {t('webServices.slogan')}
        </p>
        <p className="max-w-3xl text-muted-foreground">{t('webServices.subtitle')}</p>
      </header>

      {returned && outcome && (
        <p role="status" className={cn(card, 'text-sm')}>
          {outcome === 'canceled'
            ? t('webServices.payment.canceled')
            : confirm.isPending
              ? t('webServices.payment.returned')
              : confirm.data?.status === 'paid'
                ? t('webServices.payment.confirmed')
                : confirm.isError
                  ? confirm.error.message
                  : t('webServices.payment.pending')}
        </p>
      )}

      {catalog.isError && <p role="alert">{t('webServices.catalogFailed')}</p>}
      {catalog.data && !salesReady && (
        <p className={cn(card, 'text-sm text-muted-foreground')}>
          {t('webServices.salesClosed')}
        </p>
      )}

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {catalog.data?.packages.map((p) => (
          <PackageCard
            key={p.id}
            pkg={p}
            selected={p.code === code}
            onSelect={() => choose(p.code)}
          />
        ))}
      </section>

      {pkg && (
        <form
          ref={formRef}
          className="space-y-6"
          onSubmit={(e) => {
            e.preventDefault()
            setReviewedFor(JSON.stringify(draft))
            setAccepted(false)
            preview.mutate(draft!)
          }}
        >
          <section className={card}>
            <h2 className="text-lg font-semibold">{t('webServices.form.type')}</h2>
            <div role="radiogroup" className="mt-3 grid gap-3 sm:grid-cols-2">
              {(['resident', 'non_resident'] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={kind === value}
                  onClick={() => setKind(value)}
                  className={cn(
                    'rounded-lg border p-4 text-left transition-colors',
                    kind === value
                      ? 'border-primary-600 bg-primary-600/5'
                      : 'border-border hover:bg-muted',
                  )}
                >
                  <span className="font-medium">{t(`webServices.form.${value}`)}</span>
                  <span className="mt-1 block text-sm text-muted-foreground">
                    {t(`webServices.form.${value}Hint`)}
                  </span>
                </button>
              ))}
            </div>
          </section>

          <section className={card}>
            <h2 className="mb-4 text-lg font-semibold">
              {t('webServices.form.personal')}
            </h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <Input
                label={t('webServices.form.fullName')}
                required
                minLength={5}
                maxLength={160}
                autoComplete="name"
                value={customer.full_name}
                onChange={setField('full_name')}
              />
              <Input
                label={t('webServices.form.dateOfBirth')}
                type="date"
                required
                value={customer.date_of_birth}
                onChange={setField('date_of_birth')}
              />
              {kind === 'non_resident' && (
                <>
                  <Select
                    label={t('webServices.form.citizenship')}
                    required
                    options={regionOptions.filter((o) => o.value !== 'UZ')}
                    value={customer.citizenship_code}
                    onChange={setField('citizenship_code')}
                  />
                  <Select
                    label={t('webServices.form.country')}
                    required
                    options={regionOptions}
                    value={customer.country_code}
                    onChange={setField('country_code')}
                  />
                </>
              )}
              <Input
                label={t('webServices.form.passportNumber')}
                hint={t('webServices.form.passportHint')}
                required
                pattern="[A-Z0-9]{5,20}"
                value={customer.passport_number}
                onChange={(e) =>
                  setCustomer((c) => ({
                    ...c,
                    passport_number: e.target.value.toUpperCase().replace(/\s/g, ''),
                  }))
                }
              />
              <Input
                label={t('webServices.form.passportIssuedBy')}
                required
                value={customer.passport_issued_by}
                onChange={setField('passport_issued_by')}
              />
              <Input
                label={t('webServices.form.passportIssuedAt')}
                type="date"
                required
                value={customer.passport_issued_at}
                onChange={setField('passport_issued_at')}
              />
              {kind === 'resident' ? (
                <Input
                  label={t('webServices.form.pinfl')}
                  required
                  inputMode="numeric"
                  pattern="[0-9]{14}"
                  maxLength={14}
                  value={customer.pinfl}
                  onChange={setField('pinfl')}
                />
              ) : (
                <Input
                  label={t('webServices.form.taxId')}
                  maxLength={40}
                  value={customer.tax_id}
                  onChange={setField('tax_id')}
                />
              )}
              <Input
                label={t('webServices.form.address')}
                required
                minLength={5}
                autoComplete="street-address"
                value={customer.address}
                onChange={setField('address')}
              />
              <Input
                label={t('webServices.form.city')}
                required
                autoComplete="address-level2"
                value={customer.city}
                onChange={setField('city')}
              />
              <Input
                label={t('webServices.form.phone')}
                hint={t('webServices.form.phoneHint')}
                type="tel"
                required
                pattern="\+[1-9][0-9 ()\-]{6,20}"
                autoComplete="tel"
                value={customer.phone}
                onChange={setField('phone')}
              />
              <Input
                label={t('webServices.form.email')}
                type="email"
                required
                autoComplete="email"
                value={customer.email}
                onChange={setField('email')}
              />
            </div>
          </section>

          <section className={card}>
            <h2 className="mb-4 text-lg font-semibold">
              {t('webServices.form.project')}
            </h2>
            <div className="grid gap-4">
              <Input
                label={t('webServices.form.projectName')}
                required
                minLength={3}
                maxLength={160}
                value={project.name}
                onChange={(e) => setProject((p) => ({ ...p, name: e.target.value }))}
              />
              <label className="flex flex-col gap-1.5 text-sm font-medium">
                <span>
                  {t('webServices.form.projectDescription')}
                  <span className="text-destructive-600" aria-hidden>
                    {' '}
                    *
                  </span>
                </span>
                <textarea
                  required
                  minLength={20}
                  maxLength={4000}
                  rows={5}
                  value={project.description}
                  onChange={(e) =>
                    setProject((p) => ({ ...p, description: e.target.value }))
                  }
                  className="rounded-md border border-border bg-surface p-3 font-normal focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
                <span className="text-xs font-normal text-muted-foreground">
                  {t('webServices.form.projectDescriptionHint')}
                </span>
              </label>
              <Input
                label={t('webServices.form.referenceUrl')}
                type="url"
                placeholder="https://"
                value={project.reference_url}
                onChange={(e) =>
                  setProject((p) => ({ ...p, reference_url: e.target.value }))
                }
              />
            </div>
          </section>

          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" isLoading={preview.isPending}>
              <FileText size={16} aria-hidden />
              {t('webServices.form.review')}
            </Button>
            {preview.isError && (
              <p role="alert" className="text-sm text-destructive-600">
                {preview.error.message}
              </p>
            )}
          </div>
        </form>
      )}

      {pkg && preview.data && (
        <section className="space-y-4">
          <h2 className="text-lg font-semibold">{t('webServices.contract.title')}</h2>
          <p className="text-sm text-muted-foreground">
            {t('webServices.contract.reviewHint')}
          </p>
          <div className="max-h-[75vh] overflow-y-auto rounded-xl border border-border bg-neutral-200 p-3 sm:p-6 dark:bg-neutral-800">
            <ContractDocument doc={preview.data.document} />
          </div>
          {stale ? (
            <p role="alert" className="text-sm font-medium text-amber-700">
              {t('webServices.contract.stale')}
            </p>
          ) : (
            <div className={cn(card, 'space-y-4')}>
              <label className="flex items-start gap-3 text-sm">
                <input
                  type="checkbox"
                  className="mt-1 size-4"
                  checked={accepted}
                  onChange={(e) => setAccepted(e.target.checked)}
                />
                <span>{t('webServices.contract.accept')}</span>
              </label>
              <Button
                disabled={!accepted || !salesReady}
                isLoading={place.isPending}
                onClick={() => place.mutate()}
              >
                <ShieldCheck size={16} aria-hidden />
                {t('webServices.contract.pay', {
                  price: `$${Number(pkg.price_usd).toLocaleString('en-US')}`,
                })}
              </Button>
              <p className="text-xs text-muted-foreground">{t('webServices.secure')}</p>
              {place.isError && (
                <p role="alert" className="text-sm text-destructive-600">
                  {place.error.message}
                </p>
              )}
            </div>
          )}
        </section>
      )}

      <section className={card}>
        <h2 className="text-lg font-semibold">{t('webServices.orders.title')}</h2>
        {orders.data?.length === 0 && (
          <p className="mt-2 text-sm text-muted-foreground">
            {t('webServices.orders.empty')}
          </p>
        )}
        <ul className="divide-y divide-border">
          {orders.data?.map((order) => (
            <OrderRow key={order.id} order={order} />
          ))}
        </ul>
      </section>
    </div>
  )
}
