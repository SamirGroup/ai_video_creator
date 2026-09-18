import { useEffect, useRef } from 'react'
import { useReducedMotion } from 'framer-motion'

// Periodic displacement adapted from myweb.uz's Jv/Qv particle shader.
function noise(x: number, z: number, time: number) {
  return (
    (Math.sin(x * 2 + time) * Math.cos(z * 1.5 + time) +
      Math.sin(x * 3.2 + time * 2) * Math.cos(z * 2.1 + time) * 0.6 +
      Math.sin(x * 1.7 + time) * Math.cos(z * 2.8 + time * 3) * 0.4 +
      Math.sin(x * z * 0.5 + time * 2) * 0.3) *
    0.3
  )
}

export function MyWebParticleBackground({ tone = 'light' }: { tone?: 'light' | 'dark' }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const reduced = useReducedMotion()
  useEffect(() => {
    const canvas = ref.current
    const context = canvas?.getContext('2d')
    if (!canvas || !context) return
    let frame = 0
    let width = 0
    let height = 0
    let last = 0
    const draw = (now: number) => {
      if (now - last >= 32 || reduced) {
        last = now
        context.clearRect(0, 0, width, height)
        const time = reduced ? 0 : ((now / 1000) * Math.PI * 2) / 24
        const count = width < 640 ? 48 : 76
        for (let row = 0; row < count; row++) {
          for (let col = 0; col < count; col++) {
            const x = (col / (count - 1) - 0.5) * 12
            const z = (row / (count - 1) - 0.5) * 12
            const wave = noise(x * 0.6 + 50, z * 0.6, time + 2.094) * 0.52
            const drift = noise(x * 0.6, z * 0.6, time) * 0.52
            const depth = 1 + (z + 6) * 0.09
            const px = width / 2 + ((x + drift) * width) / 9 / depth
            const py = height * 0.53 + ((z * 0.4 + wave * 2.5) * height) / 7 / depth
            const fade = Math.max(0, 1 - Math.hypot(x, z) / 8)
            const sparkle = 0.65 + Math.sin(col * 1.7 + row * 0.7 + time) * 0.35
            context.fillStyle = `rgba(${col % 3 ? (tone === 'dark' ? '183,82,255' : '103,58,183') : (tone === 'dark' ? '33,195,252' : '14,139,190')},${fade * (0.18 + sparkle * 0.32)})`
            context.beginPath()
            context.arc(px, py, (0.7 + sparkle) / depth, 0, Math.PI * 2)
            context.fill()
          }
        }
      }
      if (!reduced && !document.hidden) frame = requestAnimationFrame(draw)
    }
    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      width = rect.width
      height = rect.height
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5)
      canvas.width = width * dpr
      canvas.height = height * dpr
      context.setTransform(dpr, 0, 0, dpr, 0, 0)
      cancelAnimationFrame(frame)
      last = -Infinity
      draw(performance.now())
    }
    const visibility = () => {
      cancelAnimationFrame(frame)
      if (!document.hidden) {
        last = -Infinity
        draw(performance.now())
      }
    }
    const observer = new ResizeObserver(resize)
    observer.observe(canvas)
    document.addEventListener('visibilitychange', visibility)
    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      document.removeEventListener('visibilitychange', visibility)
    }
  }, [reduced, tone])
  return <canvas ref={ref} className="myweb-auth-particles" aria-hidden="true" />
}
