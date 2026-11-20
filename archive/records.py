from dataclasses import asdict, dataclass
from sqlite3 import Connection

from analysis.drafts import ReportDraft
from archive.codec import decode_report_payload, encode_report_payload


@dataclass(frozen=True)
class ReportRecord:
    report_id: str
    request_id: str
    draft: ReportDraft


def initialize_records(db: Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            report_id TEXT PRIMARY KEY NOT NULL,
            request_id TEXT UNIQUE NOT NULL,
            payload TEXT NOT NULL
        )
    ''')


def insert_report(db: Connection, record: ReportRecord) -> None:
    payload = encode_report_payload(asdict(record.draft))
    db.execute('INSERT INTO reports VALUES (?, ?, ?)', (record.report_id, record.request_id, payload))


def load_report(db: Connection, report_id: str) -> ReportRecord | None:
    row = db.execute('SELECT request_id, payload FROM reports WHERE report_id = ?',
                     (report_id,)).fetchone()
    if row is None:
        return None
    request_id, payload = row
    return ReportRecord(report_id, request_id, ReportDraft(**decode_report_payload(payload)))
