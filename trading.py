import re
import logging
from typing import List, Dict, Optional
from alpaca_trade_api import REST
from alpaca_trade_api.common import URL
import json
import os

# Logging-Konfiguration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class AlpacaSignalProcessor:
    """Verarbeitet Kryptowährungs-Handelssignale und interagiert mit der Alpaca API."""

    def __init__(self, api_key: str, api_secret: str, base_url: str = 'https://paper-api.alpaca.markets'):
        """Initialisiert die Alpaca API-Verbindung."""
        try:
            self.api = REST(api_key, api_secret, base_url, api_version='v2')
            self.api.get_account()  # Testet die Verbindung
            logger.info("Alpaca API erfolgreich verbunden.")
        except Exception as e:
            logger.error(f"Fehler bei der Alpaca API-Verbindung: {e}")
            raise ConnectionError(f"Alpaca API-Verbindung fehlgeschlagen: {e}")

    def parse_signals(self, response: str) -> List[Dict]:
        """Extrahiert Signale aus der KI-Antwort."""
        try:
            signals_block = re.search(r'\[SIGNAL\](.*?)\[/SIGNAL\]', response, re.DOTALL)
            if not signals_block:
                logger.error("Kein [SIGNAL]-Block gefunden.")
                return []

            signals = signals_block.group(1).strip().split('\n')
            parsed_signals = []

            for signal in signals:
                if not signal.strip():
                    continue
                parts = signal.split(': ')
                if len(parts) < 2:
                    logger.warning(f"Ungültiges Signalformat: {signal}")
                    continue

                crypto = parts[0]
                action_data = parts[1].split(', ')
                action = action_data[0]

                params = {'crypto': crypto, 'action': action}
                for item in action_data[1:]:
                    if '=' in item:
                        key, value = item.split('=')
                        key = key.lower().replace(' ', '_')
                        params[key] = value.replace('%', '')

                parsed_signals.append(params)
            logger.info(f"{len(parsed_signals)} Signale erfolgreich geparst.")
            return parsed_signals
        except Exception as e:
            logger.error(f"Fehler beim Parsen der Signale: {e}")
            return []

    def submit_order(self, signal: Dict) -> None:
        """Sendet ein Signal an die Alpaca API."""
        try:
            crypto = signal['crypto']
            action = signal['action']
            symbol = f"{crypto}USD"
            qty = 1  # Anpassbar

            order_params = {
                'symbol': symbol,
                'qty': qty,
                'time_in_force': 'gtc'
            }

            if action == 'KAUF':
                order_params.update({'side': 'buy', 'type': 'market'})
                self.api.submit_order(**order_params)
                logger.info(f"Marktkauf für {symbol} ausgeführt.")

            elif action == 'LIMIT_KAUF':
                limit_price = float(signal.get('preis'))
                order_params.update({'side': 'buy', 'type': 'limit', 'limit_price': limit_price})
                self.api.submit_order(**order_params)
                logger.info(f"Limit-Kauf für {symbol} bei {limit_price} platziert.")

            elif action == 'VERKAUF':
                order_params.update({'side': 'sell', 'type': 'market'})
                self.api.submit_order(**order_params)
                logger.info(f"Marktverkauf für {symbol} ausgeführt.")

            elif action == 'LIMIT_VERKAUF':
                limit_price = float(signal.get('preis'))
                order_params.update({'side': 'sell', 'type': 'limit', 'limit_price': limit_price})
                self.api.submit_order(**order_params)
                logger.info(f"Limit-Verkauf für {symbol} bei {limit_price} platziert.")

            elif action == 'TAKE_PROFIT':
                take_profit_price = float(signal.get('preis'))
                order_params.update({'side': 'sell', 'type': 'limit', 'limit_price': take_profit_price})
                self.api.submit_order(**order_params)
                logger.info(f"Take-Profit für {symbol} bei {take_profit_price} platziert.")

            elif action == 'TRAILING_STOP':
                trail_percent = float(signal.get('trailing_stop')) / 100
                order_params.update({'side': 'sell', 'type': 'trailing_stop', 'trail_percent': trail_percent})
                self.api.submit_order(**order_params)
                logger.info(f"Trailing Stop für {symbol} mit {trail_percent*100}% gesetzt.")

            elif action == 'HALTEN':
                logger.info(f"{symbol}: Keine Aktion erforderlich.")
                return

            # Zusätzliche Stop-Loss-Order
            if 'stop_loss' in signal:
                stop_price = float(signal.get('preis', self.api.get_latest_trade(symbol).price)) * (1 + float(signal['stop_loss']) / 100)
                stop_order = {
                    'symbol': symbol,
                    'qty': qty,
                    'side': 'sell',
                    'type': 'stop',
                    'stop_price': stop_price,
                    'time_in_force': 'gtc'
                }
                self.api.submit_order(**stop_order)
                logger.info(f"Stop-Loss für {symbol} bei {stop_price} gesetzt.")

        except Exception as e:
            logger.error(f"Fehler beim Senden des Auftrags für {signal['crypto']}: {e}")

    def save_signals(self, signals: List[Dict], output_file: str = 'signals.json') -> None:
        """Speichert Signale als JSON für das Frontend."""
        try:
            with open(output_file, 'w') as f:
                json.dump(signals, f, indent=2)
            logger.info(f"Signale in {output_file} gespeichert.")
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Signale: {e}")

def main():
    # Alpaca API Zugangsdaten
    API_KEY = os.getenv('ALPACA_API_KEY', 'PKKGZTEBC6UNSGUFD1Z7')
    API_SECRET = os.getenv('ALPACA_API_SECRET', 'IFdjAyvhX2RlpUgMwklqAoedUrEsUqdID2u5')

    # Beispiel-KI-Antwort
    response = """
    Bericht...
    [SIGNAL]
    BTC: LIMIT_KAUF, Preis=44.500, Take_Profit=+10%, Trailing_Stop=5%, Konfidenz=92%
    ETH: HALTEN, Konfidenz=90%
    XRP: TAKE_PROFIT, Preis=0.98, Konfidenz=91%
    [/SIGNAL]
    """

    # Signalprozessor initialisieren
    processor = AlpacaSignalProcessor(API_KEY, API_SECRET)

    # Signale parsen und verarbeiten
    signals = processor.parse_signals(response)
    if not signals:
        logger.warning("Keine gültigen Signale gefunden.")
        return

    # Signale an Alpaca senden und speichern
    for signal in signals:
        processor.submit_order(signal)
    processor.save_signals(signals)

if __name__ == "__main__":
    main()
