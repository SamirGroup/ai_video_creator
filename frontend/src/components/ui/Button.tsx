import { type ButtonHTMLAttributes, forwardRef } from 'react'

import { cn } from '@/lib/cn'

type Variant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'destructive'
type Size = 'sm' | 'md' | 'lg' | 'icon'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  isLoading?: boolean
}

const variantClasses: Record<Variant, string> = {
  primary:
    'bg-primary-600 text-white hover:bg-primary-700 active:bg-primary-800 disabled:bg-primary-300',
  secondary:
    'bg-muted text-foreground hover:bg-border active:bg-border disabled:opacity-50',
  outline:
    'border border-border bg-transparent text-foreground hover:bg-muted active:bg-border disabled:opacity-50',
  ghost: 'bg-transparent text-foreground hover:bg-muted active:bg-border disabled:opacity-50',
  destructive:
    'bg-destructive-600 text-white hover:bg-destructive-700 active:bg-destructive-700 disabled:bg-destructive-50 disabled:text-destructive-500',
}

const sizeClasses: Record<Size, string> = {
  sm: 'h-8 px-3 text-sm gap-1.5',
  md: 'h-10 px-4 text-sm gap-2',
  lg: 'h-11 px-5 text-base gap-2',
  icon: 'h-10 w-10 p-0',
}

/**
 * Base button covering rest/hover/focus-visible/pressed/disabled/loading states
 * per the interactive-component acceptance gate. `disabled` blocks both click
 * and (via CSS) the hover/active transforms; `isLoading` blocks duplicate
 * submits without changing layout size.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    { className, variant = 'primary', size = 'md', isLoading, disabled, children, ...props },
    ref,
  ) => {
    return (
      <button
        ref={ref}
        className={cn(
          'inline-flex items-center justify-center rounded-md font-medium',
          'transition-colors duration-150 ease-out',
          'disabled:cursor-not-allowed disabled:opacity-60',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
          variantClasses[variant],
          sizeClasses[size],
          className,
        )}
        disabled={disabled || isLoading}
        aria-busy={isLoading || undefined}
        {...props}
      >
        {isLoading && (
          <span
            className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent"
            aria-hidden="true"
          />
        )}
        {children}
      </button>
    )
  },
)
Button.displayName = 'Button'
