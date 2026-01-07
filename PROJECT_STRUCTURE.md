# Project Structure

This document explains the organization and purpose of each file in the MT5 Discord Trading Bot project.

## 📁 Core Files

### Main Application
- **`bot.py`** - Main Discord bot with all slash commands and event handlers
- **`signals.py`** - Signal detection engine with multiple trading strategies
- **`mt5_client.py`** - MetaTrader 5 integration and order management
- **`risk_manager.py`** - Risk management, position sizing, and drawdown protection
- **`charts.py`** - Professional chart generation with technical indicators

### Advanced Systems
- **`advanced_filters.py`** - Confluence system, session filters, correlation management
- **`trailing_stops.py`** - Automatic trailing stops with breakeven management
- **`multi_timeframe.py`** - Cross-timeframe analysis (H1 signals, M15 entries)
- **`market_opening_system.py`** - Pre-market analysis and session alerts
- **`position_manager.py`** - Trade execution and position management
- **`trading_rules.py`** - Rule engine and strategy validation
- **`secrets_store.py`** - Secure credential storage and encryption

## ⚙️ Configuration

### Main Configuration
- **`rules_config.json`** - Trading strategies, risk parameters, and system settings
- **`.env`** - Environment variables (Discord tokens, trading settings)
- **`.env.example`** - Template for environment configuration
- **`requirements.txt`** - Python package dependencies

### Setup and Documentation
- **`setup.py`** - Automated setup script for easy installation
- **`README.md`** - Main documentation (English)
- **`README_ES.md`** - Spanish documentation
- **`CONTRIBUTING.md`** - Contribution guidelines
- **`LICENSE`** - MIT license with trading disclaimer
- **`.gitignore`** - Git ignore rules for sensitive files

## 🎯 Strategy System

### Strategy Hierarchy
```
Primary Strategies (Level 1)
├── eurusd_advanced - Breakout confirmation
├── xauusd_advanced - Mean reversion
└── btceur_advanced - Momentum crypto

Fallback Strategies (Level 2)
├── ema50_200 - EMA crossover
├── rsi - RSI oversold/overbought
└── macd - MACD signal line

Emergency Fallback (Level 3)
└── emergency_ema - Simple EMA (disabled by default)
```

### Configuration Structure
```json
{
  "SYMBOL": {
    "strategy": "primary_strategy",
    "fallback_strategy": "backup_strategy",
    "risk_per_trade": 1.2,
    "max_daily_trades": 3,
    "min_rr_ratio": 2.5,
    "use_fallback": true
  }
}
```

## 🔧 System Architecture

### Discord Integration
```
Discord Bot (bot.py)
├── Slash Commands (25+ commands)
├── Interactive Buttons & Modals
├── Auto-signal Broadcasting
└── Real-time Monitoring
```

### Trading Pipeline
```
Market Data (MT5) → Signal Detection → Risk Filters → Position Sizing → Order Execution
                                    ↓
                            Chart Generation → Discord Notification
```

### Risk Management Flow
```
Signal Generated → Confluence Check → Session Filter → Drawdown Check → Correlation Check → Approved/Rejected
```

## 📊 Data Flow

### Signal Generation Process
1. **Data Collection**: Get OHLC data from MT5
2. **Strategy Analysis**: Apply primary strategy logic
3. **Advanced Filtering**: Check confluence, session, risk factors
4. **Fallback System**: Try backup strategies if primary fails
5. **Quality Control**: Validate R:R ratio, confidence level
6. **Notification**: Send to Discord with chart and details

### Order Execution Process
1. **Signal Acceptance**: User accepts via Discord command
2. **Position Sizing**: Calculate lot size based on risk percentage
3. **Symbol Validation**: Ensure symbol is available and formatted correctly
4. **Order Placement**: Execute trade via MT5 API
5. **Confirmation**: Send execution result to Discord
6. **Monitoring**: Track position with trailing stops

## 🛡️ Security Features

### Credential Management
- Environment variables for sensitive data
- Encrypted credential storage option
- No hardcoded tokens or passwords
- Secure Discord user authorization

### Trading Safety
- Maximum daily trade limits
- Drawdown protection
- Position size validation
- Demo mode for testing
- Kill switch for emergency stops

## 🔄 Background Processes

### Automated Systems
- **Auto-signal Loop**: Scans markets every 2 minutes
- **Trailing Stops**: Updates stop losses every 30 seconds
- **Market Opening Alerts**: Monitors session times
- **Risk Monitoring**: Continuous drawdown checking

### Database Operations
- **Signal History**: Track generated signals
- **Trade Counter**: Daily trade limits
- **Performance Metrics**: Win/loss statistics
- **Configuration Backup**: Automatic rule backups

## 📈 Performance Monitoring

### Real-time Metrics
- Account balance and equity
- Open positions and P&L
- Daily/weekly performance
- Strategy success rates
- Risk utilization

### Analytics Features
- Multi-timeframe analysis
- Correlation monitoring
- Volatility tracking
- Session performance
- Strategy comparison

This structure provides a comprehensive trading system with professional-grade features while maintaining security and reliability standards.