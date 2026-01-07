# MT5 Trading Bot with Discord Integration

A sophisticated automated trading bot that integrates MetaTrader 5 with Discord for real-time signal generation, risk management, and trade execution across multiple currency pairs and assets.

## 🚀 Features

### Core Trading Capabilities
- **Multi-Asset Support**: EURUSD, XAUUSD (Gold), BTCEUR (Bitcoin)
- **Advanced Signal Detection**: Multiple strategies with fallback systems
- **Risk Management**: Automated position sizing, drawdown protection, correlation filters
- **Real-time Execution**: Direct MT5 integration with order management
- **Professional Charts**: High-quality candlestick charts with technical indicators

### Discord Integration
- **Slash Commands**: Modern Discord interface with 25+ commands
- **Auto-Signals**: Automated signal broadcasting every 2 minutes
- **Interactive Controls**: Accept/reject signals with buttons and modals
- **Real-time Monitoring**: Live position tracking and performance stats
- **Market Alerts**: Pre-market analysis and session notifications

### Advanced Systems
- **Multi-Timeframe Analysis**: H1 signals with M15 precision entries
- **Trailing Stops**: Automatic profit protection with breakeven management
- **Market Opening Alerts**: Pre-market analysis for London/New York sessions
- **Confluence Filters**: Multiple confirmation system for signal quality
- **Fallback Strategies**: Hierarchical strategy system for consistent signal generation

## 📋 Requirements

### Software Dependencies
- Python 3.9+
- MetaTrader 5 Terminal
- Discord Bot Token
- Required Python packages (see `requirements.txt`)

### Trading Account
- MT5 Demo or Live account
- Supported broker with EURUSD, XAUUSD, BTCEUR access
- Minimum balance: $1000 (recommended $5000+ for demo testing)

## 🛠️ Installation

### 1. Clone Repository
```bash
git clone https://github.com/yourusername/mt5-discord-bot.git
cd mt5-discord-bot
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment
Create a `.env` file with your settings:
```env
# Discord Configuration
DISCORD_TOKEN=your_discord_bot_token
GUILD_ID=your_discord_server_id
AUTHORIZED_USER_ID=your_discord_user_id

# Trading Configuration
AUTOSIGNALS=1
AUTOSIGNAL_INTERVAL=120
AUTOSIGNAL_SYMBOLS=EURUSD,XAUUSD,BTCEUR
MAX_TRADES_PER_DAY=7

# Risk Management
DEFAULT_RISK_PCT=1.0
DEMO_MODE=1
```

### 4. Setup Discord Bot
1. Create a Discord application at [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a bot and copy the token
3. Invite bot to your server with `applications.commands` scope
4. Create a `#signals` channel for automated signals

### 5. Configure MT5
1. Install and login to MetaTrader 5
2. Enable algorithmic trading in Tools → Options → Expert Advisors
3. Ensure EURUSD, XAUUSD, BTCEUR symbols are available

## 🎮 Usage

### Starting the Bot
```bash
python bot.py
```

### Essential Commands

#### Signal Generation
- `/signal [symbol]` - Generate manual signal for specific pair
- `/force_autosignal [symbol]` - Force automatic signal generation
- `/test_fallback [symbol]` - Test fallback strategy system

#### Trading Management
- `/accept [signal_id]` - Accept and execute pending signal
- `/reject [signal_id]` - Reject pending signal
- `/positions` - View open positions
- `/close_position [ticket]` - Close specific position

#### Market Analysis
- `/market_overview` - Current market status for all pairs
- `/chart [symbol] [timeframe]` - Generate professional chart
- `/pre_market_analysis [symbol]` - Pre-market conditions analysis
- `/next_opening` - Next major market opening time

#### Configuration & Monitoring
- `/autosignals` - Control automatic signal generation
- `/pairs_config` - View current pair configurations
- `/demo_stats` - Account statistics and performance
- `/strategy_performance [days]` - Performance by strategy
- `/risk_status` - Current risk management status

### Strategy Configuration

The bot uses a sophisticated configuration system in `rules_config.json`:

```json
{
  "EURUSD": {
    "strategy": "eurusd_advanced",
    "fallback_strategy": "ema50_200",
    "max_daily_trades": 3,
    "min_rr_ratio": 2.5,
    "risk_per_trade": 1.2
  }
}
```

## 🧠 Trading Strategies

### Primary Strategies
1. **EURUSD Advanced**: Breakout confirmation with consolidation detection
2. **XAUUSD Advanced**: Mean reversion at psychological levels
3. **BTCEUR Advanced**: Momentum-based crypto trading

### Fallback System
- **Level 1**: Primary advanced strategies
- **Level 2**: Simple technical indicators (EMA, RSI, MACD)
- **Level 3**: Emergency fallback (disabled by default for quality control)

### Risk Management
- **Position Sizing**: Automatic lot calculation based on account balance
- **Drawdown Protection**: Maximum daily loss limits
- **Correlation Filters**: Prevent over-exposure to correlated pairs
- **Session Filters**: Trade only during optimal market hours

## 📊 Performance Features

### Real-time Monitoring
- Live P&L tracking
- Win rate statistics
- Strategy performance comparison
- Risk metrics dashboard

### Advanced Analytics
- Multi-timeframe analysis
- Confluence scoring system
- Market session optimization
- Volatility-based filtering

## 🔧 Configuration Files

### Core Files
- `bot.py` - Main Discord bot and command handlers
- `signals.py` - Signal detection and strategy implementation
- `mt5_client.py` - MetaTrader 5 integration
- `risk_manager.py` - Risk management and position sizing
- `charts.py` - Professional chart generation

### Advanced Modules
- `advanced_filters.py` - Confluence and filtering systems
- `trailing_stops.py` - Automatic profit protection
- `multi_timeframe.py` - Cross-timeframe analysis
- `market_opening_system.py` - Session-based alerts
- `position_manager.py` - Trade execution and management

### Configuration
- `rules_config.json` - Trading rules and strategy parameters
- `.env` - Environment variables and sensitive data
- `requirements.txt` - Python dependencies

## 🚨 Risk Disclaimer

**This software is for educational and research purposes only. Trading financial instruments involves substantial risk of loss and is not suitable for all investors. Past performance does not guarantee future results.**

- Always test on demo accounts first
- Never risk more than you can afford to lose
- Understand the strategies before using them
- Monitor positions regularly
- Keep MT5 terminal running during trading hours

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## � Licuense

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- **Issues**: Report bugs via GitHub Issues
- **Documentation**: Check the `/help` command in Discord
- **Testing**: Use `/test_fallback` and `/debug_signals` for troubleshooting

## 🔄 Version History

### v2.0.0 (Current)
- Advanced multi-strategy system
- Discord slash commands integration
- Professional chart generation
- Comprehensive risk management
- Market opening alerts
- Trailing stops system

### v1.0.0
- Basic signal generation
- MT5 integration
- Simple Discord commands

---

**⚠️ Remember**: This is a powerful trading tool. Always understand the risks involved in automated trading and test thoroughly before using with real money.