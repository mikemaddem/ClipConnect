from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    storage_backend: str = "local"
    storage_local_dir: str = "./media"
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    library_dir: str = "./data"
    max_upload_bytes: int = 2147483648
    host: str = "127.0.0.1"
    port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
