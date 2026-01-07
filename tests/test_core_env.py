from agent_wt.core import Ctx, default_agent_command, merged_env


def test_default_agent_command_env_override(monkeypatch):
    monkeypatch.setenv("AGENT_WT_CMD_CODEX", "codex --profile foo")
    assert default_agent_command("codex") == "codex --profile foo"


def test_merged_env_includes_entry_and_os(monkeypatch):
    monkeypatch.setenv("BASE_ENV", "1")
    entry = {"env": {"FOO": "bar"}}
    env = merged_env(entry)
    assert env["FOO"] == "bar"
    assert env["BASE_ENV"] == "1"
