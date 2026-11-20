from dataclasses import dataclass
from sqlite3 import Connection

from desk.intake import PublicationClaim
from desk.settlement import PublicationOutcome, lookup_outcome


@dataclass(frozen=True)
class ApplicationOutcome:
    request_id: str
    test_id: str
    status: str
    report_id: str | None = None

    @property
    def terminal(self) -> bool:
        return self.status in ('published', 'cancelled')


def project_outcome(reply: PublicationOutcome) -> ApplicationOutcome:
    return ApplicationOutcome(reply.request_id, reply.test_id, reply.status, reply.report_id)


def resolve_outcome(db: Connection, claim: PublicationClaim) -> ApplicationOutcome:
    return project_outcome(lookup_outcome(db, claim))
