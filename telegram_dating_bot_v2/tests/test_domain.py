import asyncio
from unittest.mock import AsyncMock

import pytest
from conftest import add
from pydantic import ValidationError
from sqlalchemy import func, select

from app.config import Settings
from app.models import Base, ContactConsent, Match, Photo, User
from app.services.ai_service import AIService
from app.services.compatibility import calculate, eligible
from app.services.notifications import deliver
from app.validation import ProfileInput


@pytest.mark.parametrize("age", [0, 17, 101])
def test_age_rejected(profile_data, age):
    with pytest.raises(ValidationError):
        ProfileInput(**(profile_data | {"age": age}))


def test_compatibility(profile_data):
    p = profile_data
    result = calculate(p, p)
    assert result.percent == 100
    b = p | {"interests": ["музыка"], "goal": "свидания", "city": "Томск"}
    assert calculate(p, b).percent == 30
    assert calculate(p, b) == calculate(b, p)
    assert calculate(p, p | {"interests": []}).missing == ["interests"]
    assert 0 <= calculate(p, b).percent <= 100


def test_mutual_filter(profile_data):
    a = profile_data
    assert eligible(a, a)
    assert not eligible(a, a | {"min_age": 30})
    assert not eligible(a, a | {"search_city": "Томск"})
    assert not eligible(a, a | {"search_gender": "мужчина"})


async def test_registration_persistence_and_edit_age(service, profile_data):
    await add(service, 1, profile_data)
    p = await service.profile(1)
    assert p["age"] == 25 and p["photos"] == ["test-photo"]
    with pytest.raises(ValidationError):
        await service.save_profile(1, ProfileInput(**(profile_data | {"age": 17})))
    assert (await service.profile(1))["age"] == 25
    await service.db.engine.dispose()
    assert (await service.profile(1))["name"] == "Анна"


async def test_consent_required(service, profile_data):
    await service.ensure_user(1)
    with pytest.raises(ValueError):
        await service.save_profile(1, ProfileInput(**profile_data))


async def test_discovery_filters(service, profile_data):
    for uid in range(1, 5):
        await add(service, uid, profile_data)
    await service.visibility(2, False)
    await service.admin(99, {99}, "ban", 3)
    assert (await service.candidate(1))["user_id"] == 4
    await service.react(1, 4, False)
    assert await service.candidate(1) is None
    await service.visibility(2, True)
    await service.block(2, 1)
    assert await service.candidate(1) is None
    assert await service.candidate(2, 1) is None


async def test_concurrent_mutual_likes(service, profile_data):
    await add(service, 1, profile_data)
    await add(service, 2, profile_data)
    results = await asyncio.gather(service.react(1, 2, True), service.react(2, 1, True))
    assert sum(results) == 1
    assert not await service.react(1, 2, True)
    async with service.db.sessions() as s:
        assert await s.scalar(select(func.count()).select_from(Match)) == 1
    assert len(await service.matches(1)) == 1


async def test_contacts_blocks_and_permissions(service, profile_data):
    for uid in (1, 2, 3):
        await add(service, uid, profile_data)
    with pytest.raises(ValueError):
        await service.contacts(1, 3, True)
    await service.react(1, 2, True)
    await service.react(2, 1, True)
    assert await service.contacts(1, 2, True) is None
    assert await service.contacts(2, 1, True) == ("user2", "user1")
    await service.contacts(1, 2, False)
    assert await service.contacts(2, 1, True) is None
    await service.block(1, 2)
    assert not await service.matches(2)
    with pytest.raises(ValueError):
        await service.contacts(2, 1, True)
    async with service.db.sessions() as s:
        assert await s.scalar(select(func.count()).select_from(ContactConsent)) == 0


async def test_cascade_deletion(service, profile_data):
    await add(service, 1, profile_data)
    await add(service, 2, profile_data)
    await service.react(1, 2, True)
    await service.report(2, 1, "Спам")
    await service.draft(1, 2, {"name": "Секрет"})
    await service.delete_user(1)
    assert await service.profile(1) is None
    assert await service.draft(1) is None
    async with service.db.sessions() as s:
        for table in Base.metadata.sorted_tables:
            if table.name not in {
                "users",
                "profiles",
                "preferences",
                "profile_photos",
                "interests",
                "user_interests",
                "user_consents",
            }:
                assert await s.scalar(select(func.count()).select_from(table)) == 0
        assert await s.scalar(select(func.count()).select_from(User)) == 1
        assert await s.scalar(select(func.count()).select_from(Photo)) == 1


async def test_admin(service, profile_data):
    await add(service, 1, profile_data)
    with pytest.raises(ValueError):
        await service.admin(1, {99}, "ban", 1)
    await service.admin(99, {99}, "ban", 1)
    assert (await service.profile(1))["banned"]
    await service.admin(99, {99}, "unban", 1)
    assert not (await service.profile(1))["banned"]
    assert (await service.admin(99, {99}, "stats"))["active_profiles"] == 1


async def test_notifications_retry(service, profile_data):
    from aiogram.exceptions import TelegramNetworkError
    from aiogram.methods import SendMessage

    await add(service, 1, profile_data)
    await add(service, 2, profile_data)
    await service.react(1, 2, True)
    await service.react(2, 1, True)
    bot = AsyncMock()
    bot.send_message.side_effect = [
        TelegramNetworkError(method=SendMessage(chat_id=1, text="x"), message="offline"),
        None,
    ]
    await deliver(bot, service)
    assert bot.send_message.await_count == 2
    bot.send_message.side_effect = None
    await deliver(bot, service)
    assert bot.send_message.await_count == 3
    await deliver(bot, service)
    assert bot.send_message.await_count == 3


async def test_ai_consent_budget_fallback(service, profile_data):
    for uid in (1, 2):
        await add(service, uid, profile_data)
    cfg = Settings(
        _env_file=None,
        ai_enabled=True,
        ai_api_key="secret",
        ai_api_url="https://example.test",
        ai_model="test",
        ai_daily_limit=1,
    )
    provider = AsyncMock()
    provider.explain.return_value = "Общие интересы"
    ai = AIService(cfg, service, provider)
    a, b = await service.profile(1), await service.profile(2)
    result = calculate(a, b)
    assert await ai.explain(a, b, result) == result.explanation()
    provider.explain.assert_not_called()
    for uid in (1, 2):
        await service.consent(uid, "external_ai_v1", True)
    assert "AI-пояснение" in await ai.explain(a, b, result)
    assert await ai.explain(a, b, result) == result.explanation()
    payload = provider.explain.call_args.args[0]
    assert "user_id" not in str(payload) and "photos" not in str(payload)


async def test_photo_ownership(service, profile_data):
    await add(service, 1, profile_data | {"photos": ["a", "b"]})
    await add(service, 2, profile_data)
    await service.photo_action(1, 1, False)
    assert (await service.profile(1))["photos"] == ["b", "a"]
    await service.photo_action(1, 1, True)
    with pytest.raises(ValueError):
        await service.photo_action(1, 0, True)
    assert (await service.profile(2))["photos"] == ["test-photo"]


async def test_stale_photo_controls(service, profile_data):
    import hashlib

    await add(service, 1, profile_data | {"photos": ["a", "b"]})
    fingerprint = hashlib.sha256(b"a|b").hexdigest()[:10]
    await service.photo_action(1, 1, False, fingerprint)
    with pytest.raises(ValueError):
        await service.photo_action(1, 0, True, fingerprint)
    assert (await service.profile(1))["photos"] == ["b", "a"]


def test_settings_validation():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, compatibility_weights={"age": 1})
    with pytest.raises(ValidationError):
        Settings(_env_file=None, admin_ids="username")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, proxy_url="https://localhost:443")


async def test_ai_network_failure(service, profile_data):
    for uid in (1, 2):
        await add(service, uid, profile_data)
        await service.consent(uid, "external_ai_v1", True)
    provider = AsyncMock()
    provider.explain.side_effect = TimeoutError()
    cfg = Settings(
        _env_file=None,
        ai_enabled=True,
        ai_api_key="secret",
        ai_api_url="https://example.test",
        ai_model="test",
    )
    a, b = await service.profile(1), await service.profile(2)
    result = calculate(a, b)
    assert await AIService(cfg, service, provider).explain(a, b, result) == result.explanation()
