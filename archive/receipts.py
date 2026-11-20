from dataclasses import dataclass
from sqlite3 import Connection


@dataclass(frozen=True)
class PublicationReceipt:
    report_id: str
    request_id: str


def initialize_receipts(db: Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS publication_receipts (
            report_id TEXT PRIMARY KEY NOT NULL REFERENCES reports(report_id),
            request_id TEXT UNIQUE NOT NULL REFERENCES publication_commitments(request_id)
        )
    ''')


def add_receipt(db: Connection, receipt: PublicationReceipt) -> None:
    db.execute('INSERT INTO publication_receipts VALUES (?, ?)', (receipt.report_id, receipt.request_id))


def find_receipt(db: Connection, report_id: str) -> PublicationReceipt | None:
    row = db.execute('SELECT report_id, request_id FROM publication_receipts WHERE report_id = ?',
                     (report_id,)).fetchone()
    return PublicationReceipt(*row) if row is not None else None


def find_application_receipt(db: Connection, request_id: str) -> PublicationReceipt | None:
    row = db.execute('SELECT report_id, request_id FROM publication_receipts WHERE request_id = ?',
                     (request_id,)).fetchone()
    return PublicationReceipt(*row) if row is not None else None
