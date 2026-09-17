import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type Theme = 'light' | 'dark'

interface UiState {
  theme: Theme
  isSidebarOpen: boolean
  toggleTheme: () => void
  setTheme: (theme: Theme) => void
  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
}

/**
 * Client UI state only (theme, sidebar) — safe to persist to localStorage.
 * Never store tokens/PII here (see authStore for session state).
 */
export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      theme: 'light',
      isSidebarOpen: false,
      toggleTheme: () => set((s) => ({ theme: s.theme === 'light' ? 'dark' : 'light' })),
      setTheme: (theme) => set({ theme }),
      toggleSidebar: () => set((s) => ({ isSidebarOpen: !s.isSidebarOpen })),
      setSidebarOpen: (open) => set({ isSidebarOpen: open }),
    }),
    { name: 'ai-youtuber-ui' },
  ),
)
