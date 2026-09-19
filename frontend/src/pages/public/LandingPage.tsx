import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { LanguageSwitcher } from '@/components/layout/LanguageSwitcher'
import './landing.css'
import { MyWebParticleBackground } from '@/components/ui/myweb-particle-background'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { useUiStore } from '@/stores/uiStore'

/* Visual language ported 1:1 from the myweb.uz bundle in this repo: Sentient
   display type over Geist Mono labels, a neutral black/white ramp, #ffc700 as
   the single accent, oversized radii and barely-there glass surfaces. Only the
   copy is ours — every string still comes from the existing i18n keys so all 30
   locales keep working. */

const ACCENT = '#ffc700'

/** Gold capsule with a pinging dot — myweb's section eyebrow. */
function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <span
      className="mb-6 inline-flex items-center gap-2.5 rounded-full border px-4 py-1.5 font-geist text-[10px] uppercase tracking-[0.32em] text-neutral-700 sm:text-xs dark:text-[#ffd762]"
      style={{ borderColor: `${ACCENT}59`, backgroundColor: `${ACCENT}1a` }}
    >
      <span className="relative flex size-2 items-center justify-center">
        <span
          className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-75"
          style={{ backgroundColor: `${ACCENT}66` }}
        />
        <span
          className="relative inline-flex size-1.5 rounded-full"
          style={{ backgroundColor: ACCENT, boxShadow: `0 0 8px ${ACCENT}cc` }}
        />
      </span>
      {children}
    </span>
  )
}

/** Display heading: gradient that fades toward the foot of the letterforms. */
function Heading({ children, id }: { children: React.ReactNode; id?: string }) {
  return (
    <h2
      id={id}
      className="bg-gradient-to-b from-neutral-950 via-neutral-950 to-neutral-950/35 bg-clip-text font-sentient text-4xl font-black tracking-tight text-transparent text-balance sm:text-5xl lg:text-[3.5rem] dark:from-neutral-50 dark:via-neutral-50 dark:to-neutral-50/30"
    >
      {children}
    </h2>
  )
}

/** Pill CTA: inverts with the theme, exactly like myweb's primary action. */
function PrimaryAction({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <Link
      to={to}
      className="group relative inline-flex items-center gap-4 overflow-hidden rounded-full bg-neutral-900 px-8 py-4 font-geist text-[11px] font-bold uppercase tracking-[0.3em] text-white shadow-xl transition-all duration-500 will-change-transform hover:scale-105 active:scale-95 sm:px-10 sm:py-5 sm:text-sm sm:tracking-[0.4em] dark:bg-neutral-50 dark:text-neutral-950"
    >
      <span
        className="absolute inset-0 -translate-x-full transition-transform duration-700 group-hover:translate-x-0"
        style={{ background: `linear-gradient(90deg, transparent, ${ACCENT}40, transparent)` }}
        aria-hidden="true"
      />
      <span className="relative">{children}</span>
      <span className="relative transition-transform duration-500 group-hover:translate-x-1" aria-hidden="true">
        ↗
      </span>
    </Link>
  )
}

export function LandingPage() {
  const { t } = useTranslation()
  const theme = useUiStore((state) => state.theme)
  const services = t('landing.services', { returnObjects: true }) as {
    title: string
    text: string
  }[]
  const steps = t('landing.steps', { returnObjects: true }) as string[]
  const faqs = t('landing.faqs', { returnObjects: true }) as { q: string; a: string }[]

  const marquee = ['YouTube', 'AI Video', 'Shorts', 'Analytics', 'Creator Studio']
  const navLinks = [
    { href: '#services', label: t('landing.navServices') },
    { href: '#process', label: t('landing.navProcess') },
    { href: '#share', label: t('landing.navShare') },
    { href: '#faq', label: 'FAQ' },
  ]

  return (
    <div className="landing-root min-h-screen bg-white font-sans text-neutral-950 antialiased transition-colors duration-500 dark:bg-neutral-950 dark:text-neutral-50">
      {/* ---------------------------------------------------------------- nav */}
      <header className="sticky top-0 z-50 border-b border-black/5 bg-white/70 backdrop-blur-xl dark:border-white/[0.08] dark:bg-neutral-950/70">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-4 sm:px-6">
          <Link
            to="/"
            className="font-sentient text-xl font-black tracking-tighter transition-colors duration-300 sm:text-2xl"
          >
            Creator<span style={{ color: ACCENT }}>AI.</span>
          </Link>

          <nav aria-label={t('landing.navigation')} className="hidden items-center gap-8 md:flex">
            {navLinks.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="group relative font-geist text-[11px] uppercase tracking-[0.22em] text-neutral-500 transition-colors duration-300 hover:text-neutral-950 dark:text-neutral-400 dark:hover:text-neutral-50"
              >
                {link.label}
                <span
                  className="absolute -bottom-1.5 left-0 h-px w-0 transition-all duration-500 group-hover:w-full"
                  style={{ backgroundColor: ACCENT }}
                  aria-hidden="true"
                />
              </a>
            ))}
          </nav>

          <div className="flex items-center gap-2 sm:gap-3">
            <LanguageSwitcher />
            <ThemeToggle />
            <Link
              to="/login"
              className="rounded-full border border-black/10 px-4 py-2 font-geist text-[10px] font-bold uppercase tracking-[0.2em] transition-all duration-300 hover:border-black/30 sm:px-5 dark:border-white/15 dark:hover:border-white/40"
            >
              {t('auth.login.submit')} ↗
            </Link>
          </div>
        </div>
      </header>

      <main>
        {/* ------------------------------------------------------------- hero */}
        <section className="relative flex min-h-[88vh] items-center justify-center overflow-hidden bg-white px-4 py-24 transition-colors duration-500 dark:bg-neutral-950">
          <MyWebParticleBackground tone={theme} />
          {/* Accent bloom behind the headline. */}
          <div
            className="pointer-events-none absolute left-1/2 top-1/3 -z-0 h-[36rem] w-[36rem] -translate-x-1/2 -translate-y-1/2 rounded-full opacity-[0.07] blur-[120px]"
            style={{ backgroundColor: ACCENT }}
            aria-hidden="true"
          />

          <div className="relative z-10 mx-auto flex max-w-5xl flex-col items-center text-center">
            <Eyebrow>{t('landing.badge')}</Eyebrow>

            <h1 className="relative z-20 max-w-full bg-gradient-to-b from-neutral-950 via-neutral-950 to-neutral-950/25 bg-clip-text font-sentient text-[clamp(2.5rem,10vw,6rem)] leading-[0.95] tracking-tighter text-transparent sm:text-[clamp(3.5rem,11vw,7rem)] sm:leading-[1.02] dark:from-neutral-50 dark:via-neutral-50 dark:to-neutral-50/20">
              Creator AI
              <br />
              <em className="font-light italic" style={{ color: ACCENT }}>
                {t('landing.heroAccent')}
              </em>
              <br />
              {t('landing.heroEnd')}
            </h1>

            <p className="mt-8 max-w-2xl text-base leading-relaxed text-neutral-600 text-pretty sm:text-lg dark:text-neutral-400">
              {t('landing.description')}
            </p>

            <div className="mt-10">
              <PrimaryAction to="/signup">{t('landing.start')}</PrimaryAction>
            </div>
          </div>

          <a
            href="#services"
            className="absolute bottom-8 left-1/2 flex -translate-x-1/2 flex-col items-center gap-2 font-geist text-[10px] uppercase tracking-[0.28em] text-neutral-400 transition-colors duration-300 hover:text-neutral-950 dark:text-neutral-500 dark:hover:text-neutral-50"
          >
            <span className="animate-bounce" aria-hidden="true">
              ↓
            </span>
            {t('landing.discover')}
          </a>
        </section>

        {/* ----------------------------------------------------------- strip */}
        <div className="overflow-hidden border-y border-black/5 bg-[#fafafa] py-5 transition-colors duration-500 dark:border-white/[0.08] dark:bg-[#070707]">
          <div className="landing-marquee flex w-max items-center gap-12 sm:gap-20">
            {[...marquee, ...marquee, ...marquee, ...marquee].map((word, i) => (
              <span
                key={`${word}-${i}`}
                className="flex shrink-0 items-center gap-12 font-geist text-xs uppercase tracking-[0.3em] text-neutral-400 sm:gap-20 sm:text-sm dark:text-neutral-600"
              >
                {word}
                <span style={{ color: ACCENT }} aria-hidden="true">
                  ✦
                </span>
              </span>
            ))}
          </div>
        </div>

        {/* -------------------------------------------------------- services */}
        <section
          id="services"
          aria-labelledby="services-title"
          className="relative overflow-hidden bg-white px-4 py-24 transition-colors duration-500 sm:py-32 dark:bg-neutral-950"
        >
          <div className="mx-auto max-w-7xl">
            <div className="max-w-3xl">
              <Eyebrow>01 / {t('landing.navServices')}</Eyebrow>
              <Heading id="services-title">{t('landing.servicesTitle')}</Heading>
              <p className="mt-6 max-w-2xl text-base leading-relaxed text-neutral-600 text-pretty sm:text-lg dark:text-neutral-400">
                {t('landing.servicesLead')}
              </p>
            </div>

            <div className="mt-16 grid grid-cols-1 gap-5 sm:grid-cols-2 sm:gap-6 lg:gap-8">
              {services.map((service, i) => (
                <article
                  key={service.title}
                  className="group relative overflow-hidden rounded-[2rem] border border-black/5 bg-white/60 p-8 ring-1 ring-black/[0.04] backdrop-blur-xl transition-all duration-500 hover:-translate-y-1 hover:border-black/10 sm:rounded-[2.5rem] sm:p-10 dark:border-white/[0.08] dark:bg-white/[0.015] dark:ring-0 dark:hover:border-white/20"
                >
                  <span
                    className="pointer-events-none absolute right-6 top-2 select-none font-sentient text-8xl font-black text-black/[0.03] transition-colors duration-500 dark:text-white/[0.02]"
                    aria-hidden="true"
                  >
                    0{i + 1}
                  </span>

                  <p className="relative font-geist text-[10px] uppercase tracking-[0.28em] text-neutral-400 dark:text-neutral-500">
                    0{i + 1} / Creator AI
                  </p>
                  <h3 className="relative mt-5 font-sentient text-2xl font-extrabold tracking-tight text-pretty sm:text-[1.85rem]">
                    {service.title}
                  </h3>
                  <p className="relative mt-4 leading-relaxed text-neutral-600 text-pretty dark:text-neutral-400">
                    {service.text}
                  </p>

                  <span
                    className="absolute inset-x-8 bottom-0 h-px opacity-0 transition-opacity duration-500 group-hover:opacity-100"
                    style={{ background: `linear-gradient(90deg, transparent, ${ACCENT}66, transparent)` }}
                    aria-hidden="true"
                  />
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* --------------------------------------------------------- process */}
        <section
          id="process"
          aria-labelledby="process-title"
          className="relative overflow-hidden bg-[#fafafa] px-4 py-24 transition-colors duration-500 sm:py-32 dark:bg-[#070707]"
        >
          <div className="mx-auto max-w-5xl">
            <Eyebrow>02 / {t('landing.navProcess')}</Eyebrow>
            <Heading id="process-title">{t('landing.processTitle')}</Heading>

            <ol className="mt-16 divide-y divide-black/5 border-y border-black/5 dark:divide-white/[0.08] dark:border-white/[0.08]">
              {steps.map((step, i) => (
                <li
                  key={step}
                  className="group flex items-center gap-6 py-7 transition-colors duration-500 hover:bg-black/[0.02] sm:gap-10 dark:hover:bg-white/[0.02]"
                >
                  <span
                    className="font-sentient text-3xl font-black tabular-nums text-neutral-300 transition-colors duration-500 sm:text-5xl dark:text-neutral-700"
                    style={{ minWidth: '3rem' }}
                  >
                    0{i + 1}
                  </span>
                  <h3 className="flex-1 font-sentient text-lg font-bold tracking-tight text-pretty sm:text-2xl">
                    {step}
                  </h3>
                  <span
                    className="text-lg opacity-0 transition-all duration-500 group-hover:translate-x-1 group-hover:opacity-100"
                    style={{ color: ACCENT }}
                    aria-hidden="true"
                  >
                    ↗
                  </span>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* ----------------------------------------------------------- share */}
        <section
          id="share"
          aria-labelledby="share-title"
          className="relative overflow-hidden bg-white px-4 py-24 transition-colors duration-500 sm:py-32 dark:bg-neutral-950"
        >
          <div className="mx-auto max-w-5xl">
            <Eyebrow>03 / {t('landing.navShare')}</Eyebrow>
            <Heading id="share-title">{t('landing.shareTitle')}</Heading>

            <div className="mt-16 grid grid-cols-1 gap-6 sm:grid-cols-2 sm:gap-8">
              {[
                { value: 70, label: t('landing.creatorShare'), accent: true },
                { value: 30, label: t('landing.platformShare'), accent: false },
              ].map((split) => (
                <div
                  key={split.label}
                  className="relative overflow-hidden rounded-[2rem] border border-black/5 bg-white/60 p-8 ring-1 ring-black/[0.04] backdrop-blur-xl sm:rounded-[2.5rem] sm:p-10 dark:border-white/[0.08] dark:bg-white/[0.015] dark:ring-0"
                >
                  <strong
                    className="block font-sentient text-6xl font-black tracking-tighter tabular-nums sm:text-8xl"
                    style={split.accent ? { color: ACCENT } : undefined}
                  >
                    {split.value}
                    <span className="text-3xl sm:text-5xl">%</span>
                  </strong>
                  <p className="mt-4 font-geist text-[11px] uppercase tracking-[0.28em] text-neutral-500 dark:text-neutral-400">
                    {split.label}
                  </p>
                </div>
              ))}
            </div>

            <p
              className="mt-8 rounded-[1.5rem] border px-6 py-5 text-sm leading-relaxed text-neutral-700 text-pretty dark:text-neutral-300"
              style={{ borderColor: `${ACCENT}40`, backgroundColor: `${ACCENT}0f` }}
            >
              {t('landing.shareScope')}
            </p>
            <p className="mt-6 text-sm leading-relaxed text-neutral-500 text-pretty dark:text-neutral-500">
              {t('landing.shareDetails')}
            </p>
          </div>
        </section>

        {/* ------------------------------------------------------------- faq */}
        <section
          id="faq"
          aria-labelledby="faq-title"
          className="relative overflow-hidden bg-[#fafafa] px-4 py-24 transition-colors duration-500 sm:py-32 dark:bg-[#070707]"
        >
          <div className="landing-faq mx-auto max-w-4xl">
            <Eyebrow>04 / FAQ</Eyebrow>
            <Heading id="faq-title">{t('landing.faqTitle')}</Heading>

            <div className="mt-16 space-y-4">
              {faqs.map((faq) => (
                <details
                  key={faq.q}
                  className="group overflow-hidden rounded-[1.5rem] border border-black/5 bg-white/60 ring-1 ring-black/[0.04] backdrop-blur-xl transition-colors duration-500 open:border-black/10 sm:rounded-[2rem] dark:border-white/[0.08] dark:bg-white/[0.015] dark:ring-0 dark:open:border-white/20"
                >
                  <summary className="flex cursor-pointer items-center justify-between gap-6 px-6 py-6 font-sentient text-base font-bold tracking-tight text-pretty transition-colors duration-300 sm:px-8 sm:text-lg">
                    {faq.q}
                    <span
                      className="shrink-0 text-xl transition-transform duration-500 group-open:rotate-45"
                      style={{ color: ACCENT }}
                      aria-hidden="true"
                    >
                      +
                    </span>
                  </summary>
                  <p className="px-6 pb-6 leading-relaxed text-neutral-600 text-pretty sm:px-8 dark:text-neutral-400">
                    {faq.a}
                  </p>
                </details>
              ))}
            </div>
          </div>
        </section>

        {/* ------------------------------------------------------------- cta */}
        <section className="relative overflow-hidden bg-white px-4 py-24 transition-colors duration-500 sm:py-32 dark:bg-neutral-950">
          <div className="relative mx-auto max-w-4xl overflow-hidden rounded-[2rem] border border-black/5 bg-white/60 p-10 text-center ring-1 ring-black/[0.04] backdrop-blur-3xl sm:rounded-[2.5rem] sm:p-16 dark:border-white/[0.08] dark:bg-white/[0.015] dark:ring-0">
            <div
              className="pointer-events-none absolute left-1/2 top-0 h-64 w-64 -translate-x-1/2 -translate-y-1/2 rounded-full opacity-[0.12] blur-[90px]"
              style={{ backgroundColor: ACCENT }}
              aria-hidden="true"
            />
            <div className="relative flex flex-col items-center">
              <Eyebrow>Creator AI Ecosystem</Eyebrow>
              <Heading>{t('landing.ctaTitle')}</Heading>
              <p className="mt-6 max-w-xl text-base leading-relaxed text-neutral-600 text-pretty sm:text-lg dark:text-neutral-400">
                {t('landing.ctaText')}
              </p>
              <div className="mt-10">
                <PrimaryAction to="/signup">{t('landing.start')}</PrimaryAction>
              </div>
            </div>
          </div>
        </section>
      </main>

      {/* ------------------------------------------------------------ footer */}
      <footer className="border-t border-black/5 bg-[#fafafa] px-4 py-14 transition-colors duration-500 dark:border-white/[0.08] dark:bg-[#070707]">
        <div className="mx-auto flex max-w-7xl flex-col gap-8 sm:flex-row sm:items-start sm:justify-between">
          <div className="max-w-sm">
            <Link to="/" className="font-sentient text-xl font-black tracking-tighter">
              Creator<span style={{ color: ACCENT }}>AI.</span>
            </Link>
            <p className="mt-4 text-sm leading-relaxed text-neutral-500 text-pretty dark:text-neutral-400">
              {t('landing.footer')}
            </p>
          </div>

          <div className="flex flex-col gap-3 font-geist text-[11px] uppercase tracking-[0.22em]">
            <a
              href="#share"
              className="text-neutral-500 transition-colors duration-300 hover:text-neutral-950 dark:text-neutral-400 dark:hover:text-neutral-50"
            >
              {t('landing.navShare')}
            </a>
            <Link
              to="/login"
              className="text-neutral-500 transition-colors duration-300 hover:text-neutral-950 dark:text-neutral-400 dark:hover:text-neutral-50"
            >
              {t('auth.login.submit')}
            </Link>
          </div>
        </div>

        <small className="mx-auto mt-12 block max-w-7xl font-geist text-[10px] uppercase tracking-[0.28em] text-neutral-400 dark:text-neutral-600">
          © {new Date().getFullYear()} Creator AI
        </small>
      </footer>
    </div>
  )
}
