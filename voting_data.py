from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    id: int
    name: str
    party: str
    symbol: str


APP_TITLE = "Blockchain Voting Demo"
FACE_SCAN_SECONDS = 45
DB_PATH = "voting_demo.sqlite3"

HARD_CODED_CANDIDATES: list[Candidate] = [
    Candidate(1, "Asha Patel", "Unity Party", "🌿"),
    Candidate(2, "Rohan Mehta", "Civic Front", "⚙️"),
    Candidate(3, "Neel Sharma", "Progress Alliance", "⭐"),
]
