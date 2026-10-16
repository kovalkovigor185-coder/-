from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.handlers.registration import Registration, accept, begin


async def test_fsm_registration_and_resume(service):
    await service.ensure_user(1)
    await service.consent(1, "adult_rules_v1", True)
    m = AsyncMock()
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=1, user_id=1))
    await begin(m, 1, state, service)
    assert await state.get_state() == Registration.filling.state
    await accept(m, 1, state, service, "Анна")
    await accept(m, 1, state, service, "17")
    assert (await service.draft(1))[0] == 1
    await accept(m, 1, state, service, "25")
    for value in ["женщина", "любой", "Омск", "дружба", "кино, спорт", "Привет", "18-40", "любой"]:
        await accept(m, 1, state, service, value)
    await accept(m, 1, state, service, "Готово")
    assert (await service.draft(1))[0] == 10
    await accept(m, 1, state, service, ("photo", 100))
    await service.db.engine.dispose()
    await state.clear()
    await begin(m, 1, state, service)
    assert (await service.draft(1))[1]["photos"] == ["photo"]
    await accept(m, 1, state, service, "Готово")
    assert await state.get_state() == Registration.preview.state
    from app.validation import ProfileInput

    await service.save_profile(1, ProfileInput(**(await service.draft(1))[1]))
    assert (await service.profile(1))["published"]


async def test_file_limit(service):
    await service.ensure_user(1)
    await service.draft(1, 10, {"photos": ["a"]})
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=1, user_id=1))
    await accept(AsyncMock(), 1, state, service, ("too-large", 11 * 1024 * 1024))
    assert (await service.draft(1))[1]["photos"] == ["a"]
