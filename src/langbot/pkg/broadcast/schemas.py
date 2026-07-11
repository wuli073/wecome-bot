from __future__ import annotations

from dataclasses import dataclass


VALID_MERGE_MODES = {
    'first',
    'lines',
    'unique_lines',
    'commas',
    'unique_commas',
}

VALID_MATCH_TYPES = {
    'exact',
    'contains',
    'regex',
}


@dataclass(slots=True)
class BroadcastScope:
    bot_uuid: str
    connector_id: str
