import logging
from pathlib import Path

import duckdb

from dao_vang.config.settings import AppSettings

from .binance_api import BinanceExecutionClient

logger = logging.getLogger(__name__)

class ExecutionEngine:
    """
    Isolated execution engine that reads alertable signals from the database
    and optionally executes trades on Binance Futures.
    Strictly uses Testnet (paper trading) first.
    """

    def __init__(self, settings: AppSettings, db_path: Path):
        self.settings = settings.execution
        self.db_path = db_path
        self.last_processed_timestamp = 0
        
        if not self.settings.enabled:
            logger.warning("ExecutionEngine is disabled in config. It will not trade.")
            
        if self.settings.enabled and not self.settings.paper_trading:
            # Enforce paper trading constraint for now as per AGENTS.md
            logger.critical("Live trading is currently PROHIBITED. Forcing paper_trading=True.")
            self.settings.paper_trading = True
            
        self._db_conn = None
        self._api_client = None
        if self.settings.api_key and self.settings.api_secret:
            self._api_client = BinanceExecutionClient(self.settings)
        else:
            logger.warning("No API credentials found. ExecutionEngine will run in dry mode.")

    def connect(self):
        """Connect to database and Binance API."""
        from pathlib import Path
        logger.info(f"Connecting ExecutionEngine to {self.db_path} (read-only)")
        self._db_conn = duckdb.connect(str(self.db_path), read_only=True)
        exec_db_path = Path(self.db_path).parent / "execution.duckdb"
        self._exec_conn = duckdb.connect(str(exec_db_path))
        self._exec_conn.execute("CREATE TABLE IF NOT EXISTS executed_signals (prediction_id VARCHAR PRIMARY KEY, executed_at TIMESTAMP)")

    def run_loop(self):
        """Main loop: Poll database and execute trades."""
        if not self.settings.enabled:
            return

        self.connect()
        logger.info("ExecutionEngine started listening for signals...")
        
        try:
            while True:
                self.poll_signals()
                import time
                time.sleep(10)  # Poll every 10 seconds
        except KeyboardInterrupt:
            logger.info("ExecutionEngine stopped.")
        finally:
            if getattr(self, '_db_conn', None):
                self._db_conn.close()
            if getattr(self, '_exec_conn', None):
                self._exec_conn.close()

    def poll_signals(self):
        """Query DuckDB for new actionable alerts."""
        if not getattr(self, '_db_conn', None) or not getattr(self, '_exec_conn', None):
            return
            
        executed = {r[0] for r in self._exec_conn.execute("SELECT prediction_id FROM executed_signals").fetchall()}
            
        query = """
            SELECT
                alert_episode_id, symbol, probability, close_price
            FROM alert_history
            WHERE alert_episode_id IS NOT NULL
              AND COALESCE(shadow_mode, FALSE) = FALSE
            ORDER BY signal_time ASC
        """
        
        try:
            results = self._db_conn.execute(query).fetchall()
            for row in results:
                alert_episode_id, symbol, probability, price = row
                if alert_episode_id in executed:
                    continue
                
                success = self.process_signal(symbol, probability, price, alert_episode_id)
                if success:
                    self._exec_conn.execute("INSERT INTO executed_signals (prediction_id, executed_at) VALUES (?, CURRENT_TIMESTAMP)", [alert_episode_id])
        except Exception as e:
            logger.error(f"Error polling database: {e}")

    def process_signal(self, symbol: str, probability: float, price: float, prediction_id: str) -> bool:
        """Process a single signal and decide whether to enter a trade."""
        logger.info(f"ExecutionEngine evaluating signal: {symbol} probability={probability:.2f} price={price}")
        
        # 0. Check open positions for duplicate symbol
        if self.has_open_position(symbol):
            logger.info(f"Already have open position for {symbol}. Skipping signal.")
            return False

        # 1. Check open positions limit
        if self.get_open_positions_count() >= self.settings.max_open_positions:
            logger.info("Max open positions reached. Skipping signal.")
            return False
            
        # 2. Place order
        return self.execute_trade(symbol, price)

    def has_open_position(self, symbol: str) -> bool:
        """Check if there is already an open position for this symbol on Binance."""
        if not self._api_client:
            return True # Fail-closed
        try:
            positions = self._api_client.get_open_positions()
            return any(getattr(p, 'symbol', p.get('symbol', '')) == symbol for p in positions)
        except Exception as e:
            logger.error(f"Failed to check positions for {symbol}: {e}")
            return True # Fail-closed
        try:
            positions = self._api_client.get_open_positions()
            return any(getattr(p, 'symbol', p.get('symbol', '')) == symbol for p in positions)
        except Exception as e:
            logger.error(f"Failed to check positions for {symbol}: {e}")
            return True # Fail-closed

    def get_open_positions_count(self) -> int:
        """Get current open positions count from Binance."""
        if not self._api_client:
            return 0
        try:
            positions = self._api_client.get_open_positions()
            return len(positions)
        except Exception as e:
            logger.error(f"Failed to fetch open positions: {e}")
            return 999  # Fail-closed: return a high number to prevent new trades

    def execute_trade(self, symbol: str, entry_price: float) -> bool:
        """Execute the trade on Binance."""
        if not self.settings.paper_trading:
            logger.error("Live execution blocked by safety rules.")
            return False
            
        size_usd = self.settings.max_position_usd
        stop_loss = entry_price * (1 + self.settings.stop_loss_pct)  # Short: SL is higher
        take_profit = entry_price * (1 - self.settings.take_profit_pct)
        
        # Basic quantity calculation (Note: does not handle Binance stepSize/precision rules yet)
        quantity = round(size_usd / entry_price, 3)
        
        logger.warning(
            f"[PAPER TRADING] Executing SHORT on {symbol} | "
            f"Entry: {entry_price} | SL: {stop_loss:.4f} | TP: {take_profit:.4f} | Size: ${size_usd} | Qty: {quantity}"
        )
        
        if self._api_client:
            try:
                res = self._api_client.place_market_order(symbol, "SELL", quantity)
                logger.info(f"Order placed successfully: {res.get('orderId')}")
                return True
            except Exception as e:
                logger.error(f"Failed to place order for {symbol}: {e}")
                return False
