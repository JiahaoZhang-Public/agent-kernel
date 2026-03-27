"""Append-only JSONL log for the Agent OS Kernel.

Per v2 design §5: every Gate decision produces exactly one log record.
The log is append-only, kernel-exclusive write, readable by external tools.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import IO

from agent_os_kernel.models import Record


class Log:
    """Append-only JSONL log writer.

    Writes one JSON object per line. Never modifies or deletes records.
    """

    def __init__(self, log_path: str | Path) -> None:
        self._path = Path(log_path)
        self._file: IO[str] | None = None

    def open(self) -> None:
        """Open the log file for appending."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self._path.open("a")

    def close(self) -> None:
        """Close the log file."""
        if self._file is not None:
            self._file.close()
            self._file = None

    def write(self, record: Record) -> None:
        """Append a single record to the log.

        Args:
            record: The Record to write.

        Raises:
            RuntimeError: If the log is not open.
        """
        if self._file is None:
            raise RuntimeError("Log is not open. Call open() first.")
        data = asdict(record)
        # Remove None values for compact output
        data = {k: v for k, v in data.items() if v is not None}
        self._file.write(json.dumps(data) + "\n")
        self._file.flush()

    def read_all(self) -> list[Record]:
        """Read all records from the log file.

        Returns:
            List of Record instances.
        """
        if not self._path.exists():
            return []
        records: list[Record] = []
        with self._path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    records.append(
                        Record(
                            timestamp=data["timestamp"],
                            action=data["action"],
                            target=data["target"],
                            status=data["status"],
                            error=data.get("error"),
                            duration_ms=data.get("duration_ms"),
                            record_id=data.get("record_id"),
                        )
                    )
        return records

    def __enter__(self) -> Log:
        self.open()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
