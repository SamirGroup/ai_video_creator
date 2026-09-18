import { useQuery } from '@tanstack/react-query'
import { authLogosApi } from '@/api/authLogos'
import { memo, type CSSProperties } from 'react'
import {
  Clapperboard,
  Film,
  Globe2,
  Mic2,
  Play,
  Sparkles,
  Subtitles,
  Video,
} from 'lucide-react'

// Ripple/orbit animation adapted from the supplied Modern Animated Sign In.
// Decoration only: authentication stays in the existing validated forms.
const icons = [Clapperboard, Film, Globe2, Mic2, Play, Sparkles, Subtitles, Video]

export const AuthOrbitBackground = memo(function AuthOrbitBackground() {
  const { data } = useQuery({
    queryKey: ['public-auth-logos'],
    queryFn: authLogosApi.publicList,
    refetchInterval: 60000,
  })
  const logos = Array.isArray(data) ? data : []
  return (
    <div className="auth-orbit-background">
      <div className="auth-orbit-stage">
        {[320, 460, 600, 760, 920, 1080].map((size, index) => (
          <span
            key={size}
            className="auth-ripple-ring"
            style={{
              width: size,
              height: size,
              animationDelay: `${index * -0.6}s`,
              opacity: 0.32 - index * 0.035,
            }}
          />
        ))}
        {(logos.length ? logos : icons).map((item, index) => {
          const logo = typeof item === 'object' && 'image_url' in item ? item : null
          const Icon = icons[index % icons.length]
          return (
            <span
              key={index}
              className="auth-orbit-track"
              style={
                {
                  '--orbit-radius': `${290 + (index % 3) * 95}px`,
                  '--orbit-duration': `${38 + (index % 3) * 9}s`,
                  '--orbit-delay': `${-index * 7}s`,
                  animationDirection: index % 2 ? 'reverse' : 'normal',
                } as CSSProperties
              }
            >
              {logo ? (
                <a
                  className="auth-orbit-icon auth-orbit-link"
                  href={logo.link_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={logo.name}
                  title={logo.name}
                >
                  <img
                    src={logo.image_url}
                    alt=""
                    referrerPolicy="no-referrer"
                    className="h-8 w-8 object-contain"
                  />
                </a>
              ) : (
                <span className="auth-orbit-icon" aria-hidden="true">
                  <Icon size={25} strokeWidth={1.5} />
                </span>
              )}
            </span>
          )
        })}
      </div>
    </div>
  )
})
