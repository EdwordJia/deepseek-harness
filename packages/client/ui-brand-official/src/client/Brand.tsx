import { BrandWordmark, QuanJuLogo } from '@deepseek-ai/dsh-client-ui-primitives'
import type { SidebarBrandMarkOwnerProps, SidebarBrandNameOwnerProps } from '@deepseek-ai/dsh-client-ui-sidebar/client'

/**
 * Render the official mark with the presentation requested by its host surface.
 * @param props - Host-supplied mark presentation.
 * @returns the official 权聚 mark.
 */
export function OfficialBrandMark({ size }: SidebarBrandMarkOwnerProps) {
  return <QuanJuLogo size={size} />
}

/**
 * Render the official name artwork without its independently slotted mark.
 * @param props - Host-supplied wordmark presentation.
 * @returns the official name wordmark.
 */
export function OfficialBrandName({ size }: SidebarBrandNameOwnerProps) {
  return <BrandWordmark includeMark={false} size={size} />
}
