import type { RoleCode } from '@/types/common'

export interface NavItem {
  to: string
  labelKey: string
  /** Roles that may see this item; omit to show for every authenticated user. */
  roles?: RoleCode[]
}

export const creatorNavItems: NavItem[] = [
  { to: '/dashboard', labelKey: 'nav.dashboard' },
  { to: '/channel', labelKey: 'nav.channel' },
  { to: '/preferences', labelKey: 'nav.preferences' },
  { to: '/content-plan', labelKey: 'planning.title' },
  { to: '/videos', labelKey: 'nav.videos' },
  { to: '/revenue', labelKey: 'nav.revenue' },
  { to: '/virtual-numbers', labelKey: 'nav.virtualNumbers' },
  { to: '/billing', labelKey: 'nav.billing' },
  { to: '/contract', labelKey: 'nav.contract' },
]

export const adminNavItems: NavItem[] = [
  { to: '/admin/users', labelKey: 'nav.adminUsers', roles: ['admin'] },
  { to: '/admin/videos', labelKey: 'nav.adminVideos', roles: ['admin', 'support'] },
  {
    to: '/admin/moderation',
    labelKey: 'nav.adminModeration',
    roles: ['admin', 'moderator'],
  },
  { to: '/admin/finance', labelKey: 'nav.adminFinance', roles: ['admin', 'finance'] },
  { to: '/admin/virtual-numbers', labelKey: 'nav.virtualNumbers', roles: ['admin'] },
  { to: '/admin/config', labelKey: 'nav.adminConfig', roles: ['admin'] },
]

export const STAFF_ROLES: RoleCode[] = ['admin', 'moderator', 'support', 'finance']
