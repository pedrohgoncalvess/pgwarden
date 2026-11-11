# Users, roles, and resource access

Apply `20261031_01_access-control` with the PostgreSQL migrations before starting
the updated API. Administrators manage accounts in **Settings → Users** and
roles in **Settings → Roles**. Each non-administrator must have one role; existing non-administrator
accounts without a role have no resource access until assigned. Administrators
always have access to every project, server, and database.

Creating an account in the interface generates an eight-character password with
letters, numbers, and symbols. The initial credential is shown once to the
administrator after creation. Every signed-in user can open **Settings → Change
password**, enter the current password, and confirm a new password of at least
eight characters. Passwords are hashed before storage.

Roles explicitly select projects, servers, and databases. Selecting a project
does not automatically grant every server or database beneath it. A server with
a project requires that project's grant, and a database requires its server's
grant. Local servers without a project can be granted directly. Removing a
parent grant also blocks stale child grants. Catalogs, search, tags, alerts,
scheduler controls, and live streams enforce these boundaries in the API.

Each role has six independent capabilities: `alerts.read`, `alerts.configure`,
`documentation.read`, `documentation.configure`, `schedulers.read`, and
`schedulers.configure`. Enable both read and configure for a feature when its
users should manage it through the interface. User and role management, project
keys, and connection provisioning remain administrator-only. Removing an account
blocks login and existing tokens; the last active administrator cannot be removed.

Run the access-control integration suite with `INGESTION_TEST_DATABASE_URL` set
to a disposable PostgreSQL administrative connection and run
`pytest tests/test_access_control.py` from `api/`. The tests create and remove
their own database, including migration rollback validation.
