import type { IconProps } from './icons/props.ts'

/** Native viewBox of the 权聚 mark (square). */
export const QUANJU_LOGO_VIEWBOX = { width: 24, height: 24 }

/**
 * Render the 权聚 mark: a pleading document whose folded page frames a balance
 * scale — the written brief and the weighing of rights in one glyph.
 * @param props.size - width in px (default 24; the mark is square).
 * @param props.className - extra class for layout placement.
 * @returns the mark svg (aria-hidden; pair with the wordmark for accessibility).
 */
export function QuanJuLogo({ size = 24, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <g stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14.5 3H6.5A2.5 2.5 0 0 0 4 5.5v13A2.5 2.5 0 0 0 6.5 21h11a2.5 2.5 0 0 0 2.5-2.5V8.5L14.5 3Z" />
        <path d="M14.5 3v3.5A2 2 0 0 0 16.5 8.5H20" />
        <path d="M12 9.2v1.6M8.6 10.8h6.8M12 10.8v4.8M9.8 17.4h4.4M8.6 10.8v1.5M15.4 10.8v1.5" />
        <path d="M7.1 12.3a1.5 1.5 0 0 0 3 0M13.9 12.3a1.5 1.5 0 0 0 3 0" />
      </g>
      <circle cx="12" cy="8.3" r="0.9" fill="currentColor" />
    </svg>
  )
}
