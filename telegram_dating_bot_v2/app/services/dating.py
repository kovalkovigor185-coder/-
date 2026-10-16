from datetime import timedelta

from sqlalchemy import delete, func, or_, select

from app.models import (
    Block,
    ContactConsent,
    Draft,
    Interest,
    Like,
    Match,
    ModerationAction,
    Photo,
    Preference,
    Profile,
    Report,
    User,
    UserConsent,
    UserInterest,
    utcnow,
)
from app.services.compatibility import eligible
from app.validation import ProfileInput


class DatingService:
    def __init__(self, db):
        self.db = db

    async def ensure_user(self, uid: int, username: str | None = None):
        async with self.db.transaction() as s:
            u = await s.get(User, uid)
            if not u:
                s.add(User(id=uid, username=username))
            else:
                u.username = username

    async def consent(self, uid: int, kind: str, granted: bool):
        async with self.db.transaction() as s:
            row = await s.get(UserConsent, (uid, kind))
            if row:
                row.granted = granted
            else:
                s.add(UserConsent(user_id=uid, kind=kind, granted=granted))

    async def has_consent(self, uid: int, kind: str) -> bool:
        async with self.db.sessions() as s:
            row = await s.get(UserConsent, (uid, kind))
            return bool(row and row.granted)

    async def draft(self, uid: int, step: int | None = None, data: dict | None = None):
        async with self.db.transaction() as s:
            d = await s.get(Draft, uid)
            if step is None:
                return (d.step, d.data) if d else None
            if d:
                d.step, d.data = step, data or {}
            else:
                s.add(Draft(user_id=uid, step=step, data=data or {}))

    async def cancel_draft(self, uid: int):
        async with self.db.transaction() as s:
            await s.execute(delete(Draft).where(Draft.user_id == uid))

    async def save_profile(self, uid: int, data: ProfileInput):
        async with self.db.transaction() as s:
            u = await s.get(User, uid)
            consent = await s.get(UserConsent, (uid, "adult_rules_v1"))
            if not u or u.banned or not consent or not consent.granted:
                raise ValueError("Подтвердите возраст и правила через /start")
            p = await s.get(Profile, uid)
            fields = data.model_dump(include={"name", "age", "gender", "city", "goal", "bio"})
            if p:
                for k, v in fields.items():
                    setattr(p, k, v)
                p.published = True
            else:
                s.add(Profile(user_id=uid, published=True, **fields))
            pref = await s.get(Preference, uid)
            fields = {
                "min_age": data.min_age,
                "max_age": data.max_age,
                "gender": data.search_gender,
                "city": data.search_city,
            }
            if pref:
                for k, v in fields.items():
                    setattr(pref, k, v)
            else:
                s.add(Preference(user_id=uid, **fields))
            await s.execute(delete(Photo).where(Photo.user_id == uid))
            await s.execute(delete(UserInterest).where(UserInterest.user_id == uid))
            for i, photo in enumerate(data.photos):
                s.add(Photo(user_id=uid, file_id=photo, position=i))
            for name in data.interests:
                interest = await s.scalar(select(Interest).where(Interest.name == name))
                if not interest:
                    interest = Interest(name=name)
                    s.add(interest)
                    await s.flush()
                s.add(UserInterest(user_id=uid, interest_id=interest.id))
            await s.execute(delete(Draft).where(Draft.user_id == uid))

    async def snapshot(self, s, uid: int) -> dict | None:
        p, pref, u = await s.get(Profile, uid), await s.get(Preference, uid), await s.get(User, uid)
        if not p or not pref or not u:
            return None
        interests = list(
            await s.scalars(select(Interest.name).join(UserInterest).where(UserInterest.user_id == uid))
        )
        photos = list(
            await s.scalars(
                select(Photo.file_id).where(Photo.user_id == uid).order_by(Photo.position, Photo.id)
            )
        )
        return {
            "user_id": uid,
            "name": p.name,
            "age": p.age,
            "gender": p.gender,
            "city": p.city,
            "goal": p.goal,
            "bio": p.bio,
            "published": p.published,
            "banned": u.banned,
            "min_age": pref.min_age,
            "max_age": pref.max_age,
            "search_gender": pref.gender,
            "search_city": pref.city,
            "interests": interests,
            "photos": photos,
        }

    async def profile(self, uid: int):
        async with self.db.sessions() as s:
            return await self.snapshot(s, uid)

    async def accessible(self, s, a: int, b: int) -> bool:
        if a == b:
            return False
        ua, ub = await s.get(User, a), await s.get(User, b)
        return bool(
            ua
            and ub
            and not ua.banned
            and not ub.banned
            and not await s.get(Block, (a, b))
            and not await s.get(Block, (b, a))
        )

    async def candidate(self, uid: int, target: int | None = None, rated: bool = False):
        async with self.db.sessions() as s:
            a = await self.snapshot(s, uid)
            if not a or a["banned"] or not a["published"]:
                return None
            ids = (
                [target]
                if target
                else list(
                    await s.scalars(
                        select(Profile.user_id)
                        .where(Profile.published.is_(True), Profile.user_id != uid)
                        .order_by(Profile.user_id)
                    )
                )
            )
            for other in ids:
                if not await self.accessible(s, uid, other):
                    continue
                b = await self.snapshot(s, other)
                if b and b["published"] and b["photos"] and eligible(a, b):
                    if rated or not await s.get(Like, (uid, other)):
                        return b
            return None

    async def react(self, uid: int, target: int, positive: bool) -> bool:
        async with self.db.transaction() as s:
            a, b = await self.snapshot(s, uid), await self.snapshot(s, target)
            if (
                not a
                or not b
                or not await self.accessible(s, uid, target)
                or not a["published"]
                or not b["published"]
                or not eligible(a, b)
            ):
                raise ValueError("Анкета больше недоступна")
            if await s.get(Like, (uid, target)):
                return False
            count = await s.scalar(
                select(func.count())
                .select_from(Like)
                .where(Like.source == uid, Like.created_at >= utcnow() - timedelta(hours=1))
            )
            if count >= 60:
                raise ValueError("Лимит 60 оценок в час. Попробуйте позже")
            s.add(Like(source=uid, target=target, positive=positive))
            await s.flush()
            reverse = await s.get(Like, (target, uid))
            key = tuple(sorted((uid, target)))
            if positive and reverse and reverse.positive and not await s.get(Match, key):
                s.add(Match(a=key[0], b=key[1]))
                return True
            return False

    async def matches(self, uid: int) -> list[dict]:
        async with self.db.sessions() as s:
            rows = list(
                await s.scalars(
                    select(Match).where(or_(Match.a == uid, Match.b == uid), Match.active.is_(True))
                )
            )
            result = []
            for row in rows:
                other = row.b if row.a == uid else row.a
                if await self.accessible(s, uid, other):
                    p = await self.snapshot(s, other)
                    if p:
                        result.append(p)
            return result

    async def contacts(self, uid: int, target: int, granted: bool):
        async with self.db.transaction() as s:
            m = await s.get(Match, tuple(sorted((uid, target))))
            if not m or not m.active or not await self.accessible(s, uid, target):
                raise ValueError("Совпадение недоступно")
            c = await s.get(ContactConsent, (uid, target))
            if c:
                c.granted = granted
            else:
                s.add(ContactConsent(source=uid, target=target, granted=granted))
            await s.flush()
            reverse = await s.get(ContactConsent, (target, uid))
            if granted and reverse and reverse.granted:
                a, b = await s.get(User, uid), await s.get(User, target)
                return a.username, b.username
            return None

    async def block(self, uid: int, target: int):
        async with self.db.transaction() as s:
            if not await self.accessible(s, uid, target):
                raise ValueError("Пользователь недоступен")
            s.add(Block(source=uid, target=target))
            await self._remove_match(s, uid, target)

    async def _remove_match(self, s, uid: int, target: int):
        m = await s.get(Match, tuple(sorted((uid, target))))
        if m:
            m.active = False
        await s.execute(
            delete(ContactConsent).where(
                or_(
                    (ContactConsent.source == uid) & (ContactConsent.target == target),
                    (ContactConsent.source == target) & (ContactConsent.target == uid),
                )
            )
        )

    async def remove_match(self, uid: int, target: int):
        async with self.db.transaction() as s:
            await self._remove_match(s, uid, target)

    async def report(self, uid: int, target: int, reason: str):
        async with self.db.transaction() as s:
            if not await self.accessible(s, uid, target):
                raise ValueError("Анкета недоступна")
            recent = await s.scalar(
                select(Report).where(
                    Report.source == uid, Report.target == target, Report.resolved.is_(False)
                )
            )
            if not recent:
                s.add(Report(source=uid, target=target, reason=reason))

    async def visibility(self, uid: int, visible: bool):
        async with self.db.transaction() as s:
            p, u = await s.get(Profile, uid), await s.get(User, uid)
            if not p or u.banned:
                raise ValueError("Анкета недоступна")
            p.published = visible

    async def delete_user(self, uid: int):
        async with self.db.transaction() as s:
            await s.execute(delete(User).where(User.id == uid))
            unused = select(UserInterest.interest_id)
            await s.execute(delete(Interest).where(Interest.id.not_in(unused)))

    async def photo_action(self, uid: int, position: int, remove: bool, expected: str | None = None):
        async with self.db.transaction() as s:
            photos = list(
                await s.scalars(select(Photo).where(Photo.user_id == uid).order_by(Photo.position, Photo.id))
            )
            if expected is not None:
                import hashlib

                current = hashlib.sha256("|".join(p.file_id for p in photos).encode()).hexdigest()[:10]
                if expected != current:
                    raise ValueError("Фото уже изменены. Откройте раздел заново")
            if not 0 <= position < len(photos):
                raise ValueError("Фото уже изменены. Откройте раздел заново")
            if remove:
                if len(photos) <= 1:
                    raise ValueError("Оставьте хотя бы одно фото")
                await s.delete(photos[position])
                photos.pop(position)
            else:
                photos.insert(0, photos.pop(position))
            for i, photo in enumerate(photos):
                photo.position = i

    async def likes(self, uid: int):
        async with self.db.sessions() as s:
            incoming = await s.scalar(
                select(func.count()).select_from(Like).where(Like.target == uid, Like.positive.is_(True))
            )
            ids = list(
                await s.scalars(select(Like.target).where(Like.source == uid, Like.positive.is_(True)))
            )
            names = []
            for target in ids:
                if await self.accessible(s, uid, target):
                    p = await self.snapshot(s, target)
                    if p and p["published"]:
                        names.append(p["name"])
            return incoming, names

    async def admin(self, uid: int, admins: set[int], action: str, target: int = 0):
        if uid not in admins:
            raise ValueError("Нет доступа")
        async with self.db.transaction() as s:
            if action == "stats":
                return {
                    table.__tablename__: await s.scalar(select(func.count()).select_from(table))
                    for table in (User, Profile, Like, Match)
                } | {
                    "active_profiles": await s.scalar(
                        select(func.count()).select_from(Profile).where(Profile.published.is_(True))
                    )
                }
            if action == "reports":
                rows = list(
                    await s.scalars(
                        select(Report).where(Report.resolved.is_(False)).order_by(Report.id).limit(30)
                    )
                )
                return [(r.id, r.target, r.reason) for r in rows]
            if action == "resolve":
                r = await s.get(Report, target)
                if not r:
                    raise ValueError("Жалоба не найдена")
                r.resolved = True
                s.add(ModerationAction(admin_id=uid, target=r.target, action="resolve"))
                return "Жалоба закрыта"
            u = await s.get(User, target)
            if not u:
                raise ValueError("Пользователь не найден")
            if action in {"ban", "unban"}:
                u.banned = action == "ban"
            elif action == "hide":
                p = await s.get(Profile, target)
                if p:
                    p.published = False
            else:
                raise ValueError("Неизвестная команда")
            s.add(ModerationAction(admin_id=uid, target=target, action=action))
            return "Готово"
