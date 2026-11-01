"""Verify generated credentials and authenticated password changes."""
import string

import pytest

from test_access_control import (
    _apply_migrations, _stub_embeddings, db_session, client, fleet, headers,
    provision,
)
from app.auth.passwords import generate_password


def test_generated_password_contains_all_character_groups():
    passwords = {generate_password() for _ in range(100)}
    assert len(passwords) == 100
    for password in passwords:
        assert len(password) == 8
        assert any(character.islower() for character in password)
        assert any(character.isupper() for character in password)
        assert any(character.isdigit() for character in password)
        assert any(character in string.punctuation for character in password)


async def test_new_user_receives_a_generated_password_once(client, fleet):
    response = await client.post('/v1/access/users', headers=headers(), json={
        'name': 'New admin', 'email': 'new@example.com', 'is_admin': True,
    })
    assert response.status_code == 201, response.text
    password = response.json()['generated_password']
    assert len(password) == 8
    assert response.headers['cache-control'] == 'no-store'
    login = await client.post('/v1/auth', json={
        'email': 'new@example.com', 'password': password,
    })
    assert login.status_code == 200
    listing = await client.get('/v1/access/users', headers=headers())
    assert password not in listing.text
    assert 'generated_password' not in listing.text
    assert 'password' not in listing.json()[0]


async def test_user_can_change_own_password_with_current_and_confirmation(client, fleet):
    await provision(client, fleet)
    auth = headers('reader@example.com')
    response = await client.post('/v1/auth/password', headers=auth, json={
        'current_password': 'reader-password-123',
        'new_password': 'New!1234', 'confirm_password': 'New!1234',
    })
    assert response.status_code == 204, response.text
    assert (await client.post('/v1/auth', json={
        'email': 'reader@example.com', 'password': 'reader-password-123',
    })).status_code == 401
    assert (await client.post('/v1/auth', json={
        'email': 'reader@example.com', 'password': 'New!1234',
    })).status_code == 200
    assert (await client.post('/v1/auth', json={
        'email': 'admin@example.com', 'password': 'test-password-123',
    })).status_code == 200


@pytest.mark.parametrize('current,new,confirmation,expected', [
    ('incorrect', 'New!1234', 'New!1234', 400),
    ('reader-password-123', 'New!1234', 'Other!12', 422),
    ('reader-password-123', 'Short!1', 'Short!1', 422),
    ('reader-password-123', 'reader-password-123', 'reader-password-123', 422),
    ('reader-password-123', '😀' * 30, '😀' * 30, 422),
])
async def test_invalid_password_change_keeps_original_credential(
    client, fleet, current, new, confirmation, expected,
):
    await provision(client, fleet)
    response = await client.post('/v1/auth/password', headers=headers('reader@example.com'), json={
        'current_password': current, 'new_password': new,
        'confirm_password': confirmation,
    })
    assert response.status_code == expected, response.text
    assert (await client.post('/v1/auth', json={
        'email': 'reader@example.com', 'password': 'reader-password-123',
    })).status_code == 200


async def test_password_change_requires_authentication(client, fleet):
    response = await client.post('/v1/auth/password', json={
        'current_password': 'test-password-123',
        'new_password': 'New!1234', 'confirm_password': 'New!1234',
    })
    assert response.status_code == 401
