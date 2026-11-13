"""Insert structured snapshots with real deduplicated text references."""

import hashlib

from sqlalchemy import select

from database.models.metric.query_workload import QueryWorkloadMetric as Workload, StatementText


def insert_samples(session, samples):
    for sample in samples:
        row = dict(sample)
        query = row.pop("query", None)
        supplied_hash = row.pop("query_hash", None)
        if query is not None:
            fingerprint = hashlib.sha256(query.encode()).hexdigest()
            identity = session.execute(select(StatementText.id).where(
                StatementText.database_id == row["database_id"],
                StatementText.fingerprint == fingerprint,
            )).scalar_one_or_none()
            if identity is None:
                identity = session.execute(StatementText.__table__.insert().values(
                    database_id=row["database_id"], fingerprint=fingerprint, query=query,
                    query_hash=supplied_hash or hashlib.md5(query.encode()).hexdigest(),
                ).returning(StatementText.id)).scalar_one()
            row["statement_text_id"] = identity
        session.execute(Workload.__table__.insert().values(**row))
