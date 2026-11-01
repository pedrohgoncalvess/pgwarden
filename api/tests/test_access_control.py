"""Exercise authorization against a disposable local PostgreSQL database."""
import json
import os
import re
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from test_ingestion import (
    _apply_migrations as ingestion_migrations,
    db_session,
    _stub_embeddings,
)
from app.access.services import load_access
from app.auth.services import create_access_token, pwd_context
from app.routes import register_routes

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='session', autouse=True)
def _apply_migrations(tmp_path_factory):
    baseline = ingestion_migrations.__wrapped__(tmp_path_factory)
    url = next(baseline)
    with psycopg.connect(url, autocommit=True) as connection:
        for name in ['20260408_01_vVWWG-api-migrations.sql',
                     '20260720_01_notifier-module.sql', '20261031_01_access-control.sql']:
            connection.execute((ROOT / 'migrations/sql' / name).read_text())
        # The local PostgreSQL has no pgvector extension; these checks do not use embeddings.
        docs = (ROOT / 'migrations/sql/20260425_02_docs-tags-history.sql').read_text()
        docs = docs.replace('CREATE EXTENSION IF NOT EXISTS vector;', '')
        docs = docs.replace('vector(1024)', 'double precision[]')
        docs = re.sub(r'CREATE INDEX[^;]+USING hnsw[^;]+;', '', docs, flags=re.IGNORECASE)
        connection.execute(docs)
    yield url
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute((ROOT / 'migrations/sql/20261031_01_access-control.rollback.sql').read_text())
    try:
        next(baseline)
    except StopIteration:
        pass


@pytest_asyncio.fixture
async def client(db_session):
    app = FastAPI()
    register_routes(app)
    async with AsyncClient(transport=ASGITransport(app), base_url='http://test') as client:
        yield client


@pytest_asyncio.fixture
async def fleet(db_session):
    projects, servers, databases = [], [], []
    for index in range(2):
        project = uuid4()
        await db_session.execute(text('INSERT INTO ingestion.project(id,name) VALUES (:id,:name)'), {'id': project, 'name': f'Project {index}'})
        server = (await db_session.execute(text('''INSERT INTO collector.server
            (name,host,port,username,password,ingestion_project_id)
            VALUES (:name,'localhost','5432','test','test',:project) RETURNING id,public_id'''),
            {'name': f'Server {index}', 'project': project})).mappings().one()
        database = (await db_session.execute(text('''INSERT INTO metadata.database(server_id,db_name)
            VALUES (:server,:name) RETURNING id,public_id'''), {'server': server['id'], 'name': f'db_{index}'})).mappings().one()
        projects.append(str(project)); servers.append(dict(server)); databases.append(dict(database))
    await db_session.execute(text('''INSERT INTO base."user"(name,email,password,is_admin)
        VALUES ('Admin','admin@example.com',:password,TRUE)'''), {'password': pwd_context.hash('test-password-123')})
    await db_session.commit()
    return projects, servers, databases


def headers(email='admin@example.com'):
    return {'Authorization': 'Bearer ' + create_access_token({'sub': email}, timedelta(minutes=10))}


async def provision(client, fleet, permissions=None):
    projects, servers, databases = fleet
    body = {'name': uuid4().hex, 'permissions': permissions or [], 'project_ids': projects[:1],
            'server_ids': [str(servers[0]['public_id'])], 'database_ids': [str(databases[0]['public_id'])]}
    response = await client.post('/v1/access/roles', headers=headers(), json=body)
    assert response.status_code == 201, response.text
    role = response.json()
    response = await client.post('/v1/access/users', headers=headers(), json={
        'name': 'Reader', 'email': 'reader@example.com', 'password': 'reader-password-123', 'role_id': role['id']})
    assert response.status_code == 201, response.text
    assert 'password' not in response.json()
    return role, response.json()


async def test_user_role_creation_and_admin_only_management(client, fleet):
    role, user = await provision(client, fleet)
    assert (await client.post('/v1/auth', json={'email': user['email'], 'password': 'reader-password-123'})).status_code == 200
    for path in ['/v1/access/users', '/v1/access/roles']:
        assert (await client.get(path, headers=headers(user['email']))).status_code == 403
        assert (await client.post(path, headers=headers(user['email']), json={})).status_code == 403
    assert (await client.delete(f"/v1/access/roles/{role['id']}", headers=headers())).status_code == 409
    assert (await client.post('/v1/access/users', headers=headers(), json={
        'name': 'No role', 'email': 'none@example.com', 'password': 'test-password-123'})).status_code == 422
    admin = (await client.get('/v1/auth/me', headers=headers())).json()
    assert (await client.delete(f"/v1/access/users/{admin['id']}", headers=headers())).status_code == 409


async def test_catalogs_and_direct_access_follow_ancestors(client, db_session, fleet):
    role, _ = await provision(client, fleet, ['schedulers.read', 'alerts.read', 'documentation.read'])
    auth = headers('reader@example.com')
    projects, servers, databases = fleet
    response = await client.get('/v1/servers/', headers=auth)
    assert [s['id'] for s in response.json()] == [str(servers[0]['public_id'])]
    assert response.json()[0]['databases'] == [{'id': str(databases[0]['public_id'])}]
    assert len((await client.get('/v1/databases/', headers=auth)).json()) == 1
    assert len((await client.get('/v1/catalog/projects', headers=auth)).json()) == 1
    for path in [f"/v1/servers/{servers[1]['public_id']}/configs", f"/v1/databases/{databases[1]['public_id']}/docs"]:
        assert (await client.get(path, headers=auth)).status_code == 404
    assert (await client.get(f'/v1/projects/{projects[0]}/keys', headers=auth)).status_code == 403
    # Even stale child grants must stop working immediately when the parent grant disappears.
    await db_session.execute(text("UPDATE base.role SET project_ids = '{}' WHERE id = :id"), {'id': role['id']})
    await db_session.commit()
    assert (await client.get('/v1/servers/', headers=auth)).json() == []
    assert (await client.get('/v1/databases/', headers=auth)).json() == []
    assert len((await client.get('/v1/servers/', headers=headers())).json()) == 2


@pytest.mark.parametrize('feature,read_path,write_path,payload', [
    ('alerts', '/v1/notifier/rule-types', '/v1/notifier/rules', {'name': 'Test alert'}),
    ('documentation', '/v1/databases/{db}/docs', '/v1/databases/{db}/docs', {'description': 'Runbook'}),
    ('schedulers', '/v1/databases/{db}/configs', '/v1/databases/{db}/runs/999999', {'action': 'pause'}),
])
async def test_read_and_configure_are_independent(client, db_session, fleet, monkeypatch, feature, read_path, write_path, payload):
    role, _ = await provision(client, fleet, [f'{feature}.read'])
    from app.databases.docs.services import database as docs
    async def no_embedding(*args):
        return None
    monkeypatch.setattr(docs, 'generate_embedding_cached', no_embedding)
    auth = headers('reader@example.com')
    read_path = read_path.format(db=fleet[2][0]['public_id'])
    write_path = write_path.format(db=fleet[2][0]['public_id'])
    assert (await client.get(read_path, headers=auth)).status_code in (200, 404)
    method = 'PUT' if feature == 'documentation' else 'POST' if feature == 'alerts' else 'PATCH'
    assert (await client.request(method, write_path, headers=auth, json=payload)).status_code == 403
    await db_session.execute(text('UPDATE base.role SET permissions = CAST(:perms AS jsonb) WHERE id = :id'), {'id': role['id'], 'perms': json.dumps([f'{feature}.configure'])})
    await db_session.commit()
    assert (await client.get(read_path, headers=auth)).status_code == 403
    assert (await client.request(method, write_path, headers=auth, json=payload)).status_code in (200, 201, 404)


async def test_invalid_hierarchy_and_deleted_user(client, fleet):
    projects, servers, databases = fleet
    for body in [
        {'name': 'Missing project', 'server_ids': [str(servers[0]['public_id'])]},
        {'name': 'Missing server', 'project_ids': projects, 'database_ids': [str(databases[0]['public_id'])]},
    ]:
        assert (await client.post('/v1/access/roles', headers=headers(), json=body)).status_code == 422
    role, user = await provision(client, fleet)
    assert (await client.delete(f"/v1/access/users/{user['id']}", headers=headers())).status_code == 204
    assert (await client.get('/v1/servers/', headers=headers(user['email']))).status_code == 401
    assert (await client.post('/v1/auth', json={'email': user['email'], 'password': 'reader-password-123'})).status_code == 401
    assert (await client.delete(f"/v1/access/roles/{role['id']}", headers=headers())).status_code == 204


async def test_notifications_and_thresholds_do_not_expose_hidden_resources(client, db_session, fleet):
    await provision(client, fleet, ['alerts.read', 'alerts.configure'])
    rule = (await client.post('/v1/notifier/rules', headers=headers(), json={'name': 'Scoped'})).json()
    for db in fleet[2]:
        await db_session.execute(text('INSERT INTO notifier.notification(message,params) VALUES (:message,CAST(:params AS jsonb))'),
            {'message': f"database {db['id']}", 'params': json.dumps({'database_id': db['id']})})
        response = await client.post(f"/v1/notifier/rules/{rule['id']}/thresholds", headers=headers(), json={
            'scope': 'database', 'type': 'growth_percent', 'entity_public_id': str(db['public_id']), 'warning': 10, 'critical': 20})
        assert response.status_code == 201, response.text
    await db_session.commit()
    auth = headers('reader@example.com')
    notifications = (await client.get('/v1/notifications/', headers=auth)).json()
    assert notifications['total'] == notifications['visible_count'] == 1
    rules = (await client.get('/v1/notifier/rules', headers=auth)).json()
    assert len(rules[0]['thresholds']) == 1
    assert rules[0]['thresholds'][0]['entity_public_id'] == str(fleet[2][0]['public_id'])


async def test_search_tags_and_column_ids_respect_database_grants(client, db_session, fleet):
    await provision(client, fleet, ['documentation.read', 'documentation.configure'])
    columns = []
    for index, database in enumerate(fleet[2]):
        table = (await db_session.execute(text('''INSERT INTO metadata."table"(database_id,oid,schema_name,name)
            VALUES (:db,:oid,'public',:name) RETURNING id,public_id'''),
            {'db': database['id'], 'oid': 100 + index, 'name': f'customer_{index}'})).mappings().one()
        column = (await db_session.execute(text('''INSERT INTO metadata."column"(table_id,name,data_type,is_nullable,is_unique,ordinal_position)
            VALUES (:table,'email','text',TRUE,FALSE,1) RETURNING public_id'''), {'table': table['id']})).scalar_one()
        columns.append(column)
        await db_session.execute(text('INSERT INTO doc.tag(server_id,name) VALUES (:server,:name)'),
            {'server': fleet[1][index]['id'], 'name': f'Team {index}'})
    await db_session.commit()
    auth = headers('reader@example.com')
    response = await client.get('/v1/search', headers=auth, params={'q': 'customer', 'semantic': 'false', 'limit': 100})
    assert response.status_code == 200, response.text
    results = response.json()['results']
    assert any(row['name'] == 'customer_0' for row in results)
    assert not any(row.get('database_id') == str(fleet[2][1]['public_id']) for row in results)
    tags = (await client.get('/v1/tags', headers=auth)).json()
    assert [t['name'] for t in tags] == ['Team 0']
    own_column = f"/v1/databases/{fleet[2][0]['public_id']}/docs/columns/{columns[0]}"
    hidden_column = f"/v1/databases/{fleet[2][0]['public_id']}/docs/columns/{columns[1]}"
    assert (await client.get(own_column, headers=auth)).status_code == 404
    assert (await client.put(hidden_column, headers=auth, json={'description': 'no'})).status_code == 404


async def test_scheduler_ids_cannot_target_other_resources(client, db_session, fleet):
    await provision(client, fleet, ['schedulers.read', 'schedulers.configure'])
    configs = []
    for database in fleet[2]:
        configs.append((await db_session.execute(text('''INSERT INTO collector.config_database(database_id,name,interval)
            VALUES (:id,'table',60) RETURNING id'''), {'id': database['id']})).scalar_one())
    await db_session.commit()
    auth = headers('reader@example.com')
    database = fleet[2][0]['public_id']
    response = await client.patch(f'/v1/databases/{database}/configs/{configs[0]}', headers=auth, json={'interval': 120})
    assert response.status_code == 200, response.text
    response = await client.patch(f'/v1/databases/{database}/runs/{configs[1]}', headers=auth, json={'action': 'pause'})
    assert response.status_code == 404, response.text
    assert (await db_session.execute(text('SELECT interval FROM collector.config_database WHERE id=:id'), {'id': configs[1]})).scalar_one() == 60


async def test_open_stream_stops_after_parent_access_is_revoked(client, db_session, fleet):
    role, user = await provision(client, fleet, ['schedulers.read'])
    from app.access.policy import current_access
    from app.access.streams import protect_stream
    from database.models.base.user import User
    account = await db_session.get(User, user['id'])
    access = await load_access(account, db_session)
    token = current_access.set(access)

    async def source():
        yield {'event': 'runs', 'data': 'first'}
        yield {'event': 'runs', 'data': 'must not be disclosed'}

    stream = protect_stream(source(), 'database', fleet[2][0]['public_id'], 'schedulers.read')
    try:
        assert (await anext(stream))['data'] == 'first'
        await db_session.execute(text("UPDATE base.role SET project_ids = '{}' WHERE id = :id"), {'id': role['id']})
        await db_session.commit()
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
    finally:
        await stream.aclose()
        current_access.reset(token)


async def test_metric_stream_releases_connection_before_authorization(db_session, fleet, monkeypatch):
    from app.databases.sessions.services import session_stream
    from database.connection import DatabaseConnection
    await db_session.execute(text('''INSERT INTO metric.session
        (database_id,collected_at,pid,backend_start) VALUES (:db,now(),1,now())'''),
        {'db': fleet[2][0]['id']})
    await db_session.commit()
    original_enter = DatabaseConnection.__aenter__
    original_exit = DatabaseConnection.__aexit__
    active_connections = 0

    async def enter(connection):
        nonlocal active_connections
        active_connections += 1
        return await original_enter(connection)

    async def exit(connection, *args):
        nonlocal active_connections
        active_connections -= 1
        return await original_exit(connection, *args)

    monkeypatch.setattr(DatabaseConnection, '__aenter__', enter)
    monkeypatch.setattr(DatabaseConnection, '__aexit__', exit)
    stream = session_stream(fleet[2][0]['public_id'])
    try:
        event = await anext(stream)
        assert event['event'] == 'sessions'
        assert active_connections == 0
    finally:
        await stream.aclose()
