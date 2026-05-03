from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "mysql+pymysql://root:password@localhost:3306/learndo"
    api_ninjas_key: str = ""
    secret_key: str = "change-me-in-production"
    token_expire_days: int = 30
    # "external" uses API-Ninjas + Free Dictionary API
    # "openai"   uses OpenAI gpt-5-nano for both random word and definition
    word_service: str = "external"
    openai_api_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
