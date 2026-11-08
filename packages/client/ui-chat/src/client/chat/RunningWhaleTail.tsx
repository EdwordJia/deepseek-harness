/** Animated stamped-page mask and static SVG fallback for the running Chat status. */
import css from './ChatView.module.css'

const REST_PATH = 'M4 1.8H10.2L12.8 4.4V14.2H4ZM5.9 8H10.3M5.9 10.2H10.3M9.3 9.3H13.9V13.9H9.3ZM10.7 10.5H12.5'

/**
 * Render the decorative running icon; the APNG asset owns its animation timing.
 * @returns mask and static SVG selected by browser capabilities and accessibility preferences.
 */
export function RunningWhaleTail() {
  return (
    <span className={css.runningIcon} aria-hidden="true">
      <span className={css.runningWhaleAnimated} />
      <svg className={css.runningWhaleStill} width="100%" height="100%" viewBox="0 0 16 16" fill="none">
        <path d={REST_PATH} stroke="currentColor" strokeWidth={1} />
      </svg>
    </span>
  )
}
