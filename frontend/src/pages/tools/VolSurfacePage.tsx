import { useState, useEffect } from 'react'
import { ToolLayout } from './components/ToolLayout'
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
import { Checkbox } from '@/components/ui/checkbox'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { searchApi } from '@/api/search'
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

const EXCHANGES = ['NFO', 'BFO', 'MCX', 'CDS']
const COLORS = ['#3b82f6', '#22c55e', '#ef4444', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16']

interface VolSurfaceData {
  strike: number
  [key: string]: number
}

export default function VolSurfacePage() {
  const [exchange, setExchange] = useState('NFO')
  const [underlying, setUnderlying] = useState('')
  const [underlyings, setUnderlyings] = useState<string[]>([])
  const [expiries, setExpiries] = useState<string[]>([])
  const [selectedExpiries, setSelectedExpiries] = useState<string[]>([])
  const [strikeCount, setStrikeCount] = useState('15')
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<VolSurfaceData[]>([])

  useEffect(() => {
    if (exchange) {
      searchApi.getUnderlyings(exchange).then((result) => {
        if (result.status === 'success') {
          setUnderlyings(result.underlyings || [])
        }
      })
    }
  }, [exchange])

  useEffect(() => {
    if (exchange && underlying) {
      searchApi.getExpiries(exchange, underlying).then((result) => {
        if (result.status === 'success') {
          setExpiries(result.expiries || [])
          setSelectedExpiries([])
        }
      })
    }
  }, [exchange, underlying])

  const toggleExpiry = (expiry: string) => {
    setSelectedExpiries((prev) =>
      prev.includes(expiry) ? prev.filter((e) => e !== expiry) : [...prev, expiry].slice(0, 8)
    )
  }

  const fetchData = async () => {
    if (!underlying || selectedExpiries.length === 0) {
      toast.error('Please select underlying and at least one expiry')
      return
    }

    setLoading(true)
    try {
      const response = await fetch('/volsurface/api/surface-data', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          underlying,
          exchange,
          expiry_dates: selectedExpiries,
          strike_count: parseInt(strikeCount),
        }),
      })
      const result = await response.json()
      if (result.status === 'success') {
        setData(result.data || [])
      } else {
        toast.error(result.message || 'Failed to fetch vol surface data')
      }
    } catch (error) {
      toast.error('Failed to fetch vol surface data')
    } finally {
      setLoading(false)
    }
  }

  return (
    <ToolLayout
      title="Vol Surface"
      description="Volatility surface visualization across strikes and expiries"
    >
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Select Parameters</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label>Exchange</Label>
              <Select value={exchange} onValueChange={setExchange}>
                <SelectTrigger>
                  <SelectValue />
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
              <Select value={underlying} onValueChange={setUnderlying}>
                <SelectTrigger>
                  <SelectValue placeholder="Select underlying" />
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
              <Label>Strike Count</Label>
              <Select value={strikeCount} onValueChange={setStrikeCount}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {[10, 15, 20, 25, 30, 40].map((c) => (
                    <SelectItem key={c} value={c.toString()}>
                      {c} strikes
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {expiries.length > 0 && (
            <div className="space-y-2">
              <Label>Select Expiries (max 8)</Label>
              <div className="flex flex-wrap gap-3">
                {expiries.slice(0, 12).map((exp) => (
                  <div key={exp} className="flex items-center space-x-2">
                    <Checkbox
                      id={exp}
                      checked={selectedExpiries.includes(exp)}
                      onCheckedChange={() => toggleExpiry(exp)}
                      disabled={!selectedExpiries.includes(exp) && selectedExpiries.length >= 8}
                    />
                    <label htmlFor={exp} className="text-sm cursor-pointer">
                      {exp}
                    </label>
                  </div>
                ))}
              </div>
            </div>
          )}

          <Button onClick={fetchData} disabled={loading}>
            {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Fetch Vol Surface
          </Button>
        </CardContent>
      </Card>

      {data.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Volatility Surface</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[500px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="strike" />
                  <YAxis domain={['auto', 'auto']} />
                  <Tooltip />
                  <Legend />
                  {selectedExpiries.map((exp, idx) => (
                    <Line
                      key={exp}
                      type="monotone"
                      dataKey={exp}
                      name={exp}
                      stroke={COLORS[idx % COLORS.length]}
                      strokeWidth={2}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}
    </ToolLayout>
  )
}
