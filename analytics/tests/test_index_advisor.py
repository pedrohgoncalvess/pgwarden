from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from analytics.services.index_advisor import IndexShape, coverage, index_shape, predicate_roles
from analytics.services.query_analysis import _missing_index_findings
from analytics.services.recommendations import _find_missing_indexes
from analytics.services.index_workload import table_evidence


def test_composite_index_covers_both_equality_filters():
    equality, ranges, understood = predicate_roles(
        'SELECT * FROM orders WHERE customer_id = $1 AND status = $2', {'customer_id', 'status'})
    shape = index_shape('orders_idx', 'CREATE INDEX orders_idx ON public.orders USING btree (customer_id, status)')
    assert understood
    assert coverage([shape], equality, ranges, understood) == ('covered', ['orders_idx'])


def test_range_stops_search_prefix():
    shape = IndexShape('idx', ('created_at', 'customer_id'), True)
    assert coverage([shape], {'customer_id'}, {'created_at'}, True)[0] == 'partial'
    shape = IndexShape('idx', ('customer_id', 'created_at'), True)
    assert coverage([shape], {'customer_id'}, {'created_at'}, True)[0] == 'covered'


def test_include_is_not_a_search_key():
    shape = index_shape('idx', 'CREATE INDEX idx ON public.orders USING btree (customer_id) INCLUDE (status)')
    assert shape.keys == ('customer_id',)
    assert shape.certain
    assert coverage([shape], {'customer_id', 'status'}, set(), True)[0] == 'partial'


@pytest.mark.parametrize('definition,kind', [
    ('CREATE INDEX idx ON public.orders USING btree (status) WHERE active', 'btree'),
    ('CREATE INDEX idx ON public.orders USING btree (lower(email))', 'btree'),
    ('CREATE INDEX idx ON public.orders USING btree (email text_pattern_ops)', 'btree'),
    ('CREATE INDEX idx ON public.orders USING gin (payload)', 'gin'),
])
def test_specialized_indexes_require_review(definition, kind):
    shape = index_shape('idx', definition, kind)
    assert not shape.certain
    assert coverage([shape], {'status'}, set(), True)[0] == 'uncertain'


@pytest.mark.parametrize('sql', [
    'SELECT * FROM orders WHERE customer_id = 1 OR status = 2',
    'SELECT * FROM orders WHERE lower(status) = $1',
    'SELECT * FROM orders WHERE status IN (1, 2)',
    'SELECT * FROM orders o JOIN customers c ON o.customer_id = c.id WHERE status = 1',
    'SELECT * FROM orders, customers WHERE status = 1',
    'SELECT * FROM orders WHERE customer_id = (SELECT id FROM customers LIMIT 1)',
])
def test_unsupported_predicates_never_produce_certain_coverage(sql):
    assert predicate_roles(sql, {'customer_id', 'status'})[2] is False


def test_quoted_identifiers_and_predicate_order():
    equality, ranges, understood = predicate_roles(
        'SELECT * FROM "Orders" WHERE "Status" = $1 AND "Created" >= $2', {'Status', 'Created'})
    assert (equality, ranges, understood) == ({'Status'}, {'Created'}, True)
    shape = index_shape('idx', 'CREATE INDEX idx ON public."Orders" USING btree ("Status", "Created")')
    assert coverage([shape], equality, ranges, understood)[0] == 'covered'


def finding_context(sql, shapes):
    insight = SimpleNamespace(
        table=SimpleNamespace(id=1, schema_name='public', name='orders'), metric=None,
        condition_columns=[SimpleNamespace(id=1, name='customer_id'), SimpleNamespace(id=2, name='status')],
        index_columns={}, index_names={}, index_shapes=shapes, column_metrics={})
    return SimpleNamespace(query=SimpleNamespace(query=sql), tables=[insight])


def test_existing_composite_suppresses_missing_index_finding():
    context = finding_context('SELECT * FROM orders WHERE customer_id = $1 AND status = $2',
                              [IndexShape('idx', ('customer_id', 'status'), True)])
    assert _missing_index_findings(context) == []


def test_partial_coverage_keeps_whole_predicate_without_ddl():
    context = finding_context('SELECT * FROM orders WHERE customer_id = $1 AND status = $2',
                              [IndexShape('idx', ('customer_id',), True)])
    finding = _missing_index_findings(context)[0]
    assert finding.evidence['coverage'] == 'partial'
    assert finding.evidence['missing_prefix_columns'] == ['customer_id', 'status']
    assert finding.evidence['suggested_ddl'] is None


def test_candidate_places_equality_before_range_and_quotes_identifiers():
    context = finding_context('SELECT * FROM orders WHERE customer_id > $1 AND status = $2', [])
    assert _missing_index_findings(context)[0].evidence['suggested_ddl'] == (
        'CREATE INDEX CONCURRENTLY ON "public"."orders" ("status", "customer_id");')


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self.rows


def result_row(query_id=1, literal=1, native_id=100):
    return SimpleNamespace(query_id=query_id, query=f'SELECT * FROM orders WHERE customer_id = {literal}',
                           table_id=1, schema_name='public', table_name='orders', native_query_id=native_id,
                           evidence={'advisor_version': 2, 'missing_prefix_columns': ['customer_id']})


async def recommend(monkeypatch, rows, workload=None, indexes=None, write_heavy=False):
    async def query_evidence(*args):
        return workload or {}
    monkeypatch.setattr('analytics.services.recommendations.query_evidence', query_evidence)
    session = SimpleNamespace(execute=AsyncMock(side_effect=[Rows(indexes or []), Rows(rows)]))
    costs = {1: {'write_heavy': write_heavy, 'writes_per_second': 20 if write_heavy else 1}}
    return await _find_missing_indexes(session, 1, costs)


@pytest.mark.asyncio
async def test_literal_variants_count_as_one_pattern(monkeypatch):
    drafts = await recommend(monkeypatch, [result_row(i, i) for i in range(10)])
    assert len(drafts) == 1
    assert drafts[0].evidence['query_count'] == 1
    assert drafts[0].severity == 'info'
    assert drafts[0].confidence <= 0.45
    assert drafts[0].evidence['calls'] is None


@pytest.mark.asyncio
async def test_current_index_suppresses_historical_suggestion(monkeypatch):
    index = SimpleNamespace(table_id=1, name='idx', definition='CREATE INDEX idx ON public.orders USING btree (customer_id)',
                            type='btree', is_valid=True)
    assert await recommend(monkeypatch, [result_row()], indexes=[index]) == []


@pytest.mark.asyncio
async def test_invalid_index_never_establishes_coverage(monkeypatch):
    index = SimpleNamespace(table_id=1, name='idx', definition='CREATE INDEX idx ON public.orders USING btree (customer_id)',
                            type='btree', is_valid=False)
    drafts = await recommend(monkeypatch, [result_row()], indexes=[index])
    assert drafts[0].evidence['coverage'] == 'uncertain'
    assert drafts[0].evidence['suggested_ddl'] is None


@pytest.mark.asyncio
@pytest.mark.parametrize('heavy,severity', [(True, 'info'), (False, 'warning')])
async def test_priority_requires_measured_impact_and_write_evidence(monkeypatch, heavy, severity):
    now = datetime.now(timezone.utc)
    workload = {100: {'calls': 200, 'total_exec_time_ms': 120000, 'shared_blks_read': 50,
                      'shared_blks_hit': 1000, 'first_seen_at': now - timedelta(hours=2), 'last_seen_at': now}}
    drafts = await recommend(monkeypatch, [result_row()], workload, write_heavy=heavy)
    assert drafts[0].severity == severity
    assert drafts[0].evidence['benefit_estimate'] is None
    assert drafts[0].evidence['requires_plan_validation']


@pytest.mark.asyncio
async def test_legacy_findings_only_request_investigation(monkeypatch):
    row = result_row()
    row.evidence.pop('advisor_version')
    draft = (await recommend(monkeypatch, [row]))[0]
    assert draft.evidence['coverage'] == 'uncertain'
    assert draft.evidence['suggested_ddl'] is None


@pytest.mark.asyncio
async def test_unmapped_pattern_keeps_priority_low(monkeypatch):
    now = datetime.now(timezone.utc)
    workload = {100: {'calls': 200, 'total_exec_time_ms': 120000, 'shared_blks_read': 50,
                      'shared_blks_hit': 1000, 'first_seen_at': now - timedelta(hours=2), 'last_seen_at': now}}
    drafts = await recommend(monkeypatch, [result_row(), result_row(2, native_id=None)], workload)
    assert drafts[0].severity == 'info'
    assert not drafts[0].evidence['workload_evidence_complete']


@pytest.mark.asyncio
async def test_candidates_that_share_a_prefix_are_compared(monkeypatch):
    first = result_row()
    second = result_row(2)
    second.query = 'SELECT * FROM orders WHERE customer_id = 1 AND status = 2'
    second.evidence['missing_prefix_columns'] = ['customer_id', 'status']
    drafts = await recommend(monkeypatch, [first, second])
    small = next(d for d in drafts if d.evidence['missing_columns'] == ['customer_id'])
    large = next(d for d in drafts if len(d.evidence['missing_columns']) == 2)
    assert small.evidence['alternative_candidate_fingerprints'] == [large.fingerprint]
    assert small.evidence['action'] == 'compare_shared_candidates'


@pytest.mark.asyncio
@pytest.mark.parametrize('seconds,rate', [(1800, None), (7200, 20)])
async def test_write_pressure_uses_counter_deltas_and_observation_duration(seconds, rate):
    row = SimpleNamespace(table_id=1, seconds=seconds, writes=seconds * 20,
                          updates=100, hot_updates=80, index_count=4, index_size_bytes=1234)
    session = SimpleNamespace(execute=AsyncMock(return_value=Rows([row])))
    evidence = (await table_evidence(session, 1))[1]
    assert evidence['writes_per_second'] == rate
    assert evidence['hot_update_fraction'] == 0.8
    assert evidence['index_count'] == 4
