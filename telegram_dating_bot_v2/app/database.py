from contextlib import asynccontextmanager

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


class Database:
    def __init__(self, url: str):
        self.engine = create_async_engine(
            url, **({"connect_args": {"timeout": 30}} if url.startswith("sqlite") else {})
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        if url.startswith("sqlite"):

            @event.listens_for(self.engine.sync_engine, "connect")
            def configure(connection, _):
                cursor = connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.close()

    @asynccontextmanager
    async def transaction(self):
        async with self.sessions() as session, session.begin():
            if self.engine.dialect.name == "sqlite":
                await session.execute(text("BEGIN IMMEDIATE"))
            else:
                # Serialize graph mutations across workers; replace with ordered row locks at scale.
                await session.execute(text("SELECT pg_advisory_xact_lock(1852026)"))
            yield session
