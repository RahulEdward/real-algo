import { useState } from 'react'
import { ToolLayout } from './components/ToolLayout'
import { UnderlyingSelector } from './components/UnderlyingSelector'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'

interface OIProfileData {
  strike: number
  call_oi: number
  put_oi: number
}

export default function OIProfilePage() {
  const [exchange, setExchange] = useState('NFO')
  const [underlying, setUnderlying] = useState('')
  const [expiry, setExpiry] = useState('')
  const [interval, setInterval] = useState('5m')
  const [days, setDays] = useState('5')
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<OIProfileData[]>([])

  const fetchData = async () => {
    if (!underlying || !expiry) {
      toast.error('Please select underlying and expiry')
      return
    }

    setLoading(true)
    try {
      const response = await fetch('/oiprofile/api/profile-data', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          underlying,
          exchange,
          expiry_date: expiry,
          interval,
          days: parseInt(days),
        }),
      })
      const result = await response.json()
      if (result.status === 'success') {
        setData(result.data || [])
      } else {
        toast.error(result.message || 'Failed to fetch OI profile data')
      }
    } catch (error) {
      toast.error('Failed to fetch OI profile data')
    } finally {
      setLoading(false)
    }
  }

  return (
    <ToolLayout
      title="OI Profile"
      description="Open interest distribution analysis over time"
    >
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Select Parameters</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <UnderlyingSelector
            exchange={exchange}
            underlying={underlying}
            expiry={expiry}
            onExchangeChange={setExchange}
            onUnderlyingChange={setUnderlying}
            onExpiryChange={setExpiry}
          />
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>Interval</Label>
              <Select value={interval} onValueChange={setInterval}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1m">1m</SelectItem>
                  <SelectItem value="5m">5m</SelectItem>
                  <SelectItem value="15m">15m</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Days</Label>
              <Select value={days} onValueChange={setDays}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {[1, 3, 5, 7, 10, 15, 30].map((d) => (
                    <SelectItem key={d} value={d.toString()}>
                      {d} {d === 1 ? 'day' : 'days'}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <Button onClick={fetchData} disabled={loading}>
            {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Fetch OI Profile
          </Button>
        </CardContent>
      </Card>

      {data.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Open Interest Profile</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[500px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data} layout="vertical" margin={{ top: 20, right: 30, left: 60, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" />
                  <YAxis dataKey="strike" type="category" />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="call_oi" name="Call OI" fill="#22c55e" />
                  <Bar dataKey="put_oi" name="Put OI" fill="#ef4444" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}
    </ToolLayout>
  )
}
