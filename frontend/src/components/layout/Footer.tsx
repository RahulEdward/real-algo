import { useEffect, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

interface FooterProps {
  className?: string
}

export function Footer({ className }: FooterProps) {
  const [version, setVersion] = useState<string>('')

  useEffect(() => {
    const fetchVersion = async () => {
      try {
        const response = await fetch('/auth/app-info')
        const data = await response.json()
        if (data.status === 'success') {
          setVersion(data.version)
        }
      } catch (error) {
        console.error('Failed to fetch version:', error)
      }
    }

    fetchVersion()
  }, [])

  return (
    <footer className={cn('mt-auto border-t bg-muted/30', className)}>
      <div className="container mx-auto px-4 py-6">
        <div className="flex flex-col md:flex-row items-center justify-center gap-2 md:gap-4 text-sm text-muted-foreground">
          <div className="flex items-center gap-2">
            <span>Copyright 2026</span>
            <span className="hidden md:inline">|</span>
            <a
              href="https://www.realalgo.in"
              className="text-primary hover:underline font-medium"
              target="_blank"
              rel="noopener noreferrer"
            >
              www.realalgo.in
            </a>
          </div>
          <span className="hidden md:inline">|</span>
          <span className="text-center">Algo Platform for Everyone</span>
          <span className="hidden md:inline">|</span>
          {version && (
            <Badge variant="secondary" className="gap-1">
              <span className="opacity-75">v</span>
              <span>{version}</span>
            </Badge>
          )}
        </div>
      </div>
    </footer>
  )
}
