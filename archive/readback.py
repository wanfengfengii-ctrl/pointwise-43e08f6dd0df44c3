from dataclasses import dataclass
from sqlite3 import Connection

from archive.receipts import PublicationReceipt, find_receipt
from archive.records import ReportRecord, load_report
from batches.readback import SealedBatch, get_sealed_batch
from registry.families import require_id


@dataclass(frozen=True)
class ReportReadback:
    record: ReportRecord
    receipt: PublicationReceipt
    parent: SealedBatch


def read(db: Connection, preparation: Connection, report_id: str) -> ReportReadback:
    require_id(report_id, 'report ID')
    with db:
        db.execute('BEGIN')
        receipt = find_receipt(db, report_id)
        if receipt is None:
            raise KeyError(f'no public report {report_id!r}')
        record = load_report(db, report_id)
        if record is None or record.request_id != receipt.request_id:
            raise RuntimeError('public report and receipt are inconsistent')
    draft = record.draft
    parent = get_sealed_batch(preparation, draft.batch_id, draft.revision)
    return ReportReadback(record, receipt, parent)
