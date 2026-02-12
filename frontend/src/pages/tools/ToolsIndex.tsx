import { Link } from 'react-router-dom'
import {
  Activity,
  BarChart3,
  LineChart,
  TrendingUp,
  Layers,
  Target,
  Waves,
} from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

const tools = [
  {
    title: 'GEX (Gamma Exposure)',
    description: 'Analyze gamma exposure across strikes to understand dealer positioning',
    href: '/tools/gex',
    icon: BarChart3,
    color: 'text-blue-500',
  },
  {
    title: 'IV Chart',
    description: 'Historical implied volatility charts with multiple intervals',
    href: '/tools/ivchart',
    icon: LineChart,
    color: 'text-green-500',
  },
  {
    title: 'IV Smile',
    description: 'Visualize volatility smile across different strikes',
    href: '/tools/ivsmile',
    icon: Waves,
    color: 'text-purple-500',
  },
  {
    title: 'OI Profile',
    description: 'Open interest distribution analysis over time',
    href: '/tools/oiprofile',
    icon: Layers,
    color: 'text-orange-500',
  },
  {
    title: 'OI Tracker',
    description: 'Real-time open interest changes with Max Pain calculation',
    href: '/tools/oitracker',
    icon: Target,
    color: 'text-red-500',
  },
  {
    title: 'Straddle Chart',
    description: 'ATM straddle premium tracking over time',
    href: '/tools/straddle',
    icon: TrendingUp,
    color: 'text-cyan-500',
  },
  {
    title: 'Vol Surface',
    description: '3D volatility surface visualization across strikes and expiries',
    href: '/tools/volsurface',
    icon: Activity,
    color: 'text-pink-500',
  },
]

export default function ToolsIndex() {
  return (
    <div className="container mx-auto py-6 px-4">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Tools Hub</h1>
        <p className="text-muted-foreground">
          Advanced options analytics and visualization tools
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {tools.map((tool) => (
          <Link key={tool.href} to={tool.href}>
            <Card className="h-full hover:bg-accent/50 transition-colors cursor-pointer">
              <CardHeader className="flex flex-row items-center gap-4">
                <tool.icon className={`h-8 w-8 ${tool.color}`} />
                <div>
                  <CardTitle className="text-lg">{tool.title}</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                <CardDescription>{tool.description}</CardDescription>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  )
}
