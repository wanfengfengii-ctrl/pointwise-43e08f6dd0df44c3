import json
from dataclasses import dataclass
from sqlite3 import Connection

from analysis.drafts import ReportDraft
from desk.budget import family_balance
from desk.commitments import get_commitment, reserve_commitment
from desk.intake import PublicationClaim, check_draft
from registry.families import require_id


NONE = 'none'
RESERVED = 'reserved'
PUBLISHED = 'published'
FOREIGN = 'foreign'


def member_request_id(group_id: str, test_id: str) -> str:
    """A desk identity for one group member, disjoint from single request IDs."""
    # The NUL lead keeps this internal identity outside any user-supplied request ID.
    return '\x00group:' + _escape(group_id, test_id)


def group_report_id(group_id: str, test_id: str) -> str:
    """A public report number that can never equal a single `R-` report number."""
    return 'G-' + _escape(group_id, test_id)


def _escape(group_id: str, test_id: str) -> str:
    # The length prefix makes ``a:b`` and ``a/b`` style group names unambiguous.
    return f'{len(group_id)}:{group_id}:{test_id}'


@dataclass(frozen=True)
class GroupMember:
    test_id: str
    claim: PublicationClaim

    @property
    def request_id(self) -> str:
        return self.claim.request_id


@dataclass(frozen=True)
class GroupClaim:
    group_id: str
    members: tuple[GroupMember, ...]

    @property
    def family_id(self) -> str:
        return self.members[0].claim.draft.family_id

    @property
    def limit_bps(self) -> int:
        return self.members[0].claim.limit_bps

    @property
    def total_bps(self) -> int:
        return sum(member.claim.draft.alpha_bps for member in self.members)


@dataclass(frozen=True)
class GroupResult:
    group_id: str
    status: str
    report_ids: tuple[str, ...] = ()


def initialize_grouping(db: Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS group_publications (
            group_id TEXT PRIMARY KEY NOT NULL,
            family_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('reserved', 'published')),
            report_ids TEXT NOT NULL DEFAULT '[]'
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS group_members (
            test_id TEXT PRIMARY KEY NOT NULL,
            group_id TEXT NOT NULL REFERENCES group_publications(group_id)
        )
    ''')
    db.execute('CREATE INDEX IF NOT EXISTS group_members_group ON group_members(group_id)')


def resolve_group_claim(preparation: Connection, group_id: str,
                        drafts: tuple[ReportDraft, ...]) -> GroupClaim:
    require_id(group_id, 'group ID')
    if not drafts:
        raise ValueError('a group needs at least one member')
    members = []
    family_id = None
    for draft in drafts:
        limit = check_draft(preparation, draft)
        if family_id is None:
            family_id = draft.family_id
        elif draft.family_id != family_id:
            raise ValueError('group members must share one test family')
        members.append(GroupMember(draft.test_id, PublicationClaim(
            member_request_id(group_id, draft.test_id), draft, limit)))
    return GroupClaim(group_id, tuple(members))


def find_group_publication(db: Connection, group_id: str):
    return db.execute('''
        SELECT family_id, status, report_ids FROM group_publications WHERE group_id = ?
    ''', (group_id,)).fetchone()


def lookup_group_result(db: Connection, group_id: str) -> GroupResult | None:
    row = find_group_publication(db, group_id)
    if row is None:
        return None
    _, status, report_ids = row
    if status == 'published':
        return GroupResult(group_id, 'published', tuple(json.loads(report_ids)))
    return GroupResult(group_id, 'pending')


def member_owner(db: Connection, test_id: str) -> str | None:
    row = db.execute('SELECT group_id FROM group_members WHERE test_id = ?',
                     (test_id,)).fetchone()
    return row[0] if row is not None else None


def member_state(db: Connection, group_id: str, member: GroupMember) -> str:
    """What the desk already holds for one member test, as seen by this group."""
    owner = member_owner(db, member.test_id)
    if owner is not None and owner != group_id:
        return FOREIGN
    row = db.execute('SELECT request_id, status FROM publication_commitments WHERE test_id = ?',
                     (member.test_id,)).fetchone()
    if row is None:
        return NONE
    request_id, status = row
    if request_id != member.claim.request_id:
        return FOREIGN
    if status == 'published':
        return PUBLISHED
    if status == 'reserved':
        return RESERVED
    return FOREIGN


def saved_members(db: Connection, group_id: str) -> set[str]:
    return {row[0] for row in db.execute(
        'SELECT test_id FROM group_members WHERE group_id = ?', (group_id,)).fetchall()}


def check_roster(db: Connection, claim: GroupClaim) -> None:
    if find_group_publication(db, claim.group_id) is not None and \
            saved_members(db, claim.group_id) != {m.test_id for m in claim.members}:
        raise ValueError('group reservation does not match its frozen members')


def check_group(db: Connection, claim: GroupClaim) -> GroupResult | None:
    """Occupancy first, then the whole-group charge; returns a refusal or None."""
    states = {member.test_id: member_state(db, claim.group_id, member)
              for member in claim.members}
    if any(state == FOREIGN for state in states.values()):
        return GroupResult(claim.group_id, 'conflict')
    held = sum(member.claim.draft.alpha_bps for member in claim.members
               if states[member.test_id] == RESERVED)
    balance = family_balance(db, claim.family_id, claim.limit_bps)
    if claim.total_bps - held > balance.available_bps:
        return GroupResult(claim.group_id, 'insufficient')
    return None


def _insert_group(db: Connection, claim: GroupClaim) -> None:
    db.execute('INSERT INTO group_publications VALUES (?, ?, ?, ?)',
               (claim.group_id, claim.family_id, 'reserved', '[]'))
    db.executemany('INSERT INTO group_members VALUES (?, ?)',
                   ((member.test_id, claim.group_id) for member in claim.members))


def reserve_members(db: Connection, claim: GroupClaim) -> None:
    """Insert the group roster and reserve every member that is not reserved yet."""
    if find_group_publication(db, claim.group_id) is None:
        _insert_group(db, claim)
    else:
        check_roster(db, claim)
    for member in claim.members:
        if member_state(db, claim.group_id, member) == NONE:
            reserve_commitment(db, member.claim.identity())


def require_reserved(db: Connection, claim: GroupClaim) -> None:
    check_roster(db, claim)
    for member in claim.members:
        if member_state(db, claim.group_id, member) != RESERVED:
            raise ValueError('group publication requires every member to be reserved')
