from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    bot_token: SecretStr = SecretStr("")
    database_url: str = "sqlite+aiosqlite:///./dating.db"
    admin_ids: str = ""
    proxy_url: SecretStr = SecretStr("")
    ai_api_key: SecretStr = SecretStr("")
    ai_enabled: bool = False
    ai_api_url: str = ""
    ai_model: str = ""
    ai_daily_limit: int = 20
    log_level: str = "INFO"
    compatibility_weights: dict[str, float] = {
        "goals": 30,
        "interests": 25,
        "age": 20,
        "city": 15,
        "preferences": 10,
    }

    @field_validator("proxy_url")
    @classmethod
    def proxy_scheme(cls, value: SecretStr) -> SecretStr:
        from urllib.parse import urlsplit

        raw = value.get_secret_value()
        if raw:
            parsed = urlsplit(raw)
            if parsed.scheme not in {"http", "socks5"} or not parsed.hostname or not parsed.port:
                raise ValueError("PROXY_URL: требуется http:// или socks5:// с адресом и портом")
        return value

    @field_validator("compatibility_weights")
    @classmethod
    def weights_valid(cls, weights: dict[str, float]) -> dict[str, float]:
        import math

        if set(weights) != {"goals", "interests", "age", "city", "preferences"}:
            raise ValueError("Укажите все пять весов совместимости")
        if any(not math.isfinite(v) or v <= 0 for v in weights.values()):
            raise ValueError("Веса должны быть конечными положительными числами")
        return weights

    @field_validator("admin_ids")
    @classmethod
    def admins_valid(cls, value: str) -> str:
        if any(not x.strip().isdigit() for x in value.split(",") if x.strip()):
            raise ValueError("ADMIN_IDS содержит только числовые ID через запятую")
        return value

    @property
    def admins(self) -> set[int]:
        return {int(x.strip()) for x in self.admin_ids.split(",") if x.strip()}
