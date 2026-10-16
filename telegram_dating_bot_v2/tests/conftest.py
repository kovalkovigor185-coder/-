import pytest

from app.database import Database
from app.models import Base
from app.services.dating import DatingService
from app.validation import ProfileInput


@pytest.fixture
async def service(tmp_path):
    db = Database("sqlite+aiosqlite:///" + str(tmp_path / "test.db"))
    async with db.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield DatingService(db)
    await db.engine.dispose()


@pytest.fixture
def profile_data():
    return dict(
        name="Анна",
        age=25,
        gender="женщина",
        city="Омск",
        goal="дружба",
        interests=["кино", "спорт"],
        bio="Привет",
        min_age=18,
        max_age=40,
        search_gender="любой",
        search_city="любой",
        photos=["test-photo"],
    )


async def add(service, uid, data):
    await service.ensure_user(uid, f"user{uid}")
    await service.consent(uid, "adult_rules_v1", True)
    await service.save_profile(uid, ProfileInput(**data))
