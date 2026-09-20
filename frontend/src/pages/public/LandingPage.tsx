import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { motion, useInView, useReducedMotion } from 'framer-motion'
import { LanguageSwitcher } from '@/components/layout/LanguageSwitcher'
import './landing.css'
import { MyWebParticleBackground } from '@/components/ui/myweb-particle-background'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { useUiStore } from '@/stores/uiStore'

/* Visual language and motion ported 1:1 from the myweb.uz bundle in this repo:
   Sentient display type over Geist Mono labels, a neutral black/white ramp,
   #ffc700 as the single accent, oversized radii, barely-there glass surfaces,
   and its animation vocabulary — expo-out reveals on scroll, manual stagger,
   soft springs on hover and snappy ones on tap.

   Only the copy is ours: every string still comes from the existing i18n keys
   so all 30 locales keep working. */

const ACCENT = '#ffc700'

/** myweb's signature expo-out curve — fast out of the gate, long settle. */
const EXPO_OUT = [0.16, 1, 0.3, 1] as const
/** Entrance spring: soft, no perceptible overshoot. */
const SOFT_SPRING = { type: 'spring', stiffness: 150, damping: 22 } as const
/** Press spring: snappy enough to feel mechanical. */
const TAP_SPRING = { type: 'spring', stiffness: 500, damping: 10 } as const

/**
 * Scroll-triggered reveal. Fires once, a little before the element reaches the
 * viewport edge, and collapses to a plain wrapper under reduced motion.
 */
function Reveal({
  children,
  delay = 0,
  y = 24,
  className,
}: {
  children: ReactNode
  delay?: number
  y?: number
  className?: string
}) {
  const reduceMotion = useReducedMotion()
  if (reduceMotion) return <div className={className}>{children}</div>
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-100px' }}
      transition={{ duration: 0.6, ease: EXPO_OUT, delay }}
    >
      {children}
    </motion.div>
  )
}

/** Gold capsule with a pinging dot — myweb's section eyebrow. */
function Eyebrow({ children }: { children: ReactNode }) {
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
function Heading({ children, id }: { children: ReactNode; id?: string }) {
  return (
    <h2
      id={id}
      className="bg-gradient-to-b from-neutral-950 via-neutral-950 to-neutral-950/35 bg-clip-text font-sentient text-4xl font-black tracking-tight text-transparent text-balance sm:text-5xl lg:text-[3.5rem] dark:from-neutral-50 dark:via-neutral-50 dark:to-neutral-50/30"
    >
      {children}
    </h2>
  )
}

/** Pill CTA: inverts with the theme, lifts on hover, compresses on press. */
function PrimaryAction({ to, children }: { to: string; children: ReactNode }) {
  const reduceMotion = useReducedMotion()
  return (
    <motion.div
      className="inline-block"
      whileHover={reduceMotion ? undefined : { scale: 1.05 }}
      whileTap={reduceMotion ? undefined : { scale: 0.95 }}
      transition={TAP_SPRING}
    >
      <Link
        to={to}
        className="group relative inline-flex items-center gap-4 overflow-hidden rounded-full bg-neutral-900 px-8 py-4 font-geist text-[11px] font-bold uppercase tracking-[0.3em] text-white shadow-xl sm:px-10 sm:py-5 sm:text-sm sm:tracking-[0.4em] dark:bg-neutral-50 dark:text-neutral-950"
      >
        {/* Light sweeps across the pill on hover. */}
        <span
          className="absolute inset-0 -translate-x-full transition-transform duration-700 group-hover:translate-x-0"
          style={{ background: `linear-gradient(90deg, transparent, ${ACCENT}40, transparent)` }}
          aria-hidden="true"
        />
        <span className="relative">{children}</span>
        <span
          className="relative transition-transform duration-500 group-hover:translate-x-1"
          aria-hidden="true"
        >
          ↗
        </span>
      </Link>
    </motion.div>
  )
}

/**
 * Revenue-split figure. Counts up once it scrolls into view and runs a glare
 * across itself, the way myweb animates its stat tiles.
 */
function SplitFigure({ value, label, accent }: { value: number; label: string; accent: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '-100px' })
  const reduceMotion = useReducedMotion()
  const [counted, setCounted] = useState(0)
  // Reduced motion skips the count entirely and renders the final figure.
  const shown = reduceMotion ? value : counted

  useEffect(() => {
    if (!inView || reduceMotion) return
    const duration = 1200
    const start = performance.now()
    let raf = 0
    const tick = (now: number) => {
      const p = Math.min((now - start) / duration, 1)
      // Expo-out, matching the reveal curve the figure arrives on.
      setCounted(Math.round(value * (1 - Math.pow(1 - p, 4))))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [inView, reduceMotion, value])

  return (
    <div
      ref={ref}
      className="relative overflow-hidden rounded-[2rem] border border-black/5 bg-white/60 p-8 ring-1 ring-black/[0.04] backdrop-blur-xl sm:rounded-[2.5rem] sm:p-10 dark:border-white/[0.08] dark:bg-white/[0.015] dark:ring-0"
    >
      {inView && !reduceMotion && (
        <span
          className="landing-shimmer pointer-events-none absolute inset-y-0 -left-full w-1/2"
          style={{ background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.35), transparent)' }}
          aria-hidden="true"
        />
      )}
      <strong
        className="relative block font-sentient text-6xl font-black tracking-tighter tabular-nums sm:text-8xl"
        style={accent ? { color: ACCENT } : undefined}
      >
        {shown}
        <span className="text-3xl sm:text-5xl">%</span>
      </strong>
      <p className="relative mt-4 font-geist text-[11px] uppercase tracking-[0.28em] text-neutral-500 dark:text-neutral-400">
        {label}
      </p>
    </div>
  )
}

export function LandingPage() {
  const { t } = useTranslation()
  const theme = useUiStore((state) => state.theme)
  const reduceMotion = useReducedMotion()
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

  /** Hero pieces arrive on mount, staggered by hand the way myweb does it. */
  const heroStep = (i: number) =>
    reduceMotion
      ? {}
      : {
          initial: { opacity: 0, y: 20 },
          animate: { opacity: 1, y: 0 },
          transition: { duration: 0.7, ease: EXPO_OUT, delay: 0.1 + i * 0.1 },
        }

  return (
    <div className="landing-root min-h-screen bg-white font-sans text-neutral-950 antialiased transition-colors duration-500 dark:bg-neutral-950 dark:text-neutral-50">
      {/* ---------------------------------------------------------------- nav */}
      <motion.header
        className="sticky top-0 z-50 border-b border-black/5 bg-white/70 backdrop-blur-xl dark:border-white/[0.08] dark:bg-neutral-950/70"
        initial={reduceMotion ? false : { y: -80 }}
        animate={{ y: 0 }}
        transition={SOFT_SPRING}
      >
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
      </motion.header>

      <main>
        {/* ------------------------------------------------------------- hero */}
        <section className="relative flex min-h-[88vh] items-center justify-center overflow-hidden bg-white px-4 py-24 transition-colors duration-500 dark:bg-neutral-950">
          <MyWebParticleBackground tone={theme} />
          {/* Accent bloom behind the headline, breathing slowly. */}
          <motion.div
            className="pointer-events-none absolute left-1/2 top-1/3 -z-0 h-[36rem] w-[36rem] -translate-x-1/2 -translate-y-1/2 rounded-full blur-[120px]"
            style={{ backgroundColor: ACCENT }}
            initial={{ opacity: 0.07 }}
            animate={reduceMotion ? { opacity: 0.07 } : { opacity: [0.05, 0.1, 0.05] }}
            transition={{ duration: 8, repeat: Infinity, ease: 'easeInOut' }}
            aria-hidden="true"
          />

          <div className="relative z-10 mx-auto flex max-w-5xl flex-col items-center text-center">
            <motion.div {...heroStep(0)}>
              <Eyebrow>{t('landing.badge')}</Eyebrow>
            </motion.div>

            <motion.h1
              className="relative z-20 max-w-full bg-gradient-to-b from-neutral-950 via-neutral-950 to-neutral-950/25 bg-clip-text font-sentient text-[clamp(2.5rem,10vw,6rem)] leading-[0.95] tracking-tighter text-transparent sm:text-[clamp(3.5rem,11vw,7rem)] sm:leading-[1.02] dark:from-neutral-50 dark:via-neutral-50 dark:to-neutral-50/20"
              {...heroStep(1)}
            >
              Creator AI
              <br />
              <em
                className="landing-gradient-x bg-clip-text font-light italic text-transparent"
                style={{
                  backgroundImage: `linear-gradient(90deg, ${ACCENT}, #ffe9a3, ${ACCENT})`,
                }}
              >
                {t('landing.heroAccent')}
              </em>
              <br />
              {t('landing.heroEnd')}
            </motion.h1>

            <motion.p
              className="mt-8 max-w-2xl text-base leading-relaxed text-neutral-600 text-pretty sm:text-lg dark:text-neutral-400"
              {...heroStep(2)}
            >
              {t('landing.description')}
            </motion.p>

            <motion.div className="mt-10" {...heroStep(3)}>
              <PrimaryAction to="/signup">{t('landing.start')}</PrimaryAction>
            </motion.div>
          </div>

          <motion.a
            href="#services"
            className="absolute bottom-8 left-1/2 flex -translate-x-1/2 flex-col items-center gap-2 font-geist text-[10px] uppercase tracking-[0.28em] text-neutral-400 transition-colors duration-300 hover:text-neutral-950 dark:text-neutral-500 dark:hover:text-neutral-50"
            initial={reduceMotion ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6, ease: EXPO_OUT, delay: 0.9 }}
          >
            <motion.span
              animate={reduceMotion ? {} : { y: [0, 6, 0] }}
              transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }}
              aria-hidden="true"
            >
              ↓
            </motion.span>
            {t('landing.discover')}
          </motion.a>
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
            <Reveal className="max-w-3xl">
              <Eyebrow>01 / {t('landing.navServices')}</Eyebrow>
              <Heading id="services-title">{t('landing.servicesTitle')}</Heading>
              <p className="mt-6 max-w-2xl text-base leading-relaxed text-neutral-600 text-pretty sm:text-lg dark:text-neutral-400">
                {t('landing.servicesLead')}
              </p>
            </Reveal>

            <div className="mt-16 grid grid-cols-1 gap-5 sm:grid-cols-2 sm:gap-6 lg:gap-8">
              {services.map((service, i) => (
                <Reveal key={service.title} delay={0.1 * i}>
                  <motion.article
                    className="group relative h-full overflow-hidden rounded-[2rem] border border-black/5 bg-white/60 p-8 ring-1 ring-black/[0.04] backdrop-blur-xl transition-colors duration-500 hover:border-black/10 sm:rounded-[2.5rem] sm:p-10 dark:border-white/[0.08] dark:bg-white/[0.015] dark:ring-0 dark:hover:border-white/20"
                    whileHover={reduceMotion ? undefined : { y: -6 }}
                    transition={SOFT_SPRING}
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
                      style={{
                        background: `linear-gradient(90deg, transparent, ${ACCENT}66, transparent)`,
                      }}
                      aria-hidden="true"
                    />
                  </motion.article>
                </Reveal>
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
            <Reveal>
              <Eyebrow>02 / {t('landing.navProcess')}</Eyebrow>
              <Heading id="process-title">{t('landing.processTitle')}</Heading>
            </Reveal>

            <ol className="mt-16 divide-y divide-black/5 border-y border-black/5 dark:divide-white/[0.08] dark:border-white/[0.08]">
              {steps.map((step, i) => (
                <Reveal key={step} delay={0.08 * i} y={16}>
                  <li className="group flex items-center gap-6 py-7 transition-colors duration-500 hover:bg-black/[0.02] sm:gap-10 dark:hover:bg-white/[0.02]">
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
                </Reveal>
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
            <Reveal>
              <Eyebrow>03 / {t('landing.navShare')}</Eyebrow>
              <Heading id="share-title">{t('landing.shareTitle')}</Heading>
            </Reveal>

            <div className="mt-16 grid grid-cols-1 gap-6 sm:grid-cols-2 sm:gap-8">
              <Reveal>
                <SplitFigure value={70} label={t('landing.creatorShare')} accent />
              </Reveal>
              <Reveal delay={0.12}>
                <SplitFigure value={30} label={t('landing.platformShare')} accent={false} />
              </Reveal>
            </div>

            <Reveal delay={0.2}>
              <p
                className="mt-8 rounded-[1.5rem] border px-6 py-5 text-sm leading-relaxed text-neutral-700 text-pretty dark:text-neutral-300"
                style={{ borderColor: `${ACCENT}40`, backgroundColor: `${ACCENT}0f` }}
              >
                {t('landing.shareScope')}
              </p>
              <p className="mt-6 text-sm leading-relaxed text-neutral-500 text-pretty dark:text-neutral-500">
                {t('landing.shareDetails')}
              </p>
            </Reveal>
          </div>
        </section>

        {/* ------------------------------------------------------------- faq */}
        <section
          id="faq"
          aria-labelledby="faq-title"
          className="relative overflow-hidden bg-[#fafafa] px-4 py-24 transition-colors duration-500 sm:py-32 dark:bg-[#070707]"
        >
          <div className="landing-faq mx-auto max-w-4xl">
            <Reveal>
              <Eyebrow>04 / FAQ</Eyebrow>
              <Heading id="faq-title">{t('landing.faqTitle')}</Heading>
            </Reveal>

            <div className="mt-16 space-y-4">
              {faqs.map((faq, i) => (
                <Reveal key={faq.q} delay={0.08 * i} y={16}>
                  <details className="group overflow-hidden rounded-[1.5rem] border border-black/5 bg-white/60 ring-1 ring-black/[0.04] backdrop-blur-xl transition-colors duration-500 open:border-black/10 sm:rounded-[2rem] dark:border-white/[0.08] dark:bg-white/[0.015] dark:ring-0 dark:open:border-white/20">
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
                    {/* Answer slides down as the row opens. */}
                    <motion.p
                      className="px-6 pb-6 leading-relaxed text-neutral-600 text-pretty sm:px-8 dark:text-neutral-400"
                      initial={reduceMotion ? false : { opacity: 0, y: -8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.4, ease: EXPO_OUT }}
                    >
                      {faq.a}
                    </motion.p>
                  </details>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        {/* ------------------------------------------------------------- cta */}
        <section className="relative overflow-hidden bg-white px-4 py-24 transition-colors duration-500 sm:py-32 dark:bg-neutral-950">
          <Reveal className="mx-auto max-w-4xl">
            <div className="relative overflow-hidden rounded-[2rem] border border-black/5 bg-white/60 p-10 text-center ring-1 ring-black/[0.04] backdrop-blur-3xl sm:rounded-[2.5rem] sm:p-16 dark:border-white/[0.08] dark:bg-white/[0.015] dark:ring-0">
              <motion.div
                className="pointer-events-none absolute left-1/2 top-0 h-64 w-64 -translate-x-1/2 -translate-y-1/2 rounded-full blur-[90px]"
                style={{ backgroundColor: ACCENT }}
                initial={{ opacity: 0.12 }}
                animate={reduceMotion ? { opacity: 0.12 } : { opacity: [0.08, 0.16, 0.08] }}
                transition={{ duration: 6, repeat: Infinity, ease: 'easeInOut' }}
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
          </Reveal>
        </section>
      </main>

      {/* ------------------------------------------------------------ footer */}
      <footer className="border-t border-black/5 bg-[#fafafa] px-4 py-14 transition-colors duration-500 dark:border-white/[0.08] dark:bg-[#070707]">
        <Reveal y={16}>
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
        </Reveal>
      </footer>
    </div>
  )
}
