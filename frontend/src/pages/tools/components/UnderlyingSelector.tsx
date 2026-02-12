import { useEffect, useState } from 'react'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { searchApi } from '@/api/search'

interface UnderlyingSelectorProps {
  exchange: string
  underlying: string
  expiry: string
  onExchangeChange: (value: string) => void
  onUnderlyingChange: (value: string) => void
  onExpiryChange: (value: string) => void
}

const EXCHANGES = ['NFO', 'BFO', 'MCX', 'CDS']

export function UnderlyingSelector({
  exchange,
  underlying,
  expiry,
  onExchangeChange,
  onUnderlyingChange,
  onExpiryChange,
}: UnderlyingSelectorProps) {
  const [underlyings, setUnderlyings] = useState<string[]>([])
  const [expiries, setExpiries] = useState<string[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (exchange) {
      setLoading(true)
      searchApi
        .getUnderlyings(exchange)
        .then((data) => {
          if (data.status === 'success') {
            setUnderlyings(data.underlyings || [])
          }
        })
        .finally(() => setLoading(false))
    }
  }, [exchange])

  useEffect(() => {
    if (exchange && underlying) {
      searchApi.getExpiries(exchange, underlying).then((data) => {
        if (data.status === 'success') {
          setExpiries(data.expiries || [])
        }
      })
    }
  }, [exchange, underlying])

  return (
    <div className="grid gap-4 md:grid-cols-3">
      <div className="space-y-2">
        <Label>Exchange</Label>
        <Select value={exchange} onValueChange={onExchangeChange}>
          <SelectTrigger>
            <SelectValue placeholder="Select exchange" />
          </SelectTrigger>
          <SelectContent>
            {EXCHANGES.map((ex) => (
              <SelectItem key={ex} value={ex}>
                {ex}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label>Underlying</Label>
        <Select value={underlying} onValueChange={onUnderlyingChange} disabled={loading}>
          <SelectTrigger>
            <SelectValue placeholder={loading ? 'Loading...' : 'Select underlying'} />
          </SelectTrigger>
          <SelectContent>
            {underlyings.map((u) => (
              <SelectItem key={u} value={u}>
                {u}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label>Expiry</Label>
        <Select value={expiry} onValueChange={onExpiryChange}>
          <SelectTrigger>
            <SelectValue placeholder="Select expiry" />
          </SelectTrigger>
          <SelectContent>
            {expiries.map((e) => (
              <SelectItem key={e} value={e}>
                {e}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  )
}
