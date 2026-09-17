import { useEffect, useRef } from 'react'

/** Canvas counterpart of the reference site's dotted, rotating hero globe. */
export function ParticleGlobe() {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const context = canvas.getContext('2d')
    if (!context) return
    const reduced = matchMedia('(prefers-reduced-motion: reduce)')
    let frame = 0
    function draw(time: number) {
      if (!canvas || !context) return
      const width = canvas.clientWidth,
        height = canvas.clientHeight
      const ratio = Math.min(devicePixelRatio, 2)
      if (canvas.width !== width * ratio || canvas.height !== height * ratio) {
        canvas.width = width * ratio
        canvas.height = height * ratio
      }
      context.setTransform(ratio, 0, 0, ratio, 0, 0)
      context.clearRect(0, 0, width, height)
      const radius = Math.min(width * 0.43, height * 0.47)
      const rotation = reduced.matches ? 0 : time / 18000
      for (let latitude = 1; latitude < 45; latitude++) {
        const phi = (latitude / 45) * Math.PI
        for (let longitude = 0; longitude < 95; longitude++) {
          const theta = (longitude / 95) * Math.PI * 2 + rotation
          const x = Math.sin(phi) * Math.cos(theta)
          const z = Math.sin(phi) * Math.sin(theta)
          const y = Math.cos(phi)
          const scale = 1 + z * 0.13
          context.beginPath()
          context.fillStyle = `rgba(210,202,172,${0.035 + (z + 1) * 0.05})`
          context.arc(
            width / 2 + x * radius * scale,
            height / 2 + y * radius * 0.78 * scale,
            1 + (z + 1) * 1.2,
            0,
            Math.PI * 2,
          )
          context.fill()
        }
      }
      frame = requestAnimationFrame(draw)
    }
    frame = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(frame)
  }, [])
  return <canvas ref={ref} className="marketing-globe" aria-hidden="true" />
}
