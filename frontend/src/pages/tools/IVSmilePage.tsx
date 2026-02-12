import { useState } from 'react'
import { ToolLayout } from './components/ToolLayout'
import { UnderlyingSelector } from './components/UnderlyingSelector'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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
  ReferenceLine,
} from 'recharts'

interface IVSmileData {
  strike: number
  call_iv: number
  put_iv: number
}

export default function IVSmilePage() {
  const [exchange, setExchange] = useState('NFO')
  const [underlying, setUnderlying] = useState('')
  const [expiry, setExpiry] = useState('')
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<IVSmileData[]>([])
  const [spotPrice, setSpotPrice] = useState<number | null>(null)

  const fetchData = async () => {
    if (!underlying || !expiry) {
      toast.error('Please select underlying and expiry')
      return
    }

    setLoading(true)
    try {
      const response = await fetch('/ivsmile/api/iv-smile-data', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          underlying,
          exchange,
          expiry_date: expiry,
        }),
      })
      const result = await response.json()
      if (result.status === 'success') {
        setData(result.data || [])
        setSpotPrice(result.spot_price || null)
      } else {
        toast.error(result.message || 'Failed to fetch IV smile data')
      }
    } catch (error) {
      toast.error('Failed to fetch IV smile data')
    } finally {
      setLoading(false)
    }
  }

  return (
    <ToolLayout
      title="IV Smile"
      description="Visualize volatility smile across different strikes"
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
            Fetch IV Smile
          </Button>
        </CardContent>
      </Card>

      {data.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>
              IV Smile Chart
              {spotPrice && (
                <span className="ml-2 text-sm font-normal text-muted-foreground">
                  Spot: ₹{spotPrice.toLocaleString()}
                </span>
              )}
            </CardTitle>
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
                  {spotPrice && (
                    <ReferenceLine x={spotPrice} stroke="red" strokeDasharray="5 5" label="ATM" />
                  )}
                  <Line type="monotone" dataKey="call_iv" name="Call IV" stroke="#22c55e" strokeWidth={2} />
                  <Line type="monotone" dataKey="put_iv" name="Put IV" stroke="#ef4444" strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}
    </ToolLayout>
  )
}
