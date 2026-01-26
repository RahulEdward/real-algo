# RealAlgo - Open Source Algorithmic Trading Platform

**RealAlgo** is a production-ready, open-source algorithmic trading platform built with FastAPI and React. It provides a unified API layer across 24+ Indian brokers, enabling seamless integration with popular platforms like TradingView, Amibroker, Excel, Python, and AI agents.

## Quick Start

```bash
# Clone the repository
git clone https://github.com/RahulEdward/real-algo.git
cd real-algo

# Install UV package manager
pip install uv

# Configure environment
cp .sample.env .env

# Run the application
uv run uvicorn app_fastapi:app --host 127.0.0.1 --port 5000 --reload
```

The application will be available at `http://127.0.0.1:5000`

## Python Compatibility

**Supports Python 3.11, 3.12, 3.13, and 3.14**

## Supported Brokers (24+)

5paisa (Standard + XTS) | AliceBlue | AngelOne | Compositedge | Definedge | Dhan (Live + Sandbox) | Firstock | Flattrade | Fyers | Groww | IBulls | IIFL | Indmoney | JainamXTS | Kotak Neo | Motilal Oswal | Mstock | Paytm Money | Pocketful | Samco | Shoonya (Finvasia) | Tradejini | Upstox | Wisdom Capital | Zebu | Zerodha

All brokers share a unified API interface.

## Core Features

### Unified REST API Layer (`/api/v1/`)
- **Order Management**: Place, modify, cancel orders, basket orders, smart orders
- **Portfolio**: Positions, holdings, order book, trade book, funds
- **Market Data**: Real-time quotes, historical data, market depth, symbol search
- **Advanced**: Option Greeks, margin calculator, synthetic futures, auto-split orders

### Real-Time WebSocket Streaming
- Unified WebSocket proxy server for all brokers (port 8765)
- Subscribe to LTP, Quote, or Market Depth for any symbol
- ZeroMQ-based message bus for high-performance data distribution

### Flow Visual Strategy Builder
Build trading strategies visually without writing code:
- Node-based editor powered by xyflow/React Flow
- Pre-built nodes: Market data, conditions, order execution, notifications
- Real-time execution with live market data

### API Analyzer Mode
Complete testing environment with ₹1 Crore virtual capital:
- Test strategies with real market data without risking money
- Supports all order types (Market, Limit, SL, SL-M)
- Auto square-off at exchange timings

### Action Center
Order approval workflow for manual control:
- **Auto Mode**: Immediate order execution
- **Semi-Auto Mode**: Manual approval required before broker execution

### Python Strategy Manager
Host and run Python strategies directly:
- Built-in code editor with Python syntax highlighting
- Run multiple strategies in parallel with process isolation
- Automated scheduling with IST-based start/stop times

### ChartInk Integration
Direct webhook integration for scanner alerts with BUY, SELL, SHORT, COVER actions.

### AI-Powered Trading (MCP Server)
Connect AI assistants (Claude Desktop, Cursor, Windsurf, ChatGPT) for natural language trading.

### Telegram Bot Integration
Real-time notifications, order alerts, positions, holdings, and interactive commands.

### Advanced Monitoring
- **Latency Monitor**: Track order execution performance
- **Traffic Monitor**: API usage analytics and error tracking
- **PnL Tracker**: Real-time profit/loss with interactive charts

### Enterprise-Grade Security
- Argon2 password hashing
- Fernet symmetric encryption for tokens
- Two-Factor Authentication (TOTP)
- Rate limiting, CSRF protection, CSP headers
- Zero data collection policy

## Technology Stack

### Backend
- **FastAPI** - Modern Python web framework with async support
- **Uvicorn** - ASGI server
- **SQLAlchemy 2.0** - Database ORM
- **python-socketio** - Real-time WebSocket
- **ZeroMQ** - High-performance message bus
- **Pydantic** - Data validation

### Frontend
- **React 19** with TypeScript
- **Vite 7** - Build tool
- **Tailwind CSS 4** - Styling
- **shadcn/ui** - Component library
- **TanStack Query** - Server state management
- **TradingView Lightweight Charts** - Financial charts
- **CodeMirror** - Code editor
- **xyflow/React Flow** - Visual Flow builder

### Databases
- **SQLite** - 4 separate databases (main, logs, latency, sandbox)
- **DuckDB** - Historical market data (Historify)

## Supported Platforms

- Amibroker | TradingView | GoCharting | N8N | Python | GO | Node.js | ChartInk | MetaTrader | Excel | Google Sheets

## Installation Requirements

- **RAM**: 2GB (or 0.5GB + 2GB swap)
- **Disk**: 1GB
- **CPU**: 1 vCPU
- **Python**: 3.11+
- **Node.js**: 20+ (for frontend development)

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

RealAlgo is released under the **AGPL V3.0 License**. See [LICENSE](License.md) for details.

## Disclaimer

**This software is for educational purposes only. Do not risk money which you are afraid to lose. USE THE SOFTWARE AT YOUR OWN RISK. THE AUTHORS AND ALL AFFILIATES ASSUME NO RESPONSIBILITY FOR YOUR TRADING RESULTS.**

Always test your strategies in Analyzer Mode before deploying with real money.

---

Built with ❤️ by traders, for traders.
