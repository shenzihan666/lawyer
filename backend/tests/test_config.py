from app.core.config import Settings


def test_embedding_settings_support_explicit_env_names(
    monkeypatch,
) -> None:
    monkeypatch.setenv("EMBEDDING_BASE_URL", "https://emb.example/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-test")
    monkeypatch.setenv("EMBEDDING_API_KEY", "secret")

    settings = Settings(_env_file=None)

    assert settings.embedding_base_url == "https://emb.example/v1"
    assert settings.embedding_model == "text-embedding-test"
    assert settings.embedding_api_key == "secret"


def test_embedding_settings_keep_legacy_env_aliases(
    monkeypatch,
) -> None:
    monkeypatch.setenv("BASE_URL", "https://legacy.example/v1")
    monkeypatch.setenv("EMBEDDER", "legacy-embedding-model")
    monkeypatch.setenv("ARK_API_KEY", "legacy-secret")

    settings = Settings(_env_file=None)

    assert settings.embedding_base_url == "https://legacy.example/v1"
    assert settings.embedding_model == "legacy-embedding-model"
    assert settings.embedding_api_key == "legacy-secret"
