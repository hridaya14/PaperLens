import os
import sys
from pathlib import Path
from alembic import context
from sqlalchemy import engine_from_config, pool

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src.db.interfaces.postgresql import Base
import src.models  # noqa

config = context.config
target_metadata = Base.metadata

database_url = os.getenv("POSTGRES_DATABASE_URL")
if not database_url:
    raise RuntimeError("POSTGRES_DATABASE_URL is not set")

config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()