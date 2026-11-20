import json
from dataclasses import asdict, dataclass
from sqlite3 import Connection

from analysis.drafts import ReportDraft, build_draft
from archive.codec import decode_report_payload, encode_report_payload
from registry.families import require_id


@dataclass(frozen=True)
class GroupApplication:
    group_id: str
    drafts: tuple[ReportDraft, ...]

    @property
    def members(self) -> tuple[tuple[str, str, int], ...]:
        return tuple((draft.test_id, draft.batch_id, draft.revision) for draft in self.drafts)


@dataclass(frozen=True)
class GroupOutcome:
    group_id: str
    status: str
    report_ids: tuple[str, ...] = ()


def initialize_groups(db: Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS group_requests (
            group_id TEXT PRIMARY KEY NOT NULL,
            drafts_payload TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending', 'published')),
            report_ids TEXT NOT NULL DEFAULT '[]'
        )
    ''')


def _parse_members(members) -> tuple[tuple[str, str, int], ...]:
    if not isinstance(members, (list, tuple)):
        raise ValueError('group members must be a list or tuple')
    if len(members) < 2:
        raise ValueError('a group needs at least two members')
    parsed = []
    for row in members:
        if not isinstance(row, (list, tuple)) or len(row) != 3:
            raise ValueError('each group member must contain a test ID, batch ID and revision')
        test_id, batch_id, revision = row
        require_id(test_id, 'test ID')
        require_id(batch_id, 'batch ID')
        if type(revision) is not int or revision <= 0:
            raise ValueError('revision must be a positive integer')
        parsed.append((test_id, batch_id, revision))
    if len({member[0] for member in parsed}) != len(parsed):
        raise ValueError('group members must have distinct test IDs')
    return tuple(parsed)


def find_group(db: Connection, group_id: str) -> GroupApplication | None:
    require_id(group_id, 'group ID')
    row = db.execute('SELECT drafts_payload FROM group_requests WHERE group_id = ?',
                     (group_id,)).fetchone()
    if row is None:
        return None
    drafts = tuple(ReportDraft(**decode_report_payload(text))
                   for text in json.loads(row[0]))
    return GroupApplication(group_id, drafts)


def require_group(db: Connection, group_id: str) -> GroupApplication:
    application = find_group(db, group_id)
    if application is None:
        raise KeyError(f'unknown group {group_id!r}')
    return application


def request_group(db: Connection, preparation: Connection, group_id: str,
                  members) -> GroupApplication:
    require_id(group_id, 'group ID')
    parsed = tuple(sorted(_parse_members(members)))
    with db:
        db.execute('BEGIN IMMEDIATE')
        original = find_group(db, group_id)
        if original is not None:
            if tuple(sorted(original.members)) != parsed:
                raise ValueError(f'conflicting members for group {group_id!r}')
            return original

        drafts = []
        family_id = None
        for test_id, batch_id, revision in parsed:
            draft = build_draft(preparation, test_id, batch_id, revision)
            if family_id is None:
                family_id = draft.family_id
            elif draft.family_id != family_id:
                raise ValueError('group members must share one test family')
            drafts.append(draft)

        payload = json.dumps([encode_report_payload(asdict(draft)) for draft in drafts],
                             ensure_ascii=True, separators=(',', ':'))
        db.execute('''
            INSERT INTO group_requests (group_id, drafts_payload, status, report_ids)
            VALUES (?, ?, 'pending', '[]')
        ''', (group_id, payload))
        return GroupApplication(group_id, tuple(drafts))


def record_group_outcome(db: Connection, outcome: GroupOutcome) -> GroupOutcome:
    require_id(outcome.group_id, 'group ID')
    with db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT status, report_ids FROM group_requests WHERE group_id = ?',
                         (outcome.group_id,)).fetchone()
        if row is None:
            raise KeyError(f'unknown group {outcome.group_id!r}')
        status, report_ids = row
        if status == 'published':
            saved = GroupOutcome(outcome.group_id, 'published', tuple(json.loads(report_ids)))
            if outcome.status == 'published' and outcome != saved:
                raise ValueError('conflicting terminal group outcome')
            return saved
        if outcome.status != 'published':
            return outcome
        db.execute('''
            UPDATE group_requests SET status = 'published', report_ids = ? WHERE group_id = ?
        ''', (json.dumps(list(outcome.report_ids)), outcome.group_id))
        return outcome
