import type { User } from '@/types/auth'

export function homePath(user: User): string {
  if (user.roles.includes('admin')) return '/admin-dashboard'
  if (user.roles.includes('creator')) return `/creator/${user.id}`
  if (user.roles.includes('support')) return '/admin/videos'
  if (user.roles.includes('moderator')) return '/admin/moderation'
  if (user.roles.includes('finance')) return '/admin/finance'
  return '/'
}
