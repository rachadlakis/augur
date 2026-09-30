import { useEffect, useMemo, useRef, useState } from 'react'
import type { PointerEvent } from 'react'
import type { EquityPoint } from '../lib/api'
import { clockTime, money, moneyCompact } from '../lib/format'

const HEIGHT = 240
const PAD = { top: 16, right: 64, bottom: 28, left: 64 }

/** Round tick values (1, 2, 2.5, 5 × 10^n) covering [min, max]. */
function niceTicks(min: number, max: number, count = 4): number[] {
  if (min === max) {
    const pad = Math.max(1, Math.abs(min) * 0.001)
    min -= pad
    max += pad
  }
  const raw = (max - min) / count
  const magnitude = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? raw
  const ticks = []
  for (let v = Math.floor(min / step) * step; v <= max + step * 0.5; v += step) ticks.push(Number(v.toFixed(10)))
  return ticks
}

/** Single-series equity line: one axis, hairline grid, crosshair + tooltip on hover. */
export function EquityChart({ points, baseline }: { points: EquityPoint[]; baseline: number }) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(640)
  const [hover, setHover] = useState<number | null>(null)

  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(280, entry.contentRect.width)))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const geometry = useMemo(() => {
    if (points.length < 2) return null
    const values = points.map((p) => p.equity)
    const ticks = niceTicks(Math.min(...values, baseline), Math.max(...values, baseline))
    const lo = ticks[0]
    const hi = ticks[ticks.length - 1]
    const innerW = width - PAD.left - PAD.right
    const innerH = HEIGHT - PAD.top - PAD.bottom
    const x = (i: number) => PAD.left + (i / (points.length - 1)) * innerW
    const y = (v: number) => PAD.top + (1 - (v - lo) / (hi - lo || 1)) * innerH
    const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.equity).toFixed(1)}`).join('')
    const area = `${line}L${x(points.length - 1).toFixed(1)},${y(lo)}L${x(0).toFixed(1)},${y(lo)}Z`
    return { ticks, x, y, line, area, innerW }
  }, [points, width, baseline])

  if (!geometry) {
    return (
      <div ref={wrapRef} className="chart-empty">
        The equity line appears after the first price updates.
      </div>
    )
  }

  const { ticks, x, y, line, area, innerW } = geometry
  const last = points.length - 1
  const hovered = hover === null ? null : points[hover]
  const labelIdx = [0, Math.floor(last / 2), last]

  const onMove = (event: PointerEvent<SVGRectElement>) => {
    const rect = event.currentTarget.getBoundingClientRect()
    const ratio = (event.clientX - rect.left) / rect.width
    setHover(Math.max(0, Math.min(last, Math.round(ratio * last))))
  }

  return (
    <div ref={wrapRef} className="chart-wrap">
      <svg
        width={width}
        height={HEIGHT}
        role="img"
        aria-label={`Account equity over the session, now ${money(points[last].equity)}`}
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'ArrowLeft') setHover((h) => Math.max(0, (h ?? last) - 1))
          if (e.key === 'ArrowRight') setHover((h) => Math.min(last, (h ?? last) + 1))
          if (e.key === 'Escape') setHover(null)
        }}
        onBlur={() => setHover(null)}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line className="grid" x1={PAD.left} x2={PAD.left + innerW} y1={y(t)} y2={y(t)} />
            <text className="tick" x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end">
              {moneyCompact(t)}
            </text>
          </g>
        ))}
        <line className="baseline-ref" x1={PAD.left} x2={PAD.left + innerW} y1={y(baseline)} y2={y(baseline)} />
        {labelIdx.map((i, k) => (
          <text key={k} className="tick" x={x(i)} y={HEIGHT - 8} textAnchor={k === 0 ? 'start' : k === 2 ? 'end' : 'middle'}>
            {clockTime(points[i].t)}
          </text>
        ))}
        <path className="series-area" d={area} />
        <path className="series-line" d={line} />
        <circle className="series-dot" cx={x(last)} cy={y(points[last].equity)} r={4} />
        <text className="end-label" x={x(last) + 8} y={y(points[last].equity)} dy="0.32em">
          {moneyCompact(points[last].equity)}
        </text>
        {hovered && hover !== null && (
          <g pointerEvents="none">
            <line className="crosshair" x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={HEIGHT - PAD.bottom} />
            <circle className="series-dot" cx={x(hover)} cy={y(hovered.equity)} r={5} />
          </g>
        )}
        <rect
          x={PAD.left}
          y={PAD.top}
          width={innerW}
          height={HEIGHT - PAD.top - PAD.bottom}
          fill="transparent"
          onPointerMove={onMove}
          onPointerLeave={() => setHover(null)}
        />
      </svg>
      {hovered && hover !== null && (
        <div
          className="chart-tooltip"
          style={{ left: Math.min(x(hover) + 12, width - 180), top: Math.max(8, y(hovered.equity) - 56) }}
        >
          <div className="tooltip-value">{money(hovered.equity)}</div>
          <div className="tooltip-meta">
            {clockTime(hovered.t)} · {hovered.equity >= baseline ? 'above' : 'below'} start
          </div>
        </div>
      )}
    </div>
  )
}
