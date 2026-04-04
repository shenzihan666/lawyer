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


def test_query_rewrite_settings_support_explicit_env_names(
    monkeypatch,
) -> None:
    monkeypatch.setenv("QUERY_REWRITE_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("QUERY_REWRITE_MODEL", "gpt-test")
    monkeypatch.setenv("QUERY_REWRITE_API_KEY", "rewrite-secret")

    settings = Settings(_env_file=None)

    assert settings.query_rewrite_base_url == "https://llm.example/v1"
    assert settings.query_rewrite_model == "gpt-test"
    assert settings.query_rewrite_api_key == "rewrite-secret"


def test_query_rewrite_settings_keep_legacy_env_aliases(
    monkeypatch,
) -> None:
    monkeypatch.setenv("BASE_URL", "https://legacy.example/v1")
    monkeypatch.setenv("MODEL", "legacy-chat-model")
    monkeypatch.setenv("ARK_API_KEY", "legacy-secret")

    settings = Settings(_env_file=None)

    assert settings.query_rewrite_base_url == "https://legacy.example/v1"
    assert settings.query_rewrite_model == "legacy-chat-model"
    assert settings.query_rewrite_api_key == "legacy-secret"


def test_answer_generation_settings_support_explicit_env_names(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANSWER_GENERATION_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("ANSWER_GENERATION_MODEL", "gpt-answer")
    monkeypatch.setenv("ANSWER_GENERATION_API_KEY", "answer-secret")

    settings = Settings(_env_file=None)

    assert settings.answer_generation_base_url == "https://llm.example/v1"
    assert settings.answer_generation_model == "gpt-answer"
    assert settings.answer_generation_api_key == "answer-secret"


def test_answer_generation_settings_reuse_fallback_aliases(
    monkeypatch,
) -> None:
    monkeypatch.setenv("QUERY_REWRITE_BASE_URL", "https://rewrite.example/v1")
    monkeypatch.setenv("QUERY_REWRITE_MODEL", "rewrite-model")
    monkeypatch.setenv("QUERY_REWRITE_API_KEY", "rewrite-secret")

    settings = Settings(_env_file=None)

    assert settings.answer_generation_base_url == "https://rewrite.example/v1"
    assert settings.answer_generation_model == "rewrite-model"
    assert settings.answer_generation_api_key == "rewrite-secret"


def test_rerank_settings_support_explicit_env_names(
    monkeypatch,
) -> None:
    monkeypatch.setenv("RERANK_BASE_URL", "https://rerank.example")
    monkeypatch.setenv("RERANK_MODEL", "rerank-v1")
    monkeypatch.setenv("RERANK_API_KEY", "rerank-secret")

    settings = Settings(_env_file=None)

    assert settings.rerank_base_url == "https://rerank.example"
    assert settings.rerank_model == "rerank-v1"
    assert settings.rerank_api_key == "rerank-secret"


def test_rerank_settings_support_binding_host_and_api_key_fallback(
    monkeypatch,
) -> None:
    monkeypatch.setenv("RERANK_BINDING_HOST", "https://rerank.example")
    monkeypatch.setenv("RERANK_MODEL", "rerank-v1")
    monkeypatch.setenv("ARK_API_KEY", "legacy-secret")

    settings = Settings(_env_file=None)

    assert settings.rerank_base_url == "https://rerank.example"
    assert settings.rerank_model == "rerank-v1"
    assert settings.rerank_api_key == "legacy-secret"
