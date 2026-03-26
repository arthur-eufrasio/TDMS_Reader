from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from core.models import SignalRecord


@dataclass
class AppState:
    source_path: Optional[str] = None
    channels_by_group: Dict[str, List[str]] = field(default_factory=dict)

    current_group: Optional[str] = None
    current_channel: Optional[str] = None

    records: Dict[str, SignalRecord] = field(default_factory=dict)
    selected_files: List[str] = field(default_factory=list)
    active_file: Optional[str] = None

    selected_spans: Dict[str, Tuple[float, float]] = field(default_factory=dict)

    def get_active_record(self) -> Optional[SignalRecord]:
        if self.active_file is None:
            return None
        return self.records.get(self.active_file)

    def get_selected_records(self) -> List[SignalRecord]:
        return [self.records[f] for f in self.selected_files if f in self.records]
