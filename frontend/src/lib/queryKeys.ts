/** Query key factories (TanStack Query best practice: hierarchical + serializable). */

export const authKeys = {
  me: () => ['auth', 'me'] as const,
}

export const channelKeys = {
  all: ['channels'] as const,
  list: () => [...channelKeys.all, 'list'] as const,
  detail: (id: string) => [...channelKeys.all, 'detail', id] as const,
  preferences: (channelId: string) =>
    [...channelKeys.all, channelId, 'preferences'] as const,
}

export const videoKeys = {
  all: ['videos'] as const,
  list: (filters: Record<string, unknown>) =>
    [...videoKeys.all, 'list', filters] as const,
  detail: (id: string) => [...videoKeys.all, 'detail', id] as const,
  steps: (id: string) => [...videoKeys.all, 'detail', id, 'steps'] as const,
}

export const revenueKeys = {
  all: ['revenue'] as const,
  summary: (range: Record<string, unknown>) =>
    [...revenueKeys.all, 'summary', range] as const,
  daily: (range: Record<string, unknown>) =>
    [...revenueKeys.all, 'daily', range] as const,
  byVideo: (range: Record<string, unknown>) =>
    [...revenueKeys.all, 'by-video', range] as const,
  statements: () => [...revenueKeys.all, 'statements'] as const,
  statement: (id: string) => [...revenueKeys.all, 'statements', id] as const,
}

export const billingKeys = {
  plans: () => ['billing', 'plans'] as const,
  subscription: () => ['billing', 'subscription'] as const,
  invoices: () => ['billing', 'invoices'] as const,
}

export const contractKeys = {
  current: () => ['contracts', 'current'] as const,
  history: () => ['contracts', 'history'] as const,
}

export const notificationKeys = {
  all: ['notifications'] as const,
  list: () => [...notificationKeys.all, 'list'] as const,
  preferences: () => [...notificationKeys.all, 'preferences'] as const,
}

export const adminKeys = {
  users: (filters: Record<string, unknown>) => ['admin', 'users', filters] as const,
  user: (id: string) => ['admin', 'users', id] as const,
  videos: (filters: Record<string, unknown>) => ['admin', 'videos', filters] as const,
  moderationQueue: () => ['admin', 'moderation', 'queue'] as const,
  financeOverview: () => ['admin', 'finance', 'overview'] as const,
  plans: () => ['admin', 'plans'] as const,
  providers: () => ['admin', 'providers'] as const,
}
