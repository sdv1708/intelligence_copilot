"""Tests for typed configuration and storage resolution."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from core import config as config_module
from core.config import Provider, Settings, get_settings, reset_settings_cache
from core.exceptions import MissingAPIKeyError


class TestDerivedPaths:
    def test_paths_derive_from_data_dir(self, tmp_path: Path) -> None:
        settings = Settings(_env_file=None, data_dir=tmp_path / "store")

        assert settings.db_path == tmp_path / "store" / "briefs.db"
        assert settings.faiss_dir == tmp_path / "store" / "faiss"
        assert settings.raw_dir == tmp_path / "store" / "raw"

    def test_index_path_is_namespaced_per_meeting(self, tmp_path: Path) -> None:
        settings = Settings(_env_file=None, data_dir=tmp_path)

        assert settings.index_path("meeting_abc") == tmp_path / "faiss" / "meeting_abc.faiss"

    def test_legacy_env_names_still_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Existing .env files use DB_PATH and FAISS_PATH; don't break them."""
        monkeypatch.setenv("DB_PATH", str(tmp_path / "custom.db"))
        monkeypatch.setenv("FAISS_PATH", str(tmp_path / "vectors"))

        settings = Settings(_env_file=None, data_dir=tmp_path / "ignored")

        assert settings.db_path == tmp_path / "custom.db"
        assert settings.faiss_dir == tmp_path / "vectors"


class TestApiKeys:
    def test_returns_key_for_selected_provider(self) -> None:
        settings = Settings(
            _env_file=None,
            llm_provider=Provider.ANTHROPIC,
            anthropic_api_key="sk-ant-test",
        )

        assert settings.api_key_for() == "sk-ant-test"

    def test_raises_with_actionable_message_when_missing(self) -> None:
        settings = Settings(_env_file=None, llm_provider=Provider.OPENAI)

        with pytest.raises(MissingAPIKeyError) as excinfo:
            settings.api_key_for()

        assert "OPENAI_API_KEY" in str(excinfo.value)
        assert excinfo.value.provider == "openai"

    def test_blank_key_counts_as_missing(self) -> None:
        settings = Settings(_env_file=None, llm_provider=Provider.GEMINI, gemini_api_key="   ")

        with pytest.raises(MissingAPIKeyError):
            settings.api_key_for()

    def test_has_api_key_does_not_raise(self) -> None:
        settings = Settings(_env_file=None, llm_provider=Provider.GEMINI)

        assert settings.has_api_key() is False

    def test_can_query_a_provider_other_than_the_default(self) -> None:
        settings = Settings(
            _env_file=None,
            llm_provider=Provider.GEMINI,
            gemini_api_key="g",
            openai_api_key="o",
        )

        assert settings.api_key_for(Provider.OPENAI) == "o"

    def test_key_is_not_exposed_in_repr(self) -> None:
        settings = Settings(_env_file=None, gemini_api_key="super-secret-value")

        assert "super-secret-value" not in repr(settings)


class TestValidation:
    def test_overlap_must_be_smaller_than_chunk_size(self) -> None:
        with pytest.raises(ValidationError, match="chunk_overlap"):
            Settings(_env_file=None, chunk_size=500, chunk_overlap=500)

    def test_unknown_provider_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, llm_provider="llama")

    def test_temperature_is_bounded(self) -> None:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, llm_temperature=5.0)


class TestPrepareStorage:
    def test_creates_all_directories(self, tmp_path: Path) -> None:
        settings = Settings(_env_file=None, data_dir=tmp_path / "fresh")

        settings.prepare_storage()

        assert settings.data_dir.is_dir()
        assert settings.faiss_dir.is_dir()
        assert settings.raw_dir.is_dir()

    def test_falls_back_to_temp_when_data_dir_is_read_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A read-only deployment should degrade, not crash -- but only then."""
        monkeypatch.setattr(config_module, "_is_writable", lambda _path: False)
        settings = Settings(_env_file=None, data_dir=tmp_path / "readonly")

        settings.prepare_storage()

        assert settings.data_dir != tmp_path / "readonly"
        assert "intelligence_copilot" in str(settings.data_dir)

    def test_writable_directory_is_left_alone(self, tmp_path: Path) -> None:
        """Regression: the old code relocated storage whenever /tmp merely existed."""
        target = tmp_path / "perfectly_fine"
        settings = Settings(_env_file=None, data_dir=target)

        settings.prepare_storage()

        assert settings.data_dir == target


class TestSettingsCache:
    def test_get_settings_is_memoised(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("DATA_DIR", str(tmp_path / "cached"))
        reset_settings_cache()

        assert get_settings() is get_settings()

    def test_reset_allows_reconfiguration(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("DATA_DIR", str(tmp_path / "first"))
        reset_settings_cache()
        first = get_settings()

        monkeypatch.setenv("DATA_DIR", str(tmp_path / "second"))
        reset_settings_cache()
        second = get_settings()

        assert first.data_dir != second.data_dir
