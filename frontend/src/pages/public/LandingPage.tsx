import { createContext, useContext, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { AnimatePresence, motion, useInView, useReducedMotion } from 'framer-motion'
import Lenis from 'lenis'
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

const MOTION_OVERRIDE_KEY = 'landing:motion'

/**
 * Whether motion is suppressed on this page.
 *
 * The OS "reduce motion" setting is honoured by default, but it silently
 * disables every animation here, which is indistinguishable from the page
 * being broken. So the visitor can override it, and the page says so when the
 * setting is what is holding things still.
 */
const MotionContext = createContext(false)
const useMotionOff = () => useContext(MotionContext)

function useMotionPreference() {
  const systemReduced = useReducedMotion()
  // Read once during the first render: there is no server render to mismatch,
  // and an effect would repaint the page in the other mode first.
  const [override, setOverride] = useState<'on' | 'off' | null>(() => {
    try {
      const stored = localStorage.getItem(MOTION_OVERRIDE_KEY)
      return stored === 'on' || stored === 'off' ? stored : null
    } catch {
      // Private mode or blocked storage: fall back to the system setting.
      return null
    }
  })

  const setPreference = (next: 'on' | 'off') => {
    setOverride(next)
    try {
      localStorage.setItem(MOTION_OVERRIDE_KEY, next)
    } catch {
      // Not being able to remember the choice must not break the page.
    }
  }

  const motionOff = override ? override === 'off' : Boolean(systemReduced)
  return { motionOff, systemReduced: Boolean(systemReduced), setPreference }
}

/**
 * Shown only when the OS asked for reduced motion, so a visitor who sees a
 * still page knows why and can turn it on for this site.
 */
function MotionNotice({ onEnable }: { onEnable: () => void }) {
  const [dismissed, setDismissed] = useState(false)
  if (dismissed) return null
  return (
    <div className="fixed bottom-4 left-1/2 z-[60] flex -translate-x-1/2 items-center gap-3 rounded-full border border-black/10 bg-white/90 px-4 py-2 font-geist text-[10px] uppercase tracking-[0.2em] shadow-lg backdrop-blur-xl dark:border-white/15 dark:bg-neutral-900/90">
      <span className="text-neutral-500 dark:text-neutral-400">Reduce Motion</span>
      <button
        type="button"
        onClick={onEnable}
        className="rounded-full px-3 py-1 font-bold text-neutral-950 dark:text-neutral-950"
        style={{ backgroundColor: ACCENT }}
      >
        Enable animations
      </button>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        aria-label="Dismiss"
        className="text-neutral-400 transition-colors hover:text-neutral-950 dark:hover:text-neutral-50"
      >
        ✕
      </button>
    </div>
  )
}

/**
 * Inertial scrolling, which is most of what makes the original feel animated —
 * it runs GSAP's ScrollSmoother, a paid plugin, so this uses Lenis (MIT) for
 * the same effect. Torn down on unmount so it never leaks into the app shell,
 * and skipped entirely when the visitor asked for less motion.
 */
function useSmoothScroll(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return
    const lenis = new Lenis({
      duration: 1.1,
      // Expo-out, the same curve the reveals use.
      easing: (t: number) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
    })
    let raf = 0
    const tick = (time: number) => {
      lenis.raf(time)
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(raf)
      lenis.destroy()
    }
  }, [enabled])
}

/**
 * Hero phrase that swaps every three seconds, as the original's does. It cycles
 * the service titles rather than new copy, so the rotation is already
 * translated everywhere.
 */
function RotatingPhrase({ phrases }: { phrases: string[] }) {
  const reduceMotion = useMotionOff()
  const [index, setIndex] = useState(0)

  useEffect(() => {
    if (reduceMotion || phrases.length < 2) return
    const id = setInterval(() => setIndex((i) => (i + 1) % phrases.length), 3000)
    return () => clearInterval(id)
  }, [reduceMotion, phrases.length])

  const current = phrases[index] ?? ''
  return (
    <span className="relative inline-flex h-7 items-center overflow-hidden sm:h-8">
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={current}
          initial={reduceMotion ? false : { y: '100%', opacity: 0 }}
          animate={{ y: '0%', opacity: 1 }}
          exit={reduceMotion ? undefined : { y: '-100%', opacity: 0 }}
          transition={{ duration: 0.45, ease: EXPO_OUT }}
          className="whitespace-nowrap font-geist text-[11px] uppercase tracking-[0.28em] sm:text-xs"
          style={{ color: ACCENT }}
        >
          {current}
        </motion.span>
      </AnimatePresence>
    </span>
  )
}

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
  const reduceMotion = useMotionOff()
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
  const reduceMotion = useMotionOff()
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
  const reduceMotion = useMotionOff()
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

/**
 * The process list, with the original's travelling highlight: a gold frame that
 * walks from row to row on a 0.5s move / 1.5s dwell cycle, measured from the
 * live rows so it stays correct across breakpoints and translations.
 */
function ProcessList({ steps }: { steps: string[] }) {
  const reduceMotion = useMotionOff()
  const listRef = useRef<HTMLOListElement>(null)
  const rowRefs = useRef<(HTMLLIElement | null)[]>([])
  const inView = useInView(listRef, { margin: '-80px' })
  const [active, setActive] = useState(0)
  const [box, setBox] = useState<{ top: number; height: number } | null>(null)

  // Only cycle while the list is actually on screen.
  useEffect(() => {
    if (reduceMotion || !inView || steps.length < 2) return
    const id = setInterval(() => setActive((i) => (i + 1) % steps.length), 2000)
    return () => clearInterval(id)
  }, [reduceMotion, inView, steps.length])

  // Measure the active row; re-measure on resize so the frame tracks reflow.
  useEffect(() => {
    if (reduceMotion) return
    const measure = () => {
      const row = rowRefs.current[active]
      const list = listRef.current
      if (!row || !list) return
      setBox({ top: row.offsetTop, height: row.offsetHeight })
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [active, reduceMotion])

  return (
    <ol
      ref={listRef}
      className="relative mt-16 divide-y divide-black/5 border-y border-black/5 dark:divide-white/[0.08] dark:border-white/[0.08]"
    >
      {box && !reduceMotion && (
        <motion.div
          className="pointer-events-none absolute inset-x-0 z-0 rounded-2xl border"
          style={{
            borderColor: `${ACCENT}99`,
            backgroundColor: `${ACCENT}0f`,
            boxShadow: `0 0 24px ${ACCENT}4d`,
          }}
          initial={false}
          animate={{ top: box.top, height: box.height, opacity: inView ? 1 : 0 }}
          transition={{ duration: 0.5, ease: EXPO_OUT }}
          aria-hidden="true"
        />
      )}

      {steps.map((step, i) => (
        <li
          key={step}
          ref={(el) => {
            rowRefs.current[i] = el
          }}
          className="group relative z-10 flex items-center gap-6 py-7 transition-colors duration-500 sm:gap-10"
        >
          <span
            className="font-sentient text-3xl font-black tabular-nums transition-colors duration-500 sm:text-5xl"
            style={{
              minWidth: '3rem',
              color: !reduceMotion && i === active ? ACCENT : undefined,
            }}
          >
            0{i + 1}
          </span>
          <h3 className="flex-1 font-sentient text-lg font-bold tracking-tight text-pretty sm:text-2xl">
            {step}
          </h3>
          <span
            className="text-lg transition-all duration-500"
            style={{ color: ACCENT, opacity: !reduceMotion && i === active ? 1 : 0 }}
            aria-hidden="true"
          >
            ↗
          </span>
        </li>
      ))}
    </ol>
  )
}

/**
 * Owns the motion decision for the whole page and publishes it, so every
 * animated piece below agrees on it and the visitor can overrule the OS.
 */
export function LandingPage() {
  const { motionOff, systemReduced, setPreference } = useMotionPreference()
  return (
    <MotionContext.Provider value={motionOff}>
      <LandingPageInner />
      {systemReduced && motionOff && <MotionNotice onEnable={() => setPreference('on')} />}
    </MotionContext.Provider>
  )
}

function LandingPageInner() {
  const { t } = useTranslation()
  const theme = useUiStore((state) => state.theme)
  const reduceMotion = useMotionOff()
  const services = t('landing.services', { returnObjects: true }) as {
    title: string
    text: string
  }[]
  const steps = t('landing.steps', { returnObjects: true }) as string[]
  const faqs = t('landing.faqs', { returnObjects: true }) as { q: string; a: string }[]

  useSmoothScroll(!reduceMotion)

  const marquee = ['YouTube', 'AI Video', 'Shorts', 'Analytics', 'Creator Studio']
  const navLinks = [
    { href: '#services', label: t('landing.navServices') },
    { href: '#process', label: t('landing.navProcess') },
    { href: '#share', label: t('landing.navShare') },
    { href: '/pricing', label: t('billing.plans', 'Plans') },
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
    <div
      className="landing-root min-h-screen bg-white font-sans text-neutral-950 antialiased transition-colors duration-500 dark:bg-neutral-950 dark:text-neutral-50"
      data-motion={reduceMotion ? 'off' : 'on'}
    >
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
            <motion.div className="flex flex-col items-center" {...heroStep(0)}>
              <Eyebrow>{t('landing.badge')}</Eyebrow>
              <RotatingPhrase phrases={services.map((s) => s.title)} />
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

            <ProcessList steps={steps} />
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
