from pydantic import BaseModel, Field, field_validator, model_validator

GENDERS = {"мужчина", "женщина", "не указан"}
GOALS = {"общение", "дружба", "свидания", "серьёзные отношения", "пока не определился"}


class ProfileInput(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    age: int = Field(ge=18, le=100)
    gender: str = "не указан"
    city: str = Field(min_length=1, max_length=80)
    goal: str
    interests: list[str] = Field(default_factory=list, max_length=15)
    bio: str = Field(default="", max_length=500)
    min_age: int = Field(default=18, ge=18, le=100)
    max_age: int = Field(default=100, ge=18, le=100)
    search_gender: str = "любой"
    search_city: str = "любой"
    photos: list[str] = Field(min_length=1, max_length=5)

    @field_validator("name", "city", "search_city")
    @classmethod
    def clean(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value) > 80:
            raise ValueError("Заполните поле (до 80 символов)")
        return value

    @model_validator(mode="after")
    def validate_choices(self):
        if self.gender not in GENDERS or self.search_gender not in GENDERS | {"любой"}:
            raise ValueError("Выберите пол из списка")
        if self.goal not in GOALS or self.min_age > self.max_age:
            raise ValueError("Проверьте цель и диапазон возраста")
        self.interests = sorted({x.strip().casefold() for x in self.interests if x.strip()})
        if any(len(x) > 40 for x in self.interests):
            raise ValueError("Интерес должен быть не длиннее 40 символов")
        return self
