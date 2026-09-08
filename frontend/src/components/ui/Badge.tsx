import type { HTMLAttributes } from 'react'

import { cn } from '@/lib/cn'

export type BadgeTone = 'neutral' | 'primary' | 'success' | 'warning' | 'destructive' | 'info'

const toneClasses: Record<BadgeTone, string> = {
  neutral: 'bg-muted text-muted-foreground',
  primary: 'bg-primary-100 text-primary-700 dark:bg-primary-900 dark:text-primary-200',
  success:
    'bg-success-50 text-success-700 dark:bg-success-700/20 dark:text-success-500',
  warning:
    'bg-warning-50 text-warning-700 dark:bg-warning-700/20 dark:text-warning-500',
  destructive:
    'bg-destructive-50 text-destructive-700 dark:bg-destructive-700/20 dark:text-destructive-500',
  info: 'bg-info-50 text-info-600 dark:bg-info-600/20 dark:text-info-500',
}

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone
  /** Small leading dot — gives a non-color signal alongside the tone (WCAG 1.4.1). */
  dot?: boolean
}

export function Badge({ className, tone = 'neutral', dot, children, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium',
        toneClasses[tone],
        className,
      )}
      {...props}
    >
      {dot && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-current" aria-hidden="true" />}
      {children}
    </span>
  )
}
