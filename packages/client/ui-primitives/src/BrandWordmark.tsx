import type { IconProps } from './icons/props.ts'
import { QuanJuLogo } from './QuanJuLogo.tsx'
import { GLYPH_JU, GLYPH_QUAN } from './brandGlyphs.ts'

/** Display options for the official brand wordmark. */
export interface BrandWordmarkProps extends IconProps {
  /** Whether to include the leading mark; defaults to true. */
  includeMark?: boolean | undefined
}

/** Mark width in the 24-unit-tall lockup (the mark box is square). */
const MARK_SIZE = 24
/** Left edge of the lettering, after the mark and its gap. */
const NAME_OFFSET = 26
/** Ink width of the two-character lettering. */
const NAME_WIDTH = 38.23
/** Full lockup width: mark, gap, lettering. */
const WORDMARK_WIDTH = 64.23


/**
 * Render the full brand wordmark.
 * @param props.size - height in px (default 24; width follows the selected artwork).
 * @param props.className - extra class for layout placement.
 * @param props.includeMark - whether to include the leading mark.
 * @returns the wordmark svg (aria-hidden decorative brand art).
 */
export function BrandWordmark({ size = 24, className, includeMark = true }: BrandWordmarkProps) {
  const width = includeMark ? WORDMARK_WIDTH : NAME_WIDTH
  return (
    <svg
      width={(size * width) / 24}
      height={size}
      className={className}
      viewBox={includeMark ? `0 0 ${WORDMARK_WIDTH} 24` : `${NAME_OFFSET} 0 ${NAME_WIDTH} 24`}
      fill="none"
      aria-hidden="true"
    >
      {includeMark && <QuanJuLogo size={MARK_SIZE} />}
      <g fill="currentColor" transform={`translate(${NAME_OFFSET} 0)`}>
        <path d={GLYPH_QUAN} />
        <path d={GLYPH_JU} />
      </g>
    </svg>
  )
}
