import { cn } from '@/lib/utils'

interface FooterProps {
  className?: string
}

export function Footer({ className }: FooterProps) {

  return (
    <footer className={cn('mt-auto', className)}>
    </footer>
  )
}
