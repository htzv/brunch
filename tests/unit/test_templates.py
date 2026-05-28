from __future__ import annotations

from pathlib import Path

import pytest

from brunch.errors import TemplateError
from brunch.templates import materialise_template


def _write_template(home: Path, template_id: str, body: str) -> None:
    target = home / ".config" / "brunch" / "templates"
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{template_id}.toml").write_text(body, encoding="utf-8")


class TestMaterialiseTemplate:
    def test_full_template_round_trips(self, isolated_home: Path) -> None:
        _write_template(
            isolated_home,
            "t1",
            """
            description = "desc"

            [[repo]]
            repo = "kybernetix/api"
            branch = "explicit"
            base = "develop"
            """,
        )
        m = materialise_template("t1", workspace_name="task-1")
        assert m.name == "task-1"
        assert m.description == "desc"
        assert len(m.repos) == 1
        assert m.repos[0].repo == "kybernetix/api"
        assert m.repos[0].branch == "explicit"
        assert m.repos[0].base == "develop"

    def test_missing_branch_defaults_to_workspace_name(self, isolated_home: Path) -> None:
        _write_template(
            isolated_home,
            "t2",
            """
            [[repo]]
            repo = "kybernetix/api"
            base = "main"
            """,
        )
        m = materialise_template("t2", workspace_name="task-billing")
        assert m.repos[0].branch == "task-billing"

    def test_missing_base_defaults_to_main(self, isolated_home: Path) -> None:
        _write_template(
            isolated_home,
            "t3",
            """
            [[repo]]
            repo = "kybernetix/api"
            """,
        )
        m = materialise_template("t3", workspace_name="task-x")
        assert m.repos[0].base == "main"
        assert m.repos[0].branch == "task-x"

    def test_template_name_field_is_overridden_by_workspace_name(self, isolated_home: Path) -> None:
        _write_template(
            isolated_home,
            "t4",
            'name = "ignored"\n[[repo]]\nrepo = "kybernetix/api"\n',
        )
        m = materialise_template("t4", workspace_name="actual")
        assert m.name == "actual"

    def test_template_without_repos_is_valid(self, isolated_home: Path) -> None:
        _write_template(isolated_home, "t5", 'description = "empty template"\n')
        m = materialise_template("t5", workspace_name="task-x")
        assert m.repos == []

    def test_missing_template_raises(self, isolated_home: Path) -> None:
        with pytest.raises(TemplateError, match="not found"):
            materialise_template("nonexistent", workspace_name="x")

    def test_invalid_toml_raises(self, isolated_home: Path) -> None:
        _write_template(isolated_home, "broken", "not = valid = toml")
        with pytest.raises(TemplateError, match="failed to parse"):
            materialise_template("broken", workspace_name="x")

    def test_repo_not_a_list_raises(self, isolated_home: Path) -> None:
        _write_template(isolated_home, "wrong", 'repo = "scalar"\n')
        with pytest.raises(TemplateError, match="must be an array"):
            materialise_template("wrong", workspace_name="x")

    def test_validation_error_is_template_error(self, isolated_home: Path) -> None:
        _write_template(
            isolated_home,
            "incomplete",
            '[[repo]]\nbranch = "f"\nbase = "main"\n',  # missing `repo` field
        )
        with pytest.raises(TemplateError, match="does not match the manifest schema"):
            materialise_template("incomplete", workspace_name="x")


class TestTemplatePath:
    def test_path_under_user_config_dir(self, isolated_home: Path) -> None:
        # platformdirs caches paths; force a re-read by re-importing.
        from importlib import reload

        import brunch.config as cfg
        import brunch.templates as tpl

        reload(cfg)
        reload(tpl)
        path = tpl.template_path("my-template")
        assert path.name == "my-template.toml"
        assert "brunch" in path.parts
