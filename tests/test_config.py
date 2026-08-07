from pydantic import SecretStr

from enterprise_rag.config import Settings


def test_deepseek_aliases_are_used_before_nowcoding_and_legacy_opentopia(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://deepseek.test/v1")
    monkeypatch.setenv("DEEPSEEKMODEL", "deepseek-model")
    monkeypatch.setenv("DEEPSEEK_KEY", "deepseek-key")
    monkeypatch.setenv("NOWCODING_BASE_URL", "https://nowcoding.test/v1")
    monkeypatch.setenv("NOWCODINGMODEL", "nowcoding-model")
    monkeypatch.setenv("NOWCODING_KEY", "nowcoding-key")
    monkeypatch.setenv("OPENTOPIA_OPENAI_BASE_URL", "https://legacy.test/v1")
    monkeypatch.setenv("OPENTOPIA_MODEL", "legacy-model")
    monkeypatch.setenv("OPENTOPIA_MODEL_KEY", "legacy-key")

    settings = Settings(_env_file=None)

    assert settings.llm_base_url == "https://deepseek.test/v1"
    assert settings.llm_model == "deepseek-model"
    assert settings.llm_api_key.get_secret_value() == "deepseek-key"


def test_explicit_rag_llm_aliases_override_provider_specific_aliases(monkeypatch):
    monkeypatch.setenv("RAG_LLM_BASE_URL", "https://explicit.test/v1")
    monkeypatch.setenv("RAG_LLM_MODEL", "explicit-model")
    monkeypatch.setenv("RAG_LLM_API_KEY", "explicit-key")
    monkeypatch.setenv("NOWCODING_BASE_URL", "https://nowcoding.test/v1")
    monkeypatch.setenv("NOWCODINGMODEL", "nowcoding-model")
    monkeypatch.setenv("NOWCODING_KEY", "nowcoding-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://deepseek.test/v1")
    monkeypatch.setenv("DEEPSEEKMODEL", "deepseek-model")
    monkeypatch.setenv("DEEPSEEK_KEY", "deepseek-key")

    settings = Settings(_env_file=None)

    assert settings.llm_base_url == "https://explicit.test/v1"
    assert settings.llm_model == "explicit-model"
    assert settings.llm_api_key == SecretStr("explicit-key")
