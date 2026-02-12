import { useState } from 'react'
import { ToolLayout } from './components/ToolLayout'
import { UnderlyingSelector } from './components/UnderlyingSelector'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Loader2, Target } from 'lucide-react'
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
  ReferenceLine,
} from 'recharts'

interface OIData {
  strike: number
  call_oi: number
  put_oi: number
  call_oi_change: number
  put_oi_change: number
}

export default function OITrackerPage() {
  const [exchange, setExchange] = useState('NFO')
  const [underlying, setUnderlying] = useState('')
  const [expiry, setExpiry] = useState('')
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<OIData[]>([])
  const [maxPain, setMaxPain] = useState<number | null>(null)
  const [spotPrice, setSpotPrice] = useState<number | null>(null)

  const fetchData = async () => {
    if (!underlying || !expiry) {
      toast.error('Please select underlying and expiry')
      return
    }

    setLoading(true)
    try {
      const [oiResponse, maxPainResponse] = await Promise.all([
        fetch('/oitracker/api/oi-data', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ underlying, exchange, expiry_date: expiry }),
        }),
        fetch('/oitracker/api/maxpain', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ underlying, exchange, expiry_date: expiry }),
        }),
      ])

      const oiResult = await oiResponse.json()
      const maxPainResult = await maxPainResponse.json()

      if (oiResult.status === 'success') {
        setData(oiResult.data || [])
        setSpotPrice(oiResult.spot_price || null)
      } else {
        toast.error(oiResult.message || 'Failed to fetch OI data')
      }

      if (maxPainResult.status === 'success') {
        setMaxPain(maxPainResult.max_pain || null)
      }
    } catch (error) {
      toast.error('Failed to fetch OI data')
    } finally {
      setLoading(false)
    }
  }

  return (
    <ToolLayout
      title="OI Tracker"
      description="Real-time open interest changes with Max Pain calculation"
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
          <Button onClick={fetchData} disabled={loading}>
            {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Fetch OI Data
          </Button>
        </CardContent>
      </Card>

      {(maxPain || spotPrice) && (
        <div className="grid gap-4 md:grid-cols-2 mb-6">
          {maxPain && (
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center gap-2">
                  <Target className="h-5 w-5 text-orange-500" />
                  <span className="text-muted-foreground">Max Pain:</span>
                  <span className="text-xl font-bold">₹{maxPain.toLocaleString()}</span>
                </div>
              </CardContent>
            </Card>
          )}
          {spotPrice && (
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground">Spot Price:</span>
                  <span className="text-xl font-bold">₹{spotPrice.toLocaleString()}</span>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {data.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Open Interest Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[500px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="strike" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  {maxPain && (
                    <ReferenceLine x={maxPain} stroke="orange" strokeDasharray="5 5" label="Max Pain" />
                  )}
                  {spotPrice && (
                    <ReferenceLine x={spotPrice} stroke="blue" strokeDasharray="5 5" label="Spot" />
                  )}
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
