"""Explicitly requeue failed image jobs after fixing a generator problem."""
import json
import sqlite3
from pathlib import Path

config = Path('config.local.json')
if not config.exists():
    config = Path('config.example.json')
database = json.loads(config.read_text())['database']
with sqlite3.connect(database) as db:
    result = db.execute("UPDATE jobs SET status='pending',error=NULL WHERE status='failed'")
    print(f'Requeued {result.rowcount} failed jobs')
