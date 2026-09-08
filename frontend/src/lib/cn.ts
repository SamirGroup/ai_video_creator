import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** Merge Tailwind class lists safely (last conflicting utility wins). */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
