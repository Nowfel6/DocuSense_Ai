"""Online-only Alembic environment for the disposable database test harness.

The connection is supplied by the harness; this file has no default database URL.
Production integration must use the application's reviewed Alembic environment.
"""
from alembic import context

if context.is_offline_mode():
    raise RuntimeError("This verification environment requires online PostgreSQL")
connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError("An explicit test connection is required")
context.configure(connection=connection, target_metadata=None, version_table_schema="public")
with context.begin_transaction():
    context.run_migrations()
