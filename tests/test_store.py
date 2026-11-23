import json

from appscout.cli import _researchers, _tpm_limits
from appscout.pipeline import Deps, run_app
from appscout.schema import App
from appscout.store import Store

from conftest import make_finding
from test_pipeline import FakeFetcher, FakeLlm, FakeTools

APPS = [
    App(id=name, name=name.title(), website=f"{name}.test", category="CRM and Sales", batch=1)
    for name in ("zeta", "acme")
]


def store_with_apps(tmp_path) -> Store:
    rows = "".join(f"{a.id},{a.name},{a.website},{a.category},{a.batch}\n" for a in APPS)
    (tmp_path / "apps.csv").write_text("id,name,website,category,batch\n" + rows, encoding="utf-8")
    return Store(tmp_path)


async def finish(app, store):
    deps = Deps(
        llm=FakeLlm([make_finding()]),
        tools=FakeTools(),
        fetcher=FakeFetcher(),
        store=store,
        now=lambda: "2026-11-23T00:00:00+00:00",
    )
    return await run_app(app, deps)


def result_ids(store) -> list[str]:
    return [json.loads(line)["id"] for line in store.results_file.read_text(encoding="utf-8").splitlines()]


async def test_results_file_gains_a_line_as_each_app_finishes_and_keeps_app_list_order(tmp_path):
    store = store_with_apps(tmp_path)
    await finish(APPS[1], store)
    assert result_ids(store) == ["acme"]
    await finish(APPS[0], store)
    assert result_ids(store) == ["zeta", "acme"]


async def test_redoing_an_app_replaces_its_line_instead_of_duplicating_it(tmp_path):
    store = store_with_apps(tmp_path)
    await finish(APPS[1], store)
    store.clear("acme")
    assert result_ids(store) == []
    await finish(APPS[1], store)
    assert result_ids(store) == ["acme"]


async def test_writes_leave_no_temporary_files_behind(tmp_path):
    store = store_with_apps(tmp_path)
    await finish(APPS[1], store)
    assert list(tmp_path.rglob("*.tmp")) == []


def test_researcher_pool_setting_gives_each_deployment_its_workers_and_optional_critic():
    setting = "gpt-6-sol@OPENAI:3/grok-4.7@OPENAI, gpt-6.2-sol@COMPOSER:3/gpt-6-sol@OPENAI, grok-4.7:2"
    assert _researchers(setting) == [
        ("gpt-6-sol", "OPENAI", 3, "grok-4.7", "OPENAI"),
        ("gpt-6.2-sol", "COMPOSER", 3, "gpt-6-sol", "OPENAI"),
        ("grok-4.7", "OPENAI", 2, None, None),
    ]
    assert _researchers("") == []
    assert _tpm_limits("gpt-6-sol=125000, grok-4.7=45000") == {"gpt-6-sol": 125000, "grok-4.7": 45000}
