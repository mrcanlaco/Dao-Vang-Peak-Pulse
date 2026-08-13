"""Single cycle test — verify scanner pipeline works end-to-end."""
from __future__ import annotations

from datetime import timezone
from pathlib import Path

import pandas as pd

from dao_vang.alerts.store import AlertStore
from dao_vang.alerts.telegram import TelegramNotifier
from dao_vang.config.settings import AppSettings
from dao_vang.domain.time import system_now
from dao_vang.data.storage.duckdb import DuckDBQueryLayer
from dao_vang.experiments.forward_test import load_frozen_model, score_frozen


def main() -> None:
    settings = AppSettings()
    print("=== Single cycle test ===")
    print(f"Model: {settings.scanner.frozen_model_id}")

    info = load_frozen_model(
        settings.scanner.frozen_model_id, Path(settings.scanner.artifact_dir)
    )
    print(f"Threshold: {info.threshold}")
    print(f"Features: {len(info.feature_cols)}")

    db = DuckDBQueryLayer(str(settings.scanner.db_path))
    df = db.conn.execute(
        "SELECT * FROM feature_results ORDER BY feature_time DESC LIMIT 12"
    ).df()
    print(f"Features rows: {len(df)}")
    if "symbol" in df.columns:
        syms = df["symbol"].unique().tolist()
        print(f"Symbols in latest: {syms}")

    if df.empty:
        print("No data — need to collect first")
        return

    preds = score_frozen(
        settings.scanner.frozen_model_id,
        df,
        Path(settings.scanner.artifact_dir),
        only_after_cutoff=False,
    )
    print(f"Predictions: {len(preds)}")
    if not preds.empty:
        cols = ["feature_time", "symbol", "probability", "risk_level"]
        avail = [c for c in cols if c in preds.columns]
        print(preds[avail].to_string())

        latest = preds.iloc[-1]
        risk = str(latest["risk_level"])
        prob = float(latest["probability"])
        print(f"\nLatest: risk={risk}, prob={prob:.1%}")

        if risk in settings.scanner.alert_levels:
            print(">>> Sending Telegram alert!")
            notifier = TelegramNotifier(settings.telegram)
            sig_time = pd.Timestamp(latest["feature_time"]).to_pydatetime()
            if sig_time.tzinfo is None:
                sig_time = sig_time.replace(tzinfo=timezone.utc)
            from datetime import timedelta
            inv_time = sig_time + timedelta(hours=24)
            close = float(df.iloc[-1].get("close", 0)) if "close" in df.columns else None

            sent = notifier.send_alert(
                symbol=str(latest["symbol"]),
                risk_level=risk,
                probability=prob,
                threshold=float(latest["threshold"]),
                close_price=close,
                feature_time=str(sig_time),
                invalidation_time=str(inv_time),
                model_id=settings.scanner.frozen_model_id,
            )
            print(f"Telegram sent: {sent}")

            # Save to alert_history
            store = AlertStore(str(settings.scanner.db_path))
            from dao_vang.alerts.store import AlertRecord

            record = AlertRecord(
                signal_time=sig_time,
                symbol=str(latest["symbol"]),
                probability=prob,
                risk_level=risk,
                threshold=float(latest["threshold"]),
                close_price=close,
                model_id=settings.scanner.frozen_model_id,
                invalidation_time=inv_time,
                telegram_sent=sent,
                telegram_sent_at=system_now() if sent else None,
            )
            store.save(record)
            print("Saved to alert_history")
        else:
            print(">>> Below alert threshold, no alert sent")


if __name__ == "__main__":
    main()
