from __future__ import annotations

from pathlib import Path

import pytest

from brunch.config import load_config
from brunch.errors import ConfigError
from brunch.models import ToolConfig


class TestLoadConfig:
    def test_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        cfg = load_config(tmp_path / "no-such.toml")
        assert isinstance(cfg, ToolConfig)
        assert cfg.default_forge == "github.com"
        assert cfg.root == Path("~/repos/brunch")
        assert cfg.forges == {}

    def test_loads_full_config(self, tmp_path: Path) -> None:
        target = tmp_path / "config.toml"
        target.write_text(
            """
root = "/srv/repos"
default_forge = "github.com"

[forges.github_com]
base_url = "https://github.com"

[forges.gitlab_internal]
base_url = "https://gitlab.example"
""",
            encoding="utf-8",
        )
        cfg = load_config(target)
        assert cfg.root == Path("/srv/repos")
        assert cfg.default_forge == "github.com"
        assert set(cfg.forges) == {"github_com", "gitlab_internal"}
        assert cfg.forges["github_com"].base_url == "https://github.com"

    def test_loads_partial_config_fills_defaults(self, tmp_path: Path) -> None:
        target = tmp_path / "config.toml"
        target.write_text('root = "/srv/repos"\n', encoding="utf-8")
        cfg = load_config(target)
        assert cfg.root == Path("/srv/repos")
        assert cfg.default_forge == "github.com"

    def test_invalid_toml_raises_config_error(self, tmp_path: Path) -> None:
        target = tmp_path / "config.toml"
        target.write_text("not = valid = toml\n", encoding="utf-8")
        with pytest.raises(ConfigError, match="failed to parse"):
            load_config(target)

    def test_unknown_field_raises_config_error(self, tmp_path: Path) -> None:
        target = tmp_path / "config.toml"
        target.write_text('mystery_field = "x"\n', encoding="utf-8")
        with pytest.raises(ConfigError, match="invalid configuration"):
            load_config(target)

    def test_wrong_type_raises_config_error(self, tmp_path: Path) -> None:
        target = tmp_path / "config.toml"
        target.write_text("forges = 42\n", encoding="utf-8")
        with pytest.raises(ConfigError, match="invalid configuration"):
            load_config(target)


class TestDefaultConfigPath:
    def test_respects_xdg_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        # Re-import to pick up the env change in platformdirs (it caches).
        from importlib import reload

        import brunch.config as cfg_module

        reload(cfg_module)
        path = cfg_module.default_config_path()
        assert str(path).startswith(str(tmp_path))
        assert path.name == "config.toml"
