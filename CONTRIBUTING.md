# Contributing to MT5 Discord Trading Bot

Thank you for your interest in contributing to this project! This document provides guidelines and information for contributors.

## 🤝 How to Contribute

### Reporting Issues
- Use GitHub Issues to report bugs or request features
- Provide detailed information about the issue
- Include steps to reproduce the problem
- Specify your environment (Python version, OS, MT5 version)

### Submitting Changes
1. Fork the repository
2. Create a new branch for your feature/fix
3. Make your changes with clear, descriptive commits
4. Test your changes thoroughly
5. Submit a pull request with a detailed description

## 🧪 Testing Guidelines

### Before Submitting
- Test on demo accounts only
- Verify all Discord commands work correctly
- Check that no sensitive information is exposed
- Ensure code follows existing style conventions

### Test Commands
```bash
# Test signal generation
/test_fallback EURUSD
/debug_signals XAUUSD

# Test chart generation
/chart BTCEUR H1

# Test risk management
/demo_stats
/risk_status
```

## 📝 Code Style

### Python Standards
- Follow PEP 8 style guidelines
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions focused and concise

### Trading Logic
- Always include proper risk management
- Document strategy logic clearly
- Use appropriate error handling
- Test with demo accounts first

## 🚨 Security Guidelines

### Sensitive Information
- Never commit API keys, tokens, or credentials
- Use environment variables for configuration
- Sanitize logs to remove sensitive data
- Review code for information leaks

### Trading Safety
- Always validate user inputs
- Implement proper position sizing
- Include maximum loss limits
- Add confirmation steps for risky operations

## 🏗️ Development Setup

### Local Development
```bash
# Clone your fork
git clone https://github.com/yourusername/mt5-discord-bot.git
cd mt5-discord-bot

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Edit .env with your settings

# Run setup
python setup.py
```

### Project Structure
```
├── bot.py                 # Main Discord bot
├── signals.py             # Signal detection
├── mt5_client.py         # MT5 integration
├── risk_manager.py       # Risk management
├── charts.py             # Chart generation
├── advanced_filters.py   # Advanced filtering
├── trailing_stops.py     # Profit protection
├── multi_timeframe.py    # Cross-timeframe analysis
├── market_opening_system.py # Session alerts
├── position_manager.py   # Trade execution
├── trading_rules.py      # Rule engine
├── secrets_store.py      # Credential management
└── rules_config.json     # Strategy configuration
```

## 🎯 Areas for Contribution

### High Priority
- Additional trading strategies
- Improved risk management algorithms
- Better error handling and logging
- Performance optimizations
- Documentation improvements

### Medium Priority
- New technical indicators
- Additional chart types
- Mobile-friendly Discord interfaces
- Backtesting capabilities
- Strategy optimization tools

### Low Priority
- UI/UX improvements
- Additional language support
- Integration with other platforms
- Advanced analytics features

## 📚 Resources

### Trading Knowledge
- Understanding of forex/crypto markets
- Technical analysis concepts
- Risk management principles
- MetaTrader 5 platform knowledge

### Technical Skills
- Python programming
- Discord bot development
- Financial data handling
- Asynchronous programming

## ⚖️ Legal Considerations

### Trading Disclaimer
- This is educational software only
- Contributors are not responsible for trading losses
- Always test thoroughly before live trading
- Include appropriate risk warnings

### Code License
- All contributions are subject to MIT License
- Ensure you have rights to contribute code
- Don't include proprietary algorithms without permission

## 🆘 Getting Help

### Documentation
- Check README.md for basic setup
- Use `/help` command in Discord for usage
- Review existing issues for common problems

### Community
- GitHub Discussions for general questions
- Issues for specific bugs or features
- Pull Request reviews for code feedback

## 🔄 Release Process

### Version Numbering
- Major.Minor.Patch (e.g., 2.1.0)
- Major: Breaking changes or major features
- Minor: New features, backward compatible
- Patch: Bug fixes and small improvements

### Release Checklist
- [ ] All tests pass
- [ ] Documentation updated
- [ ] Version number incremented
- [ ] Changelog updated
- [ ] Security review completed
- [ ] Demo testing completed

Thank you for contributing to make this project better! 🚀