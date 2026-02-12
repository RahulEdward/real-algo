import { useState } from 'react'
import { ToolLayout } from './components/ToolLayout'
import { UnderlyingSelector } from './components/UnderlyingSelector'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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
  ReferenceLine,
} from 'recharts'

interface GEXData {
  strike: number
  call_gex: number
  put_gex: number
  net_gex: number
}

export default function GEXPage() {
  const [exchange, setExchange] = useState('NFO')
  const [underlying, setUnderlying] = useState('')
  const [expiry, setExpiry] = useState('')
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<GEXData[]>([])
  const [spotPrice, setSpotPrice] = useState<number | null>(null)

  const fetchData = async () => {
    if (!underlying || !expiry) {
      toast.error('Please select underlying and expiry')
      return
    }

    setLoading(true)
    try {
      const response = await fetch('/gex/api/gex-data', {
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
        toast.error(result.message || 'Failed to fetch GEX data')
      }
    } catch (error) {
      toast.error('Failed to fetch GEX data')
    } finally {
      setLoading(false)
    }
  }

  return (
    <ToolLayout
      title="GEX (Gamma Exposure)"
      description="Analyze gamma exposure across strikes to understand dealer positioning"
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
            Fetch GEX Data
          </Button>
        </CardContent>
      </Card>

      {data.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>
              Gamma Exposure Chart
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
                <BarChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="strike" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  {spotPrice && (
                    <ReferenceLine x={spotPrice} stroke="red" strokeDasharray="5 5" label="Spot" />
                  )}
                  <Bar dataKey="call_gex" name="Call GEX" fill="#22c55e" />
                  <Bar dataKey="put_gex" name="Put GEX" fill="#ef4444" />
                  <Bar dataKey="net_gex" name="Net GEX" fill="#3b82f6" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}
    </ToolLayout>
  )
}
