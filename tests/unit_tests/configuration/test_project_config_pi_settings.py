from concurrent.futures import ThreadPoolExecutor

from dataengineer.configuration.project_config import ProjectOverride, load_project_override, save_project_override


def test_pi_project_settings_round_trip_preserves_existing_fields(tmp_path):
    project = tmp_path / "project"
    original = ProjectOverride(target="custom/existing", default_datasource="sales", language="zh")
    save_project_override(original, cwd=str(project))
    original.pi_provider = "deepseek"
    original.pi_model = "deepseek-flash"
    original.pi_base_url = "https://api.deepseek.com"
    original.pi_thinking = "low"

    save_project_override(original, cwd=str(project))
    loaded = load_project_override(cwd=str(project))

    assert loaded.target == "custom/existing"
    assert loaded.default_datasource == "sales"
    assert loaded.language == "zh"
    assert loaded.pi_provider == "deepseek"
    assert loaded.pi_model == "deepseek-flash"
    assert loaded.pi_base_url == "https://api.deepseek.com"
    assert loaded.pi_thinking == "low"


def test_concurrent_project_settings_writes_never_leave_partial_yaml(tmp_path):
    project = tmp_path / "project"

    def save(index: int) -> None:
        save_project_override(
            ProjectOverride(
                target="custom/existing",
                pi_provider="deepseek",
                pi_model=f"model-{index}",
                pi_thinking="low",
            ),
            cwd=str(project),
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(save, range(24)))

    loaded = load_project_override(cwd=str(project))
    assert loaded is not None
    assert loaded.target == "custom/existing"
    assert loaded.pi_provider == "deepseek"
    assert loaded.pi_model in {f"model-{index}" for index in range(24)}
    assert list(project.glob(".config.yml.*.tmp")) == []
