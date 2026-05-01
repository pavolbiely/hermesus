type Particle = {
  x: number
  y: number
  vx: number
  vy: number
  radius: number
  color: string
  life: number
  ttl: number
}

const COLORS = ['#22c55e', '#38bdf8', '#a78bfa', '#facc15', '#fb7185']
const PARTICLES_PER_BURST = 42
const ANIMATION_MS = 1800

let activeCleanup: (() => void) | undefined

export function launchUpdateFireworks() {
  if (import.meta.server) return
  if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return

  activeCleanup?.()

  const canvas = document.createElement('canvas')
  const maybeContext = canvas.getContext('2d')
  if (!maybeContext) return
  const ctx: CanvasRenderingContext2D = maybeContext

  canvas.setAttribute('aria-hidden', 'true')
  Object.assign(canvas.style, {
    position: 'fixed',
    inset: '0',
    pointerEvents: 'none',
    zIndex: '2147483647'
  })
  document.body.appendChild(canvas)

  const particles: Particle[] = []
  const timeoutIds: number[] = []
  let animationFrame = 0
  const startTime = performance.now()
  let previousTime = startTime

  function resize() {
    const pixelRatio = window.devicePixelRatio || 1
    canvas.width = Math.ceil(window.innerWidth * pixelRatio)
    canvas.height = Math.ceil(window.innerHeight * pixelRatio)
    canvas.style.width = `${window.innerWidth}px`
    canvas.style.height = `${window.innerHeight}px`
    ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)
  }

  function burst(x: number, y: number) {
    for (let index = 0; index < PARTICLES_PER_BURST; index += 1) {
      const angle = Math.random() * Math.PI * 2
      const speed = 2.2 + Math.random() * 4.2
      particles.push({
        x,
        y,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed - 1.6,
        radius: 1.8 + Math.random() * 2.4,
        color: COLORS[Math.floor(Math.random() * COLORS.length)]!,
        life: 0,
        ttl: 850 + Math.random() * 650
      })
    }
  }

  function animate(now: number) {
    const elapsed = now - startTime
    const delta = Math.min(now - previousTime, 32)
    previousTime = now

    ctx.clearRect(0, 0, window.innerWidth, window.innerHeight)
    ctx.globalCompositeOperation = 'lighter'

    for (let index = particles.length - 1; index >= 0; index -= 1) {
      const particle = particles[index]!
      particle.life += delta

      if (particle.life >= particle.ttl) {
        particles.splice(index, 1)
        continue
      }

      particle.x += particle.vx * (delta / 16)
      particle.y += particle.vy * (delta / 16)
      particle.vy += 0.06 * (delta / 16)
      particle.vx *= 0.992

      const opacity = 1 - particle.life / particle.ttl
      ctx.globalAlpha = Math.max(opacity, 0)
      ctx.beginPath()
      ctx.arc(particle.x, particle.y, particle.radius * opacity, 0, Math.PI * 2)
      ctx.fillStyle = particle.color
      ctx.fill()
    }

    ctx.globalAlpha = 1
    ctx.globalCompositeOperation = 'source-over'

    if (elapsed < ANIMATION_MS || particles.length > 0) {
      animationFrame = requestAnimationFrame(animate)
      return
    }

    cleanup()
  }

  function cleanup() {
    cancelAnimationFrame(animationFrame)
    for (const timeoutId of timeoutIds) window.clearTimeout(timeoutId)
    window.removeEventListener('resize', resize)
    canvas.remove()
    if (activeCleanup === cleanup) activeCleanup = undefined
  }

  activeCleanup = cleanup
  resize()
  window.addEventListener('resize', resize)

  const width = window.innerWidth
  const height = window.innerHeight
  burst(width * 0.28, height * 0.26)
  burst(width * 0.72, height * 0.28)
  timeoutIds.push(window.setTimeout(() => burst(width * 0.5, height * 0.2), 220))
  timeoutIds.push(window.setTimeout(() => burst(width * 0.38, height * 0.36), 420))
  timeoutIds.push(window.setTimeout(() => burst(width * 0.62, height * 0.34), 520))

  animationFrame = requestAnimationFrame(animate)
}
