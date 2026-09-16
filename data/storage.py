"""数据存储: SQLite 实时落库 + CSV 导出。

frames: 原始报文 (timestamp, id, name, data_hex)
samples: 解码后的合并通道值 (timestamp, channel, value, unit)
"""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path


class DataStorage:
    def __init__(self, db_path: str | Path = "data/dvtest.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS frames ("
            "timestamp REAL, frame_id INTEGER, msg_name TEXT, data_hex TEXT)")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS samples ("
            "timestamp REAL, channel TEXT, value REAL, unit TEXT)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_samples_ts ON samples(timestamp)")
        self.conn.commit()
        self._batch_frames: list[tuple] = []
        self._batch_samples: list[tuple] = []

    def add_frame(self, timestamp: float, frame_id: int, msg_name: str, data: bytes) -> None:
        self._batch_frames.append((timestamp, frame_id, msg_name, data.hex()))
        if len(self._batch_frames) >= 100:
            self.flush()

    def add_sample(self, timestamp: float, channel: str, value: float, unit: str) -> None:
        self._batch_samples.append((timestamp, channel, round(value, 4), unit))
        if len(self._batch_samples) >= 500:
            self.flush()

    def flush(self) -> None:
        if self._batch_frames:
            self.conn.executemany(
                "INSERT INTO frames (timestamp, frame_id, msg_name, data_hex) VALUES (?,?,?,?)",
                self._batch_frames)
            self._batch_frames.clear()
        if self._batch_samples:
            self.conn.executemany(
                "INSERT INTO samples (timestamp, channel, value, unit) VALUES (?,?,?,?)",
                self._batch_samples)
            self._batch_samples.clear()
        self.conn.commit()

    def export_csv(self, base_path: str | Path) -> bool:
        self.flush()
        base = str(base_path)
        if base.lower().endswith(".csv"):
            base = base[:-4]
        ok = self._export("samples", f"{base}_signals.csv",
                          ["timestamp", "channel", "value", "unit"])
        ok &= self._export("frames", f"{base}_frames.csv",
                           ["timestamp", "frame_id", "msg_name", "data_hex"])
        return ok

    def _export(self, table: str, path: str, cols: list[str]) -> bool:
        try:
            rows = self.conn.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(cols)
                w.writerows(rows)
            return True
        except OSError:
            return False

    def trim_before(self, cutoff: float) -> None:
        self.flush()
        self.conn.execute("DELETE FROM frames WHERE timestamp < ?", (cutoff,))
        self.conn.execute("DELETE FROM samples WHERE timestamp < ?", (cutoff,))
        self.conn.commit()

    def clear_all(self) -> None:
        self.flush()
        self.conn.execute("DELETE FROM frames")
        self.conn.execute("DELETE FROM samples")
        self.conn.commit()

    def close(self) -> None:
        self.flush()
        self.conn.close()
