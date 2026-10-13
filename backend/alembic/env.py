from sqlalchemy import create_engine, pool

from alembic import context
from app.core.config import Settings
from app.core.database import Base
from app.models import Diagnosis, LearningEvent, ModelTrace  # noqa: F401

config = context.config
url = Settings().database_url
if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(url, poolclass=pool.NullPool).connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
