import type { IconProps } from './icons/props.ts'
import { GLYPH_QUAN } from './brandGlyphs.ts'

/** Native viewBox of the 权聚 mark (square). */
export const QUANJU_LOGO_VIEWBOX = { width: 24, height: 24 }

/* A pleading page — folded corner, three brief lines — carrying the red 权
   seal that makes a document official. */
const PAGE =
  'M13.407 4.125H7.032A1.219 1.219 0 0 0 5.813 5.344V16.781A1.219 1.219 0 0 0 7.032 18H15.094A1.219 1.219 0 0 0 16.313 16.781V7.031Z'
const FOLD = 'M13.407 4.125V5.810A1.221 1.221 0 0 0 15.092 7.031H16.313'

/**
 * Render the 权聚 mark: a pleading document stamped with the red 权 seal.
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
      <g stroke="currentColor" strokeWidth="0.8" strokeLinecap="round" strokeLinejoin="round">
        <path d={PAGE} />
        <path d={FOLD} />
      </g>
      <g stroke="currentColor" strokeWidth="0.65" strokeLinecap="round">
        <path d="M7.688 8.813h6.75" />
        <path d="M7.688 10.875h5.813" />
        <path d="M7.688 12.938h4.125" />
      </g>
      <g transform="rotate(-4 15.094 16.781)">
        <rect x="12" y="13.688" width="6.188" height="6.188" rx="1.031" fill="#B03A2E" />
        <rect
          x="12.563"
          y="14.25"
          width="5.063"
          height="5.063"
          rx="0.656"
          fill="none"
          stroke="#FFFFFF"
          strokeWidth="0.281"
        />
        <g fill="#FFFFFF" transform="translate(13.415 14.608) scale(0.1813)">
          <path d={GLYPH_QUAN} />
        </g>
      </g>
    </svg>
  )
}
