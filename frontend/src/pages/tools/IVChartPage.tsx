import { useState, useEffect } from 'react'
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
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'

interface IVDataPoint {
  timestamp: string
  atm_iv: number
  call_iv?: number
  put_iv?: number
}

export default function IVChartPage() {
  const [exchange, setExchange] = useState('NFO')
  const [underlying, setUnderlying] = useState('')
  const [expiry, setExpiry] = useState('')
  const [interval, setInterval] = useState('5m')
  const [days, setDays] = useState('1')
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<IVDataPoint[]>([])
  const [intervals, setIntervals] = useState<string[]>([])

  useEffect(() => {
    fetch('/ivchart/api/intervals')
      .then((res) => res.json())
      .then((result) => {
        if (result.status === 'success' && result.data) {
          const allIntervals = [
            ...(result.data.minutes || []),
            ...(result.data.hours || []),
          ]
          setIntervals(allIntervals)
        }
      })
  }, [])

  const fetchData = async () => {
    if (!underlying || !expiry) {
      toast.error('Please select underlying and expiry')
      return
    }

    setLoading(true)
    try {
      const response = await fetch('/ivchart/api/iv-data', {
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
        toast.error(result.message || 'Failed to fetch IV data')
      }
    } catch (error) {
      toast.error('Failed to fetch IV data')
    } finally {
      setLoading(false)
    }
  }

  return (
    <ToolLayout
      title="IV Chart"
      description="Historical implied volatility charts with multiple intervals"
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
                  {intervals.map((i) => (
                    <SelectItem key={i} value={i}>
                      {i}
                    </SelectItem>
                  ))}
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
                  {[1, 2, 3, 5, 7, 10, 15].map((d) => (
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
            Fetch IV Data
          </Button>
        </CardContent>
      </Card>

      {data.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Implied Volatility Chart</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[500px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="timestamp" />
                  <YAxis domain={['auto', 'auto']} />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="atm_iv" name="ATM IV" stroke="#3b82f6" dot={false} />
                  <Line type="monotone" dataKey="call_iv" name="Call IV" stroke="#22c55e" dot={false} />
                  <Line type="monotone" dataKey="put_iv" name="Put IV" stroke="#ef4444" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}
    </ToolLayout>
  )
}
