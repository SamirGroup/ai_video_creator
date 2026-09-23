import { useId } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  ArrowUpRight,
  AudioLines,
  Bot,
  CalendarDays,
  Clapperboard,
  Cpu,
  Layers3,
  Play,
  ShieldCheck,
  Sparkles,
  Video,
} from 'lucide-react'

/** Decorative studio illustration; deliberately contains no simulated metrics. */
export function StudioIllustration() {
  const id = useId()
  return (
    <div className="studio-illustration" aria-hidden="true">
      <svg viewBox="0 0 420 240" fill="none">
        <defs>
          <linearGradient
            id={id}
            x1="60"
            y1="20"
            x2="340"
            y2="230"
            gradientUnits="userSpaceOnUse"
          >
            <stop stopColor="#fb923c" />
            <stop offset="1" stopColor="#a78bfa" />
          </linearGradient>
        </defs>
        <ellipse
          cx="210"
          cy="122"
          rx="172"
          ry="86"
          stroke={`url(#${id})`}
          strokeOpacity=".22"
          transform="rotate(-18 210 122)"
        />
        <ellipse
          cx="210"
          cy="122"
          rx="130"
          ry="112"
          stroke={`url(#${id})`}
          strokeOpacity=".12"
          transform="rotate(32 210 122)"
        />
        <path
          d="M65 65 210 122 347 58M210 122l123 76M210 122 87 192"
          stroke={`url(#${id})`}
          strokeOpacity=".35"
          strokeDasharray="4 7"
        />
        <g className="studio-satellite">
          <rect
            x="34"
            y="34"
            width="64"
            height="64"
            rx="20"
            fill="#292332"
            stroke="#a78bfa"
            strokeOpacity=".45"
          />
          <foreignObject x="53" y="53" width="26" height="26">
            <Bot size={26} color="#c4b5fd" />
          </foreignObject>
        </g>
        <g className="studio-satellite studio-delay">
          <rect
            x="316"
            y="28"
            width="62"
            height="62"
            rx="19"
            fill="#252c30"
            stroke="#67e8f9"
            strokeOpacity=".35"
          />
          <foreignObject x="334" y="46" width="26" height="26">
            <AudioLines size={26} color="#67e8f9" />
          </foreignObject>
        </g>
        <rect
          x="151"
          y="63"
          width="118"
          height="118"
          rx="34"
          fill="#302722"
          stroke={`url(#${id})`}
          strokeWidth="1.5"
        />
        <rect
          x="164"
          y="76"
          width="92"
          height="92"
          rx="26"
          stroke="#fdba74"
          strokeOpacity=".18"
        />
        <path d="m199 102 31 20-31 20v-40Z" fill={`url(#${id})`} />
        <g className="studio-satellite studio-delay">
          <rect
            x="57"
            y="168"
            width="58"
            height="50"
            rx="16"
            fill="#252c30"
            stroke="#6ee7b7"
            strokeOpacity=".3"
          />
          <foreignObject x="75" y="182" width="22" height="22">
            <ShieldCheck size={22} color="#6ee7b7" />
          </foreignObject>
        </g>
        <rect
          x="298"
          y="172"
          width="72"
          height="48"
          rx="16"
          fill="#292332"
          stroke="#c4b5fd"
          strokeOpacity=".3"
        />
        <foreignObject x="322" y="183" width="24" height="24">
          <CalendarDays size={24} color="#c4b5fd" />
        </foreignObject>
        <circle cx="146" cy="32" r="3" fill="#fdba74" />
        <circle cx="284" cy="207" r="3" fill="#c4b5fd" />
      </svg>
    </div>
  )
}

export function WorkspaceHero({ admin = false }: { admin?: boolean }) {
  const { t } = useTranslation()
  return (
    <section className="studio-hero">
      <div className="relative z-10 max-w-lg">
        <span className="studio-kicker">
          <Sparkles size={13} aria-hidden="true" />
          {t(admin ? 'studio.adminLabel' : 'studio.creatorLabel')}
        </span>
        <h2 className="mt-4 text-2xl font-semibold tracking-tight sm:text-3xl">
          {t(admin ? 'studio.adminTitle' : 'studio.creatorTitle')}
        </h2>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-muted-foreground">
          {t(admin ? 'studio.adminDescription' : 'studio.creatorDescription')}
        </p>
        <Link to={admin ? '/admin/config' : '/assistant'} className="studio-cta mt-5">
          {t(admin ? 'studio.configure' : 'studio.openAssistant')}
          <ArrowUpRight size={17} aria-hidden="true" />
        </Link>
      </div>
      <StudioIllustration />
    </section>
  )
}

export function CreatorShortcuts() {
  const { t } = useTranslation()
  const items = [
    {
      to: '/content-plan',
      icon: CalendarDays,
      title: 'planning.title',
      detail: 'studio.planDetail',
      tone: 'violet',
    },
    {
      to: '/videos',
      icon: Clapperboard,
      title: 'nav.videos',
      detail: 'studio.videoDetail',
      tone: 'amber',
    },
    {
      to: '/channel',
      icon: Play,
      title: 'nav.channel',
      detail: 'studio.channelDetail',
      tone: 'mint',
    },
  ]
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {items.map(({ to, icon: Icon, title, detail, tone }) => (
        <Link to={to} className="studio-shortcut group" key={to}>
          <span className={`studio-icon studio-${tone}`}>
            <Icon size={21} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold">{t(title)}</p>
            <p className="mt-1 text-xs text-muted-foreground">{t(detail)}</p>
          </div>
          <ArrowUpRight
            size={16}
            className="shrink-0 text-muted-foreground transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5"
            aria-hidden="true"
          />
        </Link>
      ))}
    </div>
  )
}

/** Neutral service pictograms, not unofficial copies of provider trademarks. */
export function ProviderMark({ service }: { service: string }) {
  const name = service.toLowerCase()
  const Icon = /video|render/.test(name)
    ? Video
    : /audio|voice|tts/.test(name)
      ? AudioLines
      : /llm|text|script|assistant/.test(name)
        ? Bot
        : /image/.test(name)
          ? Layers3
          : Cpu
  return (
    <span className="studio-icon studio-violet shrink-0">
      <Icon size={20} aria-hidden="true" />
    </span>
  )
}
