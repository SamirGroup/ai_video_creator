import { createElement } from 'react'
import {
  Bot,
  LayoutDashboard,
  Radio,
  SlidersHorizontal,
  CalendarDays,
  Clapperboard,
  ChartNoAxesCombined,
  Phone,
  Globe2,
  Landmark,
  CreditCard,
  FileCheck2,
  Handshake,
  Users,
  ShieldCheck,
  Wallet,
  Settings2,
  type LucideIcon,
} from 'lucide-react'
import type { RoleCode } from '@/types/common'

export interface NavItem {
  to: string
  labelKey: string
  /** Roles that may see this item; omit to show for every authenticated user. */
  roles?: RoleCode[]
}

export const creatorNavItems: NavItem[] = [
  { to: '/assistant', labelKey: 'nav.assistant' },
  { to: '/dashboard', labelKey: 'nav.dashboard' },
  { to: '/channel', labelKey: 'nav.channel' },
  { to: '/preferences', labelKey: 'nav.preferences' },
  { to: '/content-plan', labelKey: 'planning.title' },
  { to: '/videos', labelKey: 'nav.videos' },
  { to: '/revenue', labelKey: 'nav.revenue' },
  { to: '/virtual-numbers', labelKey: 'nav.virtualNumbers' },
  { to: '/web-services', labelKey: 'nav.webServices' },
  { to: '/billing', labelKey: 'nav.billing' },
  { to: '/contract', labelKey: 'nav.contract' },
]

export const adminNavItems: NavItem[] = [
  { to: '/admin/partners', labelKey: 'nav.partners', roles: ['admin'] },
  { to: '/admin/users', labelKey: 'nav.adminUsers', roles: ['admin'] },
  { to: '/admin/videos', labelKey: 'nav.adminVideos', roles: ['admin', 'support'] },
  {
    to: '/admin/moderation',
    labelKey: 'nav.adminModeration',
    roles: ['admin', 'moderator'],
  },
  { to: '/admin/finance', labelKey: 'nav.adminFinance', roles: ['admin', 'finance'] },
  { to: '/admin/virtual-numbers', labelKey: 'nav.virtualNumbers', roles: ['admin'] },
  { to: '/admin/web-services', labelKey: 'nav.webServices', roles: ['admin'] },
  { to: '/admin/payoneer', labelKey: 'nav.payoneer', roles: ['admin'] },
  { to: '/admin/config', labelKey: 'nav.adminConfig', roles: ['admin'] },
]

export const STAFF_ROLES: RoleCode[] = ['admin', 'moderator', 'support', 'finance']

const navIcons: Record<string, LucideIcon> = {
  '/assistant': Bot,
  '/dashboard': LayoutDashboard,
  '/admin-dashboard': LayoutDashboard,
  '/channel': Radio,
  '/preferences': SlidersHorizontal,
  '/content-plan': CalendarDays,
  '/videos': Clapperboard,
  '/revenue': ChartNoAxesCombined,
  '/virtual-numbers': Phone,
  '/web-services': Globe2,
  '/billing': CreditCard,
  '/contract': FileCheck2,
  '/admin/partners': Handshake,
  '/admin/users': Users,
  '/admin/videos': Clapperboard,
  '/admin/moderation': ShieldCheck,
  '/admin/finance': Wallet,
  '/admin/virtual-numbers': Phone,
  '/admin/web-services': Globe2,
  '/admin/payoneer': Landmark,
  '/admin/config': Settings2,
}
export function NavIcon({ to }: { to: string }) {
  const Icon = navIcons[to] ?? LayoutDashboard
  return createElement(Icon, { size: 18, strokeWidth: 1.7, 'aria-hidden': true })
}
