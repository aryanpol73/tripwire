"""D-070: several hosts serving the same model split one eval; a host out of quota stops
and the others finish its work."""

import argparse
import json

from tests.llm_policy import first_visit_policy
from tripwire.eval import llm_eval
from tripwire.llm import client
from tripwire.llm.client import PolicySource, QuotaExhausted


class FakeHost(PolicySource):
    def __init__(self, host, quota_after=None):
        super().__init__(first_visit_policy(), cost=100)
        self.host, self.model, self.quota_after, self.calls = host, f"{host}-model", quota_after, 0

    def decide(self, request):
        self.calls += 1
        if self.quota_after is not None and self.calls > self.quota_after:
            raise QuotaExhausted(f"{self.host}: daily quota")
        return super().decide(request)


def args(tmp_path, **kw):
    base = dict(set="redteam", only="^(rt01|rt02|rt05)", out=str(tmp_path / "out"),
                replay_dir=None, record_dir=None, llm_cap=None, resume=False,
                chromium_executable=None)  # fmt: skip
    return argparse.Namespace(**(base | kw))


def test_a_host_out_of_quota_hands_its_target_to_the_other(tmp_path, monkeypatch):
    hosts = [FakeHost("a", quota_after=2), FakeHost("b")]
    monkeypatch.setattr(client, "model_sources", lambda env=None: hosts)
    llm_eval.evaluate_llm(args(tmp_path))
    summary = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
    assert summary["complete"] is True
    assert summary["quota_exhausted"] == ["a"]
    ids = [r["id"] for r in summary["runs"]]
    assert sorted(ids) == sorted(set(ids)) and len(ids) == 3  # each target exactly once
    assert {r["host"] for r in summary["runs"]} <= {"a", "b"}
    assert summary["by_host"]["b"]["runs"] >= 2
    assert summary["hosts"] == {"a": "a-model", "b": "b-model"}


def test_when_every_host_is_out_resume_finishes_later(tmp_path, monkeypatch):
    monkeypatch.setattr(client, "model_sources", lambda env=None: [FakeHost("a", 3)])
    llm_eval.evaluate_llm(args(tmp_path))
    first = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
    assert first["complete"] is False and len(first["runs"]) < 3
    monkeypatch.setattr(client, "model_sources", lambda env=None: [FakeHost("b")])
    llm_eval.evaluate_llm(args(tmp_path, resume=True))
    second = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
    assert second["complete"] is True and len(second["runs"]) == 3
