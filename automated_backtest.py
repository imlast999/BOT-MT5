#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sistema de Backtesting Automático
Prueba todas las estrategias con datos históricos para identificar la mejor para cada par
"""

import json
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple, Optional
import MetaTrader5 as mt5
from mt5_client import initialize as mt5_initialize, get_candles
from signals import detect_signal, RULES
import logging

logger = logging.getLogger(__name__)

class AutomatedBacktest:
    def __init__(self, initial_balance: float = 5000.0, risk_per_trade: float = 0.5):
        """
        Inicializa el sistema de backtesting automático
        
        Args:
            initial_balance: Balance inicial para el backtesting
            risk_per_trade: Porcentaje de riesgo por trade (0.5 = 0.5%)
        """
        self.initial_balance = initial_balance
        self.risk_per_trade = risk_per_trade / 100.0  # Convertir a decimal
        self.results_file = "automated_backtest_results.json"
        self.detailed_results_file = "detailed_backtest_results.json"
        
        # Cargar configuraciones de estrategias
        self.load_strategy_configs()
        
        # Resultados del backtesting
        self.results = self.load_results()
        self.detailed_results = self.load_detailed_results()
    
    def load_strategy_configs(self):
        """Carga las configuraciones de estrategias desde rules_config.json"""
        try:
            with open('rules_config.json', 'r', encoding='utf-8') as f:
                self.rules_config = json.load(f)
        except Exception as e:
            logger.error(f"Error cargando configuraciones: {e}")
            self.rules_config = {}
    
    def load_results(self) -> Dict:
        """Carga resultados previos del backtesting"""
        if os.path.exists(self.results_file):
            try:
                with open(self.results_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error cargando resultados: {e}")
        
        return {
            "metadata": {
                "created": datetime.now().isoformat(),
                "initial_balance": self.initial_balance,
                "risk_per_trade": self.risk_per_trade * 100
            },
            "strategy_performance": {},
            "pair_analysis": {},
            "best_strategies": {}
        }
    
    def load_detailed_results(self) -> Dict:
        """Carga resultados detallados del backtesting"""
        if os.path.exists(self.detailed_results_file):
            try:
                with open(self.detailed_results_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error cargando resultados detallados: {e}")
        
        return {"trades": []}
    
    def save_results(self):
        """Guarda los resultados del backtesting"""
        try:
            with open(self.results_file, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, indent=2, ensure_ascii=False)
            
            with open(self.detailed_results_file, 'w', encoding='utf-8') as f:
                json.dump(self.detailed_results, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"Error guardando resultados: {e}")
    
    def calculate_position_size(self, entry_price: float, sl_price: float, symbol: str) -> float:
        """
        Calcula el tamaño de posición basado en el riesgo por trade
        
        Args:
            entry_price: Precio de entrada
            sl_price: Precio de stop loss
            symbol: Símbolo del par
            
        Returns:
            Tamaño de posición en lotes
        """
        try:
            # Obtener información del símbolo
            si = mt5.symbol_info(symbol)
            if si is None:
                return 0.01  # Lote mínimo por defecto
            
            # Calcular riesgo en precio
            risk_in_price = abs(entry_price - sl_price)
            if risk_in_price == 0:
                return 0.01
            
            # Calcular valor del pip
            point = si.point
            contract_size = getattr(si, 'trade_contract_size', 100000)
            
            # Riesgo en dinero
            risk_amount = self.initial_balance * self.risk_per_trade
            
            # Calcular lotes
            pip_value = contract_size * point
            risk_in_pips = risk_in_price / point
            
            if risk_in_pips == 0:
                return 0.01
            
            lot_size = risk_amount / (risk_in_pips * pip_value)
            
            # Aplicar límites del símbolo
            vol_min = getattr(si, 'volume_min', 0.01)
            vol_max = getattr(si, 'volume_max', 100.0)
            vol_step = getattr(si, 'volume_step', 0.01)
            
            # Redondear al step más cercano
            lot_size = round(lot_size / vol_step) * vol_step
            lot_size = max(vol_min, min(vol_max, lot_size))
            
            return lot_size
            
        except Exception as e:
            logger.error(f"Error calculando tamaño de posición: {e}")
            return 0.01
    
    def simulate_trade(self, signal: Dict, df: pd.DataFrame, start_index: int) -> Dict:
        """
        Simula un trade basado en una señal
        
        Args:
            signal: Diccionario con información de la señal
            df: DataFrame con datos históricos
            start_index: Índice donde inicia el trade
            
        Returns:
            Diccionario con resultado del trade
        """
        try:
            entry_price = float(signal['entry'])
            sl_price = float(signal['sl'])
            tp_price = float(signal['tp'])
            trade_type = signal['type']
            symbol = signal['symbol']
            
            # Calcular tamaño de posición
            lot_size = self.calculate_position_size(entry_price, sl_price, symbol)
            
            # Buscar salida del trade en datos futuros
            max_bars_to_check = min(100, len(df) - start_index - 1)  # Máximo 100 barras o hasta el final
            
            for i in range(start_index + 1, start_index + max_bars_to_check + 1):
                if i >= len(df):
                    break
                
                current_bar = df.iloc[i]
                high = float(current_bar['high'])
                low = float(current_bar['low'])
                close = float(current_bar['close'])
                
                # Verificar si se alcanzó SL o TP
                if trade_type == 'BUY':
                    if low <= sl_price:
                        # Stop Loss alcanzado
                        exit_price = sl_price
                        result = 'LOSS'
                        break
                    elif high >= tp_price:
                        # Take Profit alcanzado
                        exit_price = tp_price
                        result = 'WIN'
                        break
                else:  # SELL
                    if high >= sl_price:
                        # Stop Loss alcanzado
                        exit_price = sl_price
                        result = 'LOSS'
                        break
                    elif low <= tp_price:
                        # Take Profit alcanzado
                        exit_price = tp_price
                        result = 'WIN'
                        break
            else:
                # No se alcanzó ni SL ni TP, cerrar al precio actual
                exit_price = float(df.iloc[start_index + max_bars_to_check]['close'])
                if trade_type == 'BUY':
                    result = 'WIN' if exit_price > entry_price else 'LOSS'
                else:
                    result = 'WIN' if exit_price < entry_price else 'LOSS'
            
            # Calcular P&L
            if trade_type == 'BUY':
                pips = (exit_price - entry_price) / (0.0001 if 'USD' in symbol else 0.1 if 'XAU' in symbol else 1.0)
            else:
                pips = (entry_price - exit_price) / (0.0001 if 'USD' in symbol else 0.1 if 'XAU' in symbol else 1.0)
            
            # Calcular P&L en dinero (aproximado)
            risk_amount = self.initial_balance * self.risk_per_trade
            if result == 'WIN':
                rr_ratio = signal.get('rr_ratio', 2.0)
                pnl = risk_amount * rr_ratio
            else:
                pnl = -risk_amount
            
            return {
                'entry_price': entry_price,
                'exit_price': exit_price,
                'result': result,
                'pips': pips,
                'pnl': pnl,
                'lot_size': lot_size,
                'bars_held': i - start_index if 'i' in locals() else max_bars_to_check
            }
            
        except Exception as e:
            logger.error(f"Error simulando trade: {e}")
            return {
                'entry_price': 0,
                'exit_price': 0,
                'result': 'ERROR',
                'pips': 0,
                'pnl': 0,
                'lot_size': 0.01,
                'bars_held': 0
            }
    
    def backtest_strategy(self, symbol: str, strategy_name: str, config: Dict, 
                         days_back: int = 30, max_trades: int = 100) -> Dict:
        """
        Ejecuta backtesting para una estrategia específica
        
        Args:
            symbol: Par de divisas
            strategy_name: Nombre de la estrategia
            config: Configuración de la estrategia
            days_back: Días hacia atrás para obtener datos
            max_trades: Máximo número de trades a simular
            
        Returns:
            Diccionario con resultados del backtesting
        """
        try:
            print(f"🧪 Backtesting {strategy_name} en {symbol}...")
            
            # Obtener datos históricos
            mt5_initialize()
            df = get_candles(symbol, mt5.TIMEFRAME_H1, days_back * 24)
            
            if df is None or len(df) < 50:
                return {
                    'error': f'Datos insuficientes para {symbol}',
                    'trades': 0,
                    'win_rate': 0,
                    'total_pnl': 0
                }
            
            trades = []
            total_pnl = 0
            wins = 0
            losses = 0
            
            # Iterar por los datos históricos buscando señales
            for i in range(50, len(df) - 10):  # Dejar margen para cálculos
                try:
                    # Obtener subset de datos hasta el punto actual
                    current_df = df.iloc[:i+1].copy()
                    
                    # Detectar señal
                    signal, _ = detect_signal(current_df, strategy=strategy_name, config=config)
                    
                    if signal and len(trades) < max_trades:
                        # Simular el trade
                        trade_result = self.simulate_trade(signal, df, i)
                        
                        if trade_result['result'] != 'ERROR':
                            # Registrar trade
                            trade_data = {
                                'timestamp': df.iloc[i].name.isoformat() if hasattr(df.iloc[i].name, 'isoformat') else str(df.iloc[i].name),
                                'symbol': symbol,
                                'strategy': strategy_name,
                                'signal': signal,
                                'result': trade_result,
                                'confidence': signal.get('confidence', 'MEDIUM')
                            }
                            
                            trades.append(trade_data)
                            total_pnl += trade_result['pnl']
                            
                            if trade_result['result'] == 'WIN':
                                wins += 1
                            else:
                                losses += 1
                            
                            # Saltar algunas barras para evitar trades muy seguidos
                            i += 5
                
                except Exception as e:
                    logger.debug(f"Error en iteración {i}: {e}")
                    continue
            
            # Calcular estadísticas
            total_trades = len(trades)
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
            avg_win = sum([t['result']['pnl'] for t in trades if t['result']['result'] == 'WIN']) / wins if wins > 0 else 0
            avg_loss = sum([t['result']['pnl'] for t in trades if t['result']['result'] == 'LOSS']) / losses if losses > 0 else 0
            profit_factor = abs(avg_win * wins / (avg_loss * losses)) if avg_loss != 0 and losses > 0 else 0
            
            # Calcular máximo drawdown
            running_balance = self.initial_balance
            peak_balance = self.initial_balance
            max_drawdown = 0
            
            for trade in trades:
                running_balance += trade['result']['pnl']
                if running_balance > peak_balance:
                    peak_balance = running_balance
                
                current_drawdown = (peak_balance - running_balance) / peak_balance * 100
                if current_drawdown > max_drawdown:
                    max_drawdown = current_drawdown
            
            final_balance = self.initial_balance + total_pnl
            roi = (final_balance - self.initial_balance) / self.initial_balance * 100
            
            result = {
                'symbol': symbol,
                'strategy': strategy_name,
                'total_trades': total_trades,
                'wins': wins,
                'losses': losses,
                'win_rate': round(win_rate, 2),
                'total_pnl': round(total_pnl, 2),
                'roi': round(roi, 2),
                'avg_win': round(avg_win, 2),
                'avg_loss': round(avg_loss, 2),
                'profit_factor': round(profit_factor, 2),
                'max_drawdown': round(max_drawdown, 2),
                'final_balance': round(final_balance, 2),
                'trades_per_day': round(total_trades / days_back, 2),
                'avg_rr_ratio': round(sum([t['signal'].get('rr_ratio', 0) for t in trades]) / total_trades, 2) if total_trades > 0 else 0,
                'confidence_distribution': self._calculate_confidence_distribution(trades),
                'trades': trades  # Incluir trades detallados
            }
            
            print(f"✅ {strategy_name} en {symbol}: {total_trades} trades, {win_rate:.1f}% WR, {roi:.1f}% ROI")
            return result
            
        except Exception as e:
            logger.error(f"Error en backtesting {strategy_name} para {symbol}: {e}")
            return {
                'error': str(e),
                'symbol': symbol,
                'strategy': strategy_name,
                'total_trades': 0,
                'win_rate': 0,
                'total_pnl': 0
            }
    
    def _calculate_confidence_distribution(self, trades: List[Dict]) -> Dict:
        """Calcula la distribución de niveles de confianza"""
        if not trades:
            return {}
        
        confidence_counts = {}
        for trade in trades:
            confidence = trade.get('confidence', 'MEDIUM')
            confidence_counts[confidence] = confidence_counts.get(confidence, 0) + 1
        
        total = len(trades)
        return {conf: round(count/total*100, 1) for conf, count in confidence_counts.items()}
    
    def run_comprehensive_backtest(self, symbols: List[str] = None, days_back: int = 30) -> Dict:
        """
        Ejecuta backtesting completo para todas las estrategias y pares
        
        Args:
            symbols: Lista de símbolos a probar (None para usar los principales)
            days_back: Días hacia atrás para obtener datos
            
        Returns:
            Diccionario con todos los resultados
        """
        if symbols is None:
            symbols = ['EURUSD', 'XAUUSD', 'BTCEUR']
        
        # Estrategias a probar por símbolo
        strategies_to_test = {
            'EURUSD': [
                ('eurusd_premium', 'EURUSD Premium'),
                ('wick_rejection_eurusd', 'Wick Rejection EUR'),
                ('first_candle_eurusd', 'First Candle EUR'),
                ('liquidity_grab_eurusd', 'Liquidity Grab EUR'),
                ('confluence_breakout', 'Confluence Breakout'),
                ('ema50_200', 'EMA 50/200'),
                ('macd', 'MACD'),
                ('rsi', 'RSI')
            ],
            'XAUUSD': [
                ('xauusd_advanced', 'XAUUSD Advanced'),
                ('wick_rejection_xauusd', 'Wick Rejection Gold'),
                ('first_candle_xauusd', 'First Candle Gold'),
                ('liquidity_grab_xauusd', 'Liquidity Grab Gold'),
                ('macd', 'MACD'),
                ('rsi', 'RSI')
            ],
            'BTCEUR': [
                ('btceur_advanced', 'BTCEUR Advanced'),
                ('liquidity_grab_btceur', 'Liquidity Grab Crypto'),
                ('macd', 'MACD'),
                ('rsi', 'RSI')
            ]
        }
        
        print(f"🚀 Iniciando backtesting completo para {len(symbols)} pares...")
        print(f"📊 Riesgo por trade: {self.risk_per_trade*100}%")
        print(f"💰 Balance inicial: {self.initial_balance} EUR")
        print(f"📅 Período: {days_back} días")
        print("=" * 60)
        
        all_results = {}
        
        for symbol in symbols:
            print(f"\n📈 Procesando {symbol}...")
            symbol_results = {}
            
            strategies = strategies_to_test.get(symbol, [])
            
            for strategy_key, strategy_name in strategies:
                # Obtener configuración de la estrategia
                config = self.rules_config.get(symbol, {}).copy()
                if not config:
                    config = {}
                
                config['symbol'] = symbol
                
                # Ejecutar backtesting
                result = self.backtest_strategy(symbol, strategy_key, config, days_back)
                symbol_results[strategy_key] = result
            
            all_results[symbol] = symbol_results
        
        # Analizar resultados y encontrar mejores estrategias
        best_strategies = self._analyze_results(all_results)
        
        # Actualizar resultados globales
        self.results['strategy_performance'] = all_results
        self.results['best_strategies'] = best_strategies
        self.results['metadata']['last_backtest'] = datetime.now().isoformat()
        self.results['metadata']['days_tested'] = days_back
        
        # Guardar trades detallados
        for symbol, strategies in all_results.items():
            for strategy, result in strategies.items():
                if 'trades' in result:
                    self.detailed_results['trades'].extend(result['trades'])
        
        # Guardar resultados
        self.save_results()
        
        print("\n" + "=" * 60)
        print("🎯 BACKTESTING COMPLETO - MEJORES ESTRATEGIAS:")
        print("=" * 60)
        
        for symbol, best_strategy in best_strategies.items():
            if 'error' not in best_strategy:
                print(f"🏆 {symbol}: {best_strategy['strategy']} - {best_strategy['win_rate']}% WR, {best_strategy['roi']}% ROI")
        
        return {
            'results': all_results,
            'best_strategies': best_strategies,
            'summary': self._generate_summary(all_results)
        }
    
    def _analyze_results(self, all_results: Dict) -> Dict:
        """Analiza los resultados para encontrar las mejores estrategias por par"""
        best_strategies = {}
        
        for symbol, strategies in all_results.items():
            best_strategy = None
            best_score = -999999
            
            for strategy_name, result in strategies.items():
                if 'error' in result or result.get('total_trades', 0) < 5:
                    continue
                
                # Calcular score compuesto (win rate + ROI - drawdown)
                win_rate = result.get('win_rate', 0)
                roi = result.get('roi', 0)
                max_drawdown = result.get('max_drawdown', 100)
                profit_factor = result.get('profit_factor', 0)
                
                # Score ponderado
                score = (win_rate * 0.3) + (roi * 0.4) + (profit_factor * 10) - (max_drawdown * 0.3)
                
                if score > best_score:
                    best_score = score
                    best_strategy = result.copy()
                    best_strategy['score'] = round(score, 2)
            
            best_strategies[symbol] = best_strategy if best_strategy else {'error': 'No hay estrategias válidas'}
        
        return best_strategies
    
    def _generate_summary(self, all_results: Dict) -> Dict:
        """Genera un resumen general de todos los resultados"""
        total_trades = 0
        total_wins = 0
        total_pnl = 0
        all_strategies = []
        
        for symbol, strategies in all_results.items():
            for strategy_name, result in strategies.items():
                if 'error' not in result:
                    total_trades += result.get('total_trades', 0)
                    total_wins += result.get('wins', 0)
                    total_pnl += result.get('total_pnl', 0)
                    all_strategies.append(result)
        
        overall_win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
        overall_roi = (total_pnl / self.initial_balance * 100) if self.initial_balance > 0 else 0
        
        return {
            'total_strategies_tested': len(all_strategies),
            'total_trades': total_trades,
            'overall_win_rate': round(overall_win_rate, 2),
            'total_pnl': round(total_pnl, 2),
            'overall_roi': round(overall_roi, 2),
            'avg_trades_per_strategy': round(total_trades / len(all_strategies), 1) if all_strategies else 0
        }
    
    def generate_html_report(self) -> str:
        """Genera un reporte HTML completo del backtesting"""
        if not self.results.get('strategy_performance'):
            return "<html><body><h1>No hay datos de backtesting disponibles</h1></body></html>"
        
        html = """
<!DOCTYPE html>
<html>
<head>
    <title>Reporte de Backtesting Automático</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        table { border-collapse: collapse; width: 100%; margin: 20px 0; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        .best { background-color: #d4edda; font-weight: bold; }
        .good { background-color: #fff3cd; }
        .poor { background-color: #f8d7da; }
        .summary { background-color: #e7f3ff; padding: 15px; margin: 20px 0; }
    </style>
</head>
<body>
    <h1>🎯 Reporte de Backtesting Automático</h1>
"""
        
        # Resumen general
        summary = self.results.get('summary', {})
        html += f"""
    <div class="summary">
        <h2>📊 Resumen General</h2>
        <p><strong>Estrategias probadas:</strong> {summary.get('total_strategies_tested', 0)}</p>
        <p><strong>Total de trades:</strong> {summary.get('total_trades', 0)}</p>
        <p><strong>Win rate general:</strong> {summary.get('overall_win_rate', 0)}%</p>
        <p><strong>ROI total:</strong> {summary.get('overall_roi', 0)}%</p>
        <p><strong>Balance inicial:</strong> {self.initial_balance} EUR</p>
        <p><strong>Riesgo por trade:</strong> {self.risk_per_trade*100}%</p>
    </div>
"""
        
        # Mejores estrategias
        best_strategies = self.results.get('best_strategies', {})
        html += """
    <h2>🏆 Mejores Estrategias por Par</h2>
    <table>
        <tr><th>Par</th><th>Estrategia</th><th>Trades</th><th>Win Rate</th><th>ROI</th><th>Profit Factor</th><th>Max DD</th><th>Score</th></tr>
"""
        
        for symbol, strategy in best_strategies.items():
            if 'error' not in strategy:
                html += f"""
        <tr class="best">
            <td>{symbol}</td>
            <td>{strategy.get('strategy', 'N/A')}</td>
            <td>{strategy.get('total_trades', 0)}</td>
            <td>{strategy.get('win_rate', 0)}%</td>
            <td>{strategy.get('roi', 0)}%</td>
            <td>{strategy.get('profit_factor', 0)}</td>
            <td>{strategy.get('max_drawdown', 0)}%</td>
            <td>{strategy.get('score', 0)}</td>
        </tr>"""
        
        html += "</table>"
        
        # Resultados detallados por par
        for symbol, strategies in self.results.get('strategy_performance', {}).items():
            html += f"""
    <h2>📈 {symbol} - Todas las Estrategias</h2>
    <table>
        <tr><th>Estrategia</th><th>Trades</th><th>Win Rate</th><th>ROI</th><th>P&L</th><th>Profit Factor</th><th>Max DD</th><th>Trades/Día</th></tr>
"""
            
            # Ordenar estrategias por ROI
            sorted_strategies = sorted(strategies.items(), 
                                     key=lambda x: x[1].get('roi', -999), reverse=True)
            
            for strategy_name, result in sorted_strategies:
                if 'error' in result:
                    continue
                
                # Determinar clase CSS basada en rendimiento
                roi = result.get('roi', 0)
                css_class = 'best' if roi > 20 else 'good' if roi > 0 else 'poor'
                
                html += f"""
        <tr class="{css_class}">
            <td>{strategy_name}</td>
            <td>{result.get('total_trades', 0)}</td>
            <td>{result.get('win_rate', 0)}%</td>
            <td>{result.get('roi', 0)}%</td>
            <td>{result.get('total_pnl', 0)} EUR</td>
            <td>{result.get('profit_factor', 0)}</td>
            <td>{result.get('max_drawdown', 0)}%</td>
            <td>{result.get('trades_per_day', 0)}</td>
        </tr>"""
            
            html += "</table>"
        
        html += """
</body>
</html>
"""
        
        return html
    
    def save_html_report(self, filename: str = None) -> str:
        """Guarda el reporte HTML en un archivo"""
        if not filename:
            filename = f"backtest_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        
        html_content = self.generate_html_report()
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return filename

# Instancia global del backtester
automated_backtest = AutomatedBacktest()

if __name__ == "__main__":
    # Ejecutar backtesting completo
    print("🚀 Iniciando backtesting automático...")
    results = automated_backtest.run_comprehensive_backtest(days_back=30)
    
    # Generar reporte HTML
    report_file = automated_backtest.save_html_report()
    print(f"📊 Reporte guardado en: {report_file}")