# Quick Start Guide

Get your MT5 Discord Trading Bot up and running in 10 minutes!

## 🚀 Prerequisites

- Python 3.9+ installed
- MetaTrader 5 terminal
- Discord account and server
- Demo trading account (recommended)

## ⚡ 5-Minute Setup

### 1. Clone and Install
```bash
git clone https://github.com/yourusername/mt5-discord-bot.git
cd mt5-discord-bot
python setup.py
```

### 2. Create Discord Bot
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create New Application → Bot
3. Copy the bot token
4. Invite bot to your server with `applications.commands` scope

### 3. Configure Environment
```bash
# Edit .env file
DISCORD_TOKEN=your_bot_token_here
GUILD_ID=your_server_id_here
AUTHORIZED_USER_ID=your_user_id_here
```

### 4. Setup MT5
1. Install MetaTrader 5
2. Login to demo account
3. Enable algorithmic trading (Tools → Options → Expert Advisors)

### 5. Start Bot
```bash
python bot.py
```

## 🎮 First Commands

### Test the Bot
```bash
/help                    # Show all commands
/demo_stats             # Check account status
/pairs_config           # View trading pairs
/market_overview        # Current market status
```

### Generate Your First Signal
```bash
/signal EURUSD          # Manual signal
/test_fallback EURUSD   # Test strategy system
/chart EURUSD H1        # Generate chart
```

### Enable Auto-Signals
```bash
/autosignals            # View status and controls
# Click "🟢 Activar" button to enable
```

## 📊 What You'll See

### Auto-Signal Example
```
🎯 SEÑAL AUTOMÁTICA (ID 1)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 EURUSD | Estrategia: eurusd_advanced
🔄 BUY | Confianza: HIGH

📈 Niveles de Trading:
• Entrada: 1.08450
• Stop Loss: 1.08200
• Take Profit: 1.08950

💡 Análisis: Breakout confirmado con volumen
⏱️ Válida por: 16:45 GMT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎮 Comandos: /accept 1 | /reject 1
```

### Accept Signal
```bash
/accept 1               # Accept signal ID 1
# Choose: Execute Now | Customize | Cancel
```

## ⚙️ Key Settings

### Trading Pairs (Default)
- **EURUSD**: Breakout strategy, 3 trades/day max
- **XAUUSD**: Mean reversion, 2 trades/day max  
- **BTCEUR**: Momentum crypto, 2 trades/day max

### Risk Management
- **Risk per trade**: 1-2% of account
- **Max daily trades**: 7 total
- **R:R ratios**: 2.5-3.5 minimum
- **Auto-signals**: Every 2 minutes

### Safety Features
- **Demo mode**: Enabled by default
- **Kill switch**: Emergency stop available
- **Daily limits**: Prevent overtrading
- **Drawdown protection**: 20% maximum

## 🔧 Customization

### Modify Trading Rules
Edit `rules_config.json`:
```json
{
  "EURUSD": {
    "max_daily_trades": 5,
    "risk_per_trade": 1.5,
    "min_rr_ratio": 3.0
  }
}
```

### Change Auto-Signal Frequency
Edit `.env`:
```env
AUTOSIGNAL_INTERVAL=300  # 5 minutes instead of 2
```

## 🆘 Troubleshooting

### Common Issues

**Bot doesn't start**
- Check Python version (3.9+)
- Verify Discord token in `.env`
- Install requirements: `pip install -r requirements.txt`

**No signals generated**
- Check MT5 connection: `/demo_stats`
- Test strategies: `/test_fallback EURUSD`
- Verify market hours (avoid weekends)

**Commands not working**
- Ensure bot has `applications.commands` permission
- Check if you're the authorized user
- Try `/help` to see available commands

**MT5 connection failed**
- Verify MT5 is running and logged in
- Check if symbols are available
- Enable algorithmic trading in MT5

### Debug Commands
```bash
/debug_signals EURUSD   # Detailed signal analysis
/test_fallback XAUUSD   # Test strategy system
/risk_status            # Check risk management
/trailing_status        # Monitor trailing stops
```

## 📚 Next Steps

### Learn the System
1. Read [README.md](README.md) for complete documentation
2. Check [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) for architecture
3. Review [CONTRIBUTING.md](CONTRIBUTING.md) for development

### Advanced Features
- **Trailing Stops**: Automatic profit protection
- **Market Opening Alerts**: Session-based notifications
- **Multi-timeframe Analysis**: H1 + M15 precision
- **Performance Analytics**: Strategy comparison

### Go Live (When Ready)
1. Test thoroughly on demo for 2+ weeks
2. Change `DEMO_MODE=0` in `.env`
3. Use live MT5 account
4. Start with small position sizes
5. Monitor performance closely

## ⚠️ Important Reminders

- **Always test on demo first**
- **Never risk more than you can afford to lose**
- **Monitor positions regularly**
- **Keep MT5 terminal running**
- **Understand the strategies before using**

Happy trading! 🎯