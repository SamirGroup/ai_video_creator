import { type InputHTMLAttributes, forwardRef, useId } from 'react'

import { cn } from '@/lib/cn'

export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label: string
  error?: string
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className, label, error, id, ...props }, ref) => {
    const generatedId = useId()
    const inputId = id ?? generatedId

    return (
      <div className="flex flex-col gap-1">
        <div className="flex items-start gap-2">
          <input
            ref={ref}
            type="checkbox"
            id={inputId}
            aria-invalid={Boolean(error) || undefined}
            className={cn(
              'mt-0.5 h-4 w-4 shrink-0 rounded border-border text-primary-600',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
              'disabled:cursor-not-allowed disabled:opacity-60',
              className,
            )}
            {...props}
          />
          <label htmlFor={inputId} className="text-sm text-foreground">
            {label}
          </label>
        </div>
        {error && (
          <p role="alert" className="pl-6 text-xs text-destructive-600">
            {error}
          </p>
        )}
      </div>
    )
  },
)
Checkbox.displayName = 'Checkbox'
