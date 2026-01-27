# Requirements Document

## Introduction

This specification defines the enhancement of the existing semi-automatic trading bot to implement dynamic ATR-based trading rules, replacing fixed pip-based calculations with volatility-adaptive measurements. The system maintains a confidence-based execution model where HIGH confidence signals auto-execute, MEDIUM_HIGH signals require manual confirmation, and lower confidence signals are logged for analysis.

## Glossary

- **ATR**: Average True Range - a volatility indicator measuring price movement
- **Trading_Bot**: The semi-automatic trading system that proposes signals and requires human confirmation
- **Confidence_System**: The scoring mechanism (HIGH/MEDIUM_HIGH/MEDIUM/LOW_MEDIUM) that determines signal quality
- **Signal_Processor**: Component responsible for analyzing market conditions and generating trading signals
- **Rejected_Signal_Logger**: System component that tracks and stores signals that don't meet execution criteria
- **Dynamic_Rules**: Trading rules that adapt to market volatility using ATR calculations instead of fixed values

## Requirements

### Requirement 1: Dynamic ATR-Based Rule Adaptation

**User Story:** As a trader, I want trading rules to adapt to real market volatility using ATR calculations instead of fixed pip values, so that the bot can better respond to changing market conditions.

#### Acceptance Criteria

1. WHEN calculating breakout strength for EURUSD, THE Signal_Processor SHALL use ATR-relative measurements where breakout_size/ATR > 0.6 indicates strong, > 0.4 indicates medium, and > 0.25 indicates weak breakouts
2. WHEN measuring EMA separation for EURUSD, THE Signal_Processor SHALL calculate abs(EMA50-EMA200)/ATR where > 0.5 indicates strong and > 0.3 indicates medium separation
3. WHEN setting stop loss for EURUSD, THE Signal_Processor SHALL use ATR × 1.5 as the stop loss distance
4. WHEN setting take profit for EURUSD, THE Signal_Processor SHALL use stop loss × 2.0 as the take profit distance
5. WHEN calculating stop loss for BTCEUR, THE Signal_Processor SHALL use ATR × 2.5 as the stop loss distance
6. WHEN setting take profit for BTCEUR, THE Signal_Processor SHALL use stop loss × 2.5 as the take profit distance

### Requirement 2: Enhanced EURUSD Breakout Strategy

**User Story:** As a trader, I want improved EURUSD breakout detection with dynamic ATR-based measurements and optimized RSI scoring, so that breakout signals are more accurate and adaptive to market conditions.

#### Acceptance Criteria

1. WHEN analyzing RSI for EURUSD buy signals, THE Signal_Processor SHALL score RSI values between 55-70 as optimal
2. WHEN analyzing RSI for EURUSD sell signals, THE Signal_Processor SHALL score RSI values between 30-45 as optimal
3. WHEN processing EURUSD signals, THE Signal_Processor SHALL maintain a maximum of 4 concurrent trades
4. WHEN calculating breakout strength, THE Signal_Processor SHALL replace fixed pip measurements with ATR-relative calculations
5. WHEN evaluating EMA separation, THE Signal_Processor SHALL use ATR-normalized distances instead of fixed pip values

### Requirement 3: Refined XAUUSD Reversal Strategy

**User Story:** As a trader, I want precise XAUUSD reversal signals with dynamic level generation and session filtering, so that gold trading opportunities are captured more effectively during optimal market hours.

#### Acceptance Criteria

1. WHEN calculating distance to support/resistance levels for XAUUSD, THE Signal_Processor SHALL classify ≤5$ as strong, ≤8$ as medium, and ≤10$ as weak
2. WHEN generating support/resistance levels for XAUUSD, THE Signal_Processor SHALL use dynamic calculation: level = round(price / 50) * 50
3. WHEN processing XAUUSD signals, THE Signal_Processor SHALL only consider signals during London and New York trading sessions
4. WHEN setting stop loss for XAUUSD, THE Signal_Processor SHALL use fixed 12$ distance
5. WHEN setting take profit for XAUUSD, THE Signal_Processor SHALL use fixed 24$ distance
6. WHEN processing XAUUSD signals, THE Signal_Processor SHALL maintain a maximum of 3 concurrent trades
7. WHEN validating XAUUSD reversal signals, THE Signal_Processor SHALL require candle wick ≥30% of total candle range

### Requirement 4: Adaptive BTCEUR Momentum Strategy

**User Story:** As a trader, I want BTCEUR momentum signals that incorporate EMA slope analysis and ATR-relative measurements, so that cryptocurrency trends are captured more effectively with adaptive parameters.

#### Acceptance Criteria

1. WHEN analyzing BTCEUR momentum, THE Signal_Processor SHALL calculate EMA50 slope as EMA50[current] - EMA50[current-3]
2. WHEN EMA50 slope is positive, THE Signal_Processor SHALL favor buy signals for BTCEUR
3. WHEN EMA50 slope is negative, THE Signal_Processor SHALL favor sell signals for BTCEUR
4. WHEN calculating BTCEUR separations, THE Signal_Processor SHALL replace fixed percentage values with ATR-relative measurements
5. WHEN setting signal expiration for BTCEUR, THE Signal_Processor SHALL use 180-240 minute timeframe
6. WHEN processing BTCEUR signals, THE Signal_Processor SHALL maintain a maximum of 4 concurrent trades

### Requirement 5: Streamlined Confidence System

**User Story:** As a trader, I want a simplified confidence scoring system that focuses on essential factors without requiring perfect simultaneous conditions, so that signal evaluation is more practical and less rigid.

#### Acceptance Criteria

1. WHEN calculating confidence scores, THE Signal_Processor SHALL limit evaluation to exactly 2 structural factors, 1 quality factor, and 1 context factor
2. WHEN evaluating signals, THE Signal_Processor SHALL not require perfect scores across all factors simultaneously
3. WHEN assigning confidence levels, THE Signal_Processor SHALL maintain HIGH/MEDIUM_HIGH/MEDIUM/LOW_MEDIUM classifications
4. WHEN scoring signals, THE Signal_Processor SHALL focus on practical signal quality rather than theoretical perfection
5. WHEN processing confidence calculations, THE Signal_Processor SHALL avoid complex AND logic that requires all conditions to be optimal

### Requirement 6: Automated Execution Logic

**User Story:** As a trader, I want the bot to automatically execute only HIGH confidence signals while showing MEDIUM_HIGH signals for manual review, so that I maintain control over trading decisions while benefiting from automation on the best opportunities.

#### Acceptance Criteria

1. WHEN a signal receives HIGH confidence rating, THE Trading_Bot SHALL execute the trade automatically without human intervention
2. WHEN a signal receives MEDIUM_HIGH confidence rating, THE Trading_Bot SHALL display the signal with manual confirmation buttons but not auto-execute
3. WHEN a signal receives MEDIUM, LOW_MEDIUM, or LOW confidence rating, THE Trading_Bot SHALL not display the signal to the user
4. WHEN processing any signal regardless of confidence level, THE Rejected_Signal_Logger SHALL record all signal details for analysis
5. WHEN auto-executing HIGH confidence signals, THE Trading_Bot SHALL apply the appropriate stop loss and take profit levels based on the asset's dynamic rules

### Requirement 7: Comprehensive Rejected Signal Logging

**User Story:** As a trader, I want detailed logging of all rejected signals including reasons and scores, so that I can analyze the bot's filtering effectiveness and understand what trading opportunities were avoided.

#### Acceptance Criteria

1. WHEN any signal is processed, THE Rejected_Signal_Logger SHALL record timestamp, symbol, signal type, confidence level, and score
2. WHEN a signal is rejected, THE Rejected_Signal_Logger SHALL capture specific rejection reasons (e.g., "weak_breakout", "low_atr", "flat_ema")
3. WHEN storing rejected signals, THE Rejected_Signal_Logger SHALL use structured format with timestamp, symbol, confidence, score, and reasons fields
4. WHEN logging rejected signals, THE Rejected_Signal_Logger SHALL persist data to either database or CSV file for later analysis
5. WHEN a signal fails to meet execution criteria, THE Rejected_Signal_Logger SHALL ensure all relevant scoring factors are captured for review

### Requirement 8: Configuration Management

**User Story:** As a trader, I want the bot's new dynamic rules and confidence thresholds to be configurable through the existing configuration system, so that I can fine-tune parameters without code changes.

#### Acceptance Criteria

1. WHEN updating ATR multipliers, THE Signal_Processor SHALL read values from the configuration file
2. WHEN modifying confidence scoring weights, THE Signal_Processor SHALL apply changes from the configuration without restart
3. WHEN adjusting asset-specific parameters, THE Signal_Processor SHALL load settings from the rules configuration
4. WHEN changing session filters, THE Signal_Processor SHALL respect configuration-defined trading hours
5. WHEN updating maximum trade limits per asset, THE Signal_Processor SHALL enforce limits defined in configuration