"""tests/gnm/test_h8_git_dependency_resolver.py

Adversarial + positive tests for the H8 Git dependency resolver (scripts/gnm/h8_git_dependency_resolver.py)
and its fail-closed provider preflight integration.

NON-Isaac, NON-capturing. Real behaviour is exercised against REAL temporary Git repositories (git init +
commit + controlled mutation) so index/worktree/symlink/mode states are genuine; a small FakeGit runner
covers states that need tooling absent here (git-lfs) or that are awkward to construct (submodule/timeout/
shallow). No Isaac, ROS 2, camera, robot, render, drive, image, trajectory, rosbag, dataset or capture.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.gnm import h8_git_dependency_resolver as R  # noqa: E402
from scripts.gnm import h8_evidence_provider as prov  # noqa: E402
from scripts.gnm import h8_evidence_schema as es  # noqa: E402

MV = "h8-dependency-manifest/1.0.0"
CLK = "2026-07-16T12:00:00Z"


def _git(repo, *a):
    subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)


def _init_repo(tmp_path, files):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "x@y.z")
    _git(repo, "config", "user.name", "x")
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    root = subprocess.run(["git", "-C", str(repo), "rev-list", "--max-parents=0", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    return repo, root, head


def _manifest(repo, root, deps):
    return {"manifest_version": MV,
            "expected_repository": {"canonical_name": os.path.basename(str(repo)), "root_commit": root,
                                    "identity_policy": "root_commit_and_name"},
            "dependencies": deps}


def _dep(id_, path, **kw):
    d = {"id": id_, "path": path, "type": "f", "required": True}
    d.update(kw)
    return d


def _resolve(repo, root, deps, **kw):
    man = _manifest(repo, root, deps)
    return R.GitDependencyResolver(str(repo), **kw).build_resolution_report(man)


def _reason_of(rep, dep_id):
    for r in rep["results"]:
        if r["dependency_id"] == dep_id:
            return r["reason_code"]
    return rep["reason_code"]


# ── FakeGit for git-level and exotic states ─────────────────────────────────────────
class FakeGit:
    def __init__(self, responses, *, raise_on=None):
        self.responses = responses            # (argtuple-prefix) -> bytes stdout
        self.raise_on = raise_on              # (prefix) -> R.GitError

    def run(self, repo_root, args, *, check=True):
        key = tuple(args)
        if self.raise_on:
            for pref, err in self.raise_on.items():
                if key[:len(pref)] == pref:
                    raise err
        for pref, out in self.responses.items():
            if key[:len(pref)] == pref:
                return {"rc": 0, "out": out, "err": b""}
        return {"rc": 0, "out": b"", "err": b""}


# =====================================================================================
# POSITIVE PATH (§26) — proves the resolver is NOT reject-all
# =====================================================================================
def test_pos_clean_single_file_accepted(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    rep = _resolve(repo, root, [_dep("a", "a.txt")])
    assert rep["overall_accepted"] is True and rep["reason_code"] == R.ACCEPTED
    assert rep["results"][0]["reason_code"] == R.ACCEPTED
    assert rep["closure_digest"].startswith("sha256:")


def test_pos_full_closure_accepted(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n", "d/b.json": "{}\n", "s.py": "x=1\n"})
    deps = [_dep("a", "a.txt"), _dep("b", "d/b.json"), _dep("s", "s.py")]
    rep = _resolve(repo, root, deps)
    assert rep["overall_accepted"] is True
    assert rep["accepted_count"] == 3 and rep["rejected_count"] == 0


def test_pos_repository_identity_bound(tmp_path):
    repo, root, head = _init_repo(tmp_path, {"a.txt": "a\n"})
    rep = _resolve(repo, root, [_dep("a", "a.txt")])
    assert rep["repository"]["root_commit"] == root and rep["head_commit"] == head


def test_pos_optional_missing_dependency_ok(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    rep = _resolve(repo, root, [_dep("a", "a.txt"), _dep("opt", "missing.txt", required=False)])
    assert rep["overall_accepted"] is True          # optional failure does not fail the aggregate
    assert _reason_of(rep, "opt") == R.DEPENDENCY_MISSING


def test_pos_deterministic_and_reorder_invariant(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n", "b.txt": "b\n"})
    r1 = _resolve(repo, root, [_dep("a", "a.txt"), _dep("b", "b.txt")])
    r2 = _resolve(repo, root, [_dep("b", "b.txt"), _dep("a", "a.txt")])   # reordered
    assert r1["closure_digest"] == r2["closure_digest"]                   # order-invariant
    assert r1["overall_accepted"] and r2["overall_accepted"]


def test_pos_closure_digest_excludes_volatile_metadata(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    r1 = R.GitDependencyResolver(str(repo), clock=lambda: "2026-07-16T00:00:00Z").build_resolution_report(
        _manifest(repo, root, [_dep("a", "a.txt")]))
    r2 = R.GitDependencyResolver(str(repo), clock=lambda: "2099-01-01T00:00:00Z").build_resolution_report(
        _manifest(repo, root, [_dep("a", "a.txt")]))
    assert r1["closure_digest"] == r2["closure_digest"]                  # clock excluded from digest
    assert r1["generated_at"] != r2["generated_at"]


# =====================================================================================
# NEGATIVE MATRIX (§27) — every dirty/substitution/ambiguous state fails closed
# =====================================================================================
def test_neg_staged_modification(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    (repo / "a.txt").write_text("staged\n"); _git(repo, "add", "a.txt")
    rep = _resolve(repo, root, [_dep("a", "a.txt")])
    assert rep["overall_accepted"] is False
    assert _reason_of(rep, "a") == R.DEPENDENCY_STAGED_MODIFICATION


def test_neg_unstaged_modification(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    (repo / "a.txt").write_text("changed\n")
    assert _reason_of(_resolve(repo, root, [_dep("a", "a.txt")]), "a") == R.DEPENDENCY_WORKTREE_MODIFICATION


def test_neg_staged_and_unstaged(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    (repo / "a.txt").write_text("staged\n"); _git(repo, "add", "a.txt")
    (repo / "a.txt").write_text("then-unstaged\n")
    # index differs from HEAD → staged modification detected (fail closed either way)
    assert _resolve(repo, root, [_dep("a", "a.txt")])["overall_accepted"] is False


def test_neg_deleted(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    os.remove(repo / "a.txt")
    assert _reason_of(_resolve(repo, root, [_dep("a", "a.txt")]), "a") == R.DEPENDENCY_DELETED


def test_neg_renamed(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n", "pad.txt": "x" * 200})
    _git(repo, "mv", "a.txt", "b.txt")
    code = _reason_of(_resolve(repo, root, [_dep("a", "a.txt")]), "a")
    assert code in (R.DEPENDENCY_RENAMED, R.DEPENDENCY_DELETED)   # rename detection is git-config dependent


def test_neg_missing_required(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    assert _reason_of(_resolve(repo, root, [_dep("m", "missing.txt")]), "m") == R.DEPENDENCY_MISSING


def test_neg_untracked_required(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    (repo / "u.txt").write_text("u\n")
    assert _reason_of(_resolve(repo, root, [_dep("u", "u.txt")]), "u") == R.DEPENDENCY_UNTRACKED


def test_neg_untracked_replacement_after_delete(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    _git(repo, "rm", "-q", "a.txt")
    (repo / "a.txt").write_text("substituted-untracked\n")   # deleted-then-recreated untracked
    assert _resolve(repo, root, [_dep("a", "a.txt")])["overall_accepted"] is False


def test_neg_ignored_dependency(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n", ".gitignore": "ig.txt\n"})
    (repo / "ig.txt").write_text("ignored\n")
    assert _reason_of(_resolve(repo, root, [_dep("ig", "ig.txt")]), "ig") == R.DEPENDENCY_UNTRACKED


def test_neg_mode_change_via_expected_mode(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    assert _reason_of(_resolve(repo, root, [_dep("a", "a.txt", expected_mode="100755")]),
                      "a") == R.DEPENDENCY_MODE_CHANGED


def test_neg_object_type_tree(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"d/a.txt": "a\n"})
    assert _reason_of(_resolve(repo, root, [_dep("d", "d")]), "d") == R.DEPENDENCY_OBJECT_TYPE_MISMATCH


def test_neg_blob_pin_mismatch(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    bad = "0" * 40
    assert _reason_of(_resolve(repo, root, [_dep("a", "a.txt", expected_blob_sha=bad)]),
                      "a") == R.DEPENDENCY_BLOB_MISMATCH


@pytest.mark.parametrize("bad", ["/etc/passwd", "../x", "a\x00b", "a\\b"])
def test_neg_path_invalid(tmp_path, bad):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    assert _reason_of(_resolve(repo, root, [_dep("p", bad)]), "p") == R.DEPENDENCY_PATH_INVALID


def test_neg_case_variant_path_rejected(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"Case.txt": "a\n"})
    # different case on a case-sensitive FS → not tracked at HEAD → missing
    assert _resolve(repo, root, [_dep("c", "case.txt")])["overall_accepted"] is False


def test_neg_symlink_unexpected(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"target.txt": "t\n"})
    os.symlink("target.txt", repo / "link.txt"); _git(repo, "add", "link.txt")
    _git(repo, "commit", "-q", "-m", "link")
    assert _reason_of(_resolve(repo, root, [_dep("l", "link.txt")]), "l") == R.DEPENDENCY_SYMLINK_UNEXPECTED


def test_neg_symlink_escape(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    os.symlink("/etc/hosts", repo / "out.txt"); _git(repo, "add", "out.txt")
    _git(repo, "commit", "-q", "-m", "escape")
    assert _reason_of(_resolve(repo, root, [_dep("o", "out.txt", allow_symlink=True)]),
                      "o") == R.DEPENDENCY_SYMLINK_ESCAPE


def test_neg_symlink_broken(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    os.symlink("nonexistent-xyz", repo / "brk.txt"); _git(repo, "add", "brk.txt")
    _git(repo, "commit", "-q", "-m", "broken")
    assert _resolve(repo, root, [_dep("b", "brk.txt", allow_symlink=True)])["overall_accepted"] is False


def test_neg_assume_unchanged(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    _git(repo, "update-index", "--assume-unchanged", "a.txt")
    assert _reason_of(_resolve(repo, root, [_dep("a", "a.txt")]), "a") == R.DEPENDENCY_ASSUME_UNCHANGED


def test_neg_skip_worktree(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    _git(repo, "update-index", "--skip-worktree", "a.txt")
    assert _reason_of(_resolve(repo, root, [_dep("a", "a.txt")]), "a") == R.DEPENDENCY_SKIP_WORKTREE


def test_neg_lfs_pointer_without_object(tmp_path):
    ptr = "version https://git-lfs.github.com/spec/v1\noid sha256:" + "a" * 64 + "\nsize 12\n"
    repo, root, _ = _init_repo(tmp_path, {"big.bin": ptr})
    assert _reason_of(_resolve(repo, root, [_dep("big", "big.bin")]), "big") == R.DEPENDENCY_LFS_UNAVAILABLE


def test_neg_lfs_pointer_malformed(tmp_path):
    ptr = "version https://git-lfs.github.com/spec/v1\nNO-OID\n"
    repo, root, _ = _init_repo(tmp_path, {"big.bin": ptr})
    assert _resolve(repo, root, [_dep("big", "big.bin")])["overall_accepted"] is False


def test_neg_digest_failure_fails_closed(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    def boom(_):
        raise RuntimeError("digest boom")
    assert _reason_of(_resolve(repo, root, [_dep("a", "a.txt")], digest_fn=boom),
                      "a") == R.DEPENDENCY_DIGEST_FAILED


def test_neg_repository_not_found(tmp_path):
    nongit = tmp_path / "plain"; nongit.mkdir(); (nongit / "a.txt").write_text("a\n")
    man = {"manifest_version": MV,
           "expected_repository": {"canonical_name": "plain", "identity_policy": "toplevel_only"},
           "dependencies": [_dep("a", "a.txt")]}
    rep = R.GitDependencyResolver(str(nongit)).build_resolution_report(man)
    assert rep["overall_accepted"] is False and rep["reason_code"] == R.GIT_REPOSITORY_NOT_FOUND


def test_neg_repository_mismatch_wrong_root(tmp_path):
    repo, _, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    man = _manifest(repo, "f" * 40, [_dep("a", "a.txt")])   # wrong root commit
    assert R.GitDependencyResolver(str(repo)).build_resolution_report(man)["reason_code"] == \
        R.GIT_REPOSITORY_MISMATCH


def test_neg_head_unresolved_empty_repo(tmp_path):
    empty = tmp_path / "empty"; empty.mkdir()
    _git(empty, "init", "-q")
    man = {"manifest_version": MV,
           "expected_repository": {"canonical_name": "empty", "identity_policy": "toplevel_only"},
           "dependencies": [_dep("a", "a.txt")]}
    rep = R.GitDependencyResolver(str(empty)).build_resolution_report(man)
    assert rep["overall_accepted"] is False and rep["reason_code"] == R.GIT_HEAD_UNRESOLVED


def test_neg_manifest_invalid():
    res = R.GitDependencyResolver(str(REPO))
    for bad in [{}, {"manifest_version": "wrong"}, {"manifest_version": MV, "dependencies": []},
                {"manifest_version": MV, "dependencies": [{"id": "x"}, {"id": "x"}]}]:
        rep = res.build_resolution_report(bad)
        assert rep["overall_accepted"] is False and rep["reason_code"] == R.DEPENDENCY_MANIFEST_INVALID


def test_neg_git_command_failed_fakegit():
    fg = FakeGit({}, raise_on={("rev-parse", "--show-toplevel"): R.GitError(R.GIT_COMMAND_FAILED, "boom")})
    man = {"manifest_version": MV, "expected_repository": {"canonical_name": "x",
           "identity_policy": "toplevel_only"}, "dependencies": [_dep("a", "a.txt")]}
    rep = R.GitDependencyResolver("/x", git=fg).build_resolution_report(man)
    assert rep["overall_accepted"] is False and rep["reason_code"] == R.GIT_REPOSITORY_NOT_FOUND


def test_neg_git_command_failed_during_inspection():
    # identity/head/status succeed; ls-tree fails mid-inspection → that dependency fails closed
    fg = FakeGit({("rev-parse", "--show-toplevel"): b"/x\n",
                  ("rev-list", "--max-parents=0", "HEAD"): b"abc\n",
                  ("rev-parse", "HEAD"): b"headsha\n",
                  ("rev-parse", "--is-shallow-repository"): b"false\n",
                  ("status",): b""},
                 raise_on={("ls-tree",): R.GitError(R.GIT_COMMAND_FAILED, "ls-tree boom")})
    man = {"manifest_version": MV, "expected_repository": {"canonical_name": "x", "root_commit": "abc",
           "identity_policy": "root_commit_and_name"}, "dependencies": [_dep("a", "a.txt")]}
    rep = R.GitDependencyResolver("/x", git=fg).build_resolution_report(man)
    assert _reason_of(rep, "a") == R.GIT_COMMAND_FAILED and rep["overall_accepted"] is False


def test_neg_git_command_timeout_fakegit():
    fg = FakeGit({}, raise_on={("rev-parse", "--show-toplevel"):
                               R.GitError(R.GIT_COMMAND_TIMEOUT, "slow")})
    man = {"manifest_version": MV, "expected_repository": {"canonical_name": "x",
           "identity_policy": "toplevel_only"}, "dependencies": [_dep("a", "a.txt")]}
    rep = R.GitDependencyResolver("/x", git=fg).build_resolution_report(man)
    assert rep["reason_code"] == R.GIT_COMMAND_TIMEOUT


def test_neg_shallow_history_insufficient_fakegit():
    fg = FakeGit({("rev-parse", "--show-toplevel"): b"/x\n",
                  ("rev-list", "--max-parents=0", "HEAD"): b"abc\n",
                  ("rev-parse", "HEAD"): b"headsha\n",
                  ("rev-parse", "--is-shallow-repository"): b"true\n"})
    man = {"manifest_version": MV, "expected_repository": {"canonical_name": "x", "root_commit": "abc",
           "identity_policy": "root_commit_and_name"},
           "dependencies": [_dep("a", "a.txt", provenance_requires_history=True)]}
    rep = R.GitDependencyResolver("/x", git=fg).build_resolution_report(man)
    assert rep["reason_code"] == R.GIT_HISTORY_INSUFFICIENT


def test_neg_submodule_mismatch_fakegit():
    # ls-tree returns a gitlink (type commit); no submodule policy → mismatch
    ls = b"160000 commit deadbeef" + b"\t" + b"sub\x00"
    fg = FakeGit({("rev-parse", "--show-toplevel"): b"/x\n",
                  ("rev-list", "--max-parents=0", "HEAD"): b"abc\n",
                  ("rev-parse", "HEAD"): b"headsha\n",
                  ("rev-parse", "--is-shallow-repository"): b"false\n",
                  ("status",): b"",
                  ("ls-tree", "-z", "HEAD", "--", "sub"): ls,
                  ("ls-files", "-s", "-z", "--", "sub"): b"",
                  ("ls-files", "-v", "-z", "--", "sub"): b""})
    man = {"manifest_version": MV, "expected_repository": {"canonical_name": "x", "root_commit": "abc",
           "identity_policy": "root_commit_and_name"}, "dependencies": [_dep("sub", "sub")]}
    rep = R.GitDependencyResolver("/x", git=fg).build_resolution_report(man)
    assert _reason_of(rep, "sub") == R.DEPENDENCY_SUBMODULE_MISMATCH


def test_neg_manifest_omits_mandatory_dependency_is_caller_visible(tmp_path):
    # A manifest that lists FEWER deps than the closure still resolves what it lists; completeness is the
    # manifest author's responsibility — the resolver reports exactly its declared closure count.
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n", "b.txt": "b\n"})
    rep = _resolve(repo, root, [_dep("a", "a.txt")])
    assert rep["dependency_count"] == 1     # b.txt omission is visible as count, not a silent pass of all


# =====================================================================================
# REPORT-BINDING (§21, §24) — repo/head/closure/stale/fixture
# =====================================================================================
def test_binding_head_mismatch(tmp_path):
    repo, root, head = _init_repo(tmp_path, {"a.txt": "a\n"})
    rep = _resolve(repo, root, [_dep("a", "a.txt")])
    ok, code = R.report_binding_ok(rep, expected_head="deadbeef")
    assert ok is False and code == R.REPORT_HEAD_MISMATCH


def test_binding_closure_digest_mismatch_is_stale(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    rep = _resolve(repo, root, [_dep("a", "a.txt")])
    ok, code = R.report_binding_ok(rep, expected_closure_digest="sha256:" + "0" * 64)
    assert ok is False and code == R.REPORT_CLOSURE_DIGEST_MISMATCH


def test_binding_fixture_resolver_rejected(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    rep = R.GitDependencyResolver(str(repo), resolver_id=R.FIXTURE_RESOLVER_ID).build_resolution_report(
        _manifest(repo, root, [_dep("a", "a.txt")]))
    ok, code = R.report_binding_ok(rep)
    assert ok is False and code == R.RESOLVER_FIXTURE_IN_PROTECTED


def test_binding_unavailable_on_non_dict():
    ok, code = R.report_binding_ok(None)
    assert ok is False and code == R.RESOLVER_UNAVAILABLE


def test_binding_repo_mismatch(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    rep = _resolve(repo, root, [_dep("a", "a.txt")])
    ok, code = R.report_binding_ok(rep, expected_repo="/some/other/repo")
    assert ok is False and code == R.REPORT_REPO_MISMATCH


# =====================================================================================
# PROVIDER INTEGRATION (§28) — resolver report gates preflight; capture always blocked
# =====================================================================================
def _clean_resolver_adapter(tmp_path, **kw):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    res = R.GitDependencyResolver(str(repo))
    man = _manifest(repo, root, [_dep("a", "a.txt")])
    return R.provider_tree_state(res, man, **kw), res, man, repo


def test_integration_clean_report_permits_preflight_capture_blocked(tmp_path):
    ts, *_ = _clean_resolver_adapter(tmp_path)
    p = prov.H8EvidenceProvider(mode="preflight", clock=lambda: CLK, tree_state=ts)
    r = p.emit_evidence("sfork_00", kind="both")
    assert r["provider_code"] == prov.PROVIDER_OK_PREFLIGHT and r["ok"] is True
    # resolution digest threaded into provenance
    env = r["evidence"]["render_valid"]
    assert env["provenance"]["dependency_resolution_digest"].startswith("sha256:")
    # a preflight document NEVER authorises capture
    cap, meta = prov.preflight_satisfies_capture_gate(env, review_time="2026-07-16T12:30:00Z",
                                                      expected={k: env["subject"][k]
                                                                for k in es._SUBJECT_COMMON})
    assert cap is False and meta["is_valid_document"] is True


def _dirty_adapter(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    (repo / "a.txt").write_text("dirty\n")            # unstaged modification
    return R.provider_tree_state(R.GitDependencyResolver(str(repo)),
                                 _manifest(repo, root, [_dep("a", "a.txt")]))


def test_integration_dirty_blocks_provider_no_output(tmp_path):
    sink = prov.InMemorySink()
    p = prov.H8EvidenceProvider(mode="preflight", clock=lambda: CLK,
                                tree_state=_dirty_adapter(tmp_path), sink=sink)
    r = p.emit_evidence("sfork_00")
    assert r["provider_code"] == prov.PROVIDER_DIRTY_TREE and r["ok"] is False
    assert sink.atomic_ops == 0 and sink.store == {}


def test_integration_resolver_crash_blocks(tmp_path):
    class Boom:
        def build_resolution_report(self, *_a, **_k):
            raise RuntimeError("resolver down")
    ts = R.provider_tree_state(Boom(), {"manifest_version": MV})
    p = prov.H8EvidenceProvider(mode="preflight", clock=lambda: CLK, tree_state=ts)
    assert p.emit_evidence("sfork_00")["provider_code"] == prov.PROVIDER_DIRTY_TREE


def test_integration_fixture_resolver_blocks_in_protected(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    res = R.GitDependencyResolver(str(repo), resolver_id=R.FIXTURE_RESOLVER_ID)
    ts = R.provider_tree_state(res, _manifest(repo, root, [_dep("a", "a.txt")]))
    p = prov.H8EvidenceProvider(mode="preflight", clock=lambda: CLK, tree_state=ts)
    assert p.emit_evidence("sfork_00")["provider_code"] == prov.PROVIDER_DIRTY_TREE


def test_integration_head_mismatch_blocks(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    ts = R.provider_tree_state(R.GitDependencyResolver(str(repo)),
                               _manifest(repo, root, [_dep("a", "a.txt")]),
                               expected_head="deadbeef")
    p = prov.H8EvidenceProvider(mode="preflight", clock=lambda: CLK, tree_state=ts)
    assert p.emit_evidence("sfork_00")["provider_code"] == prov.PROVIDER_DIRTY_TREE


def test_integration_stale_closure_digest_blocks(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    ts = R.provider_tree_state(R.GitDependencyResolver(str(repo)),
                               _manifest(repo, root, [_dep("a", "a.txt")]),
                               expected_closure_digest="sha256:" + "0" * 64)
    p = prov.H8EvidenceProvider(mode="preflight", clock=lambda: CLK, tree_state=ts)
    assert p.emit_evidence("sfork_00")["provider_code"] == prov.PROVIDER_DIRTY_TREE


def test_integration_backend_never_invoked_on_block(tmp_path):
    # the provider has NO capture_backend in preflight; a blocked case creates nothing
    sink = prov.InMemorySink()
    prov.H8EvidenceProvider(mode="preflight", clock=lambda: CLK,
                            tree_state=_dirty_adapter(tmp_path), sink=sink).emit_evidence("sfork_00")
    assert sink.atomic_ops == 0


# =====================================================================================
# TAXONOMY / TRUST IDENTITY
# =====================================================================================
def test_reason_code_taxonomy_split():
    assert R.REPORT_STALE in R.RESERVED_CODES
    assert R.RESERVED_CODES.issubset(R.REASON_CODES)
    assert R.ACTIVE_CODES == R.REASON_CODES - R.RESERVED_CODES
    assert R.ACCEPTED in R.ACTIVE_CODES


def test_resolver_trust_identity():
    assert R.RESOLVER_ID in R.APPROVED_RESOLVER_IDS
    assert R.FIXTURE_RESOLVER_ID not in R.APPROVED_RESOLVER_IDS


def test_real_manifest_file_is_valid_schema_shape():
    import json
    man = json.loads((REPO / "configs/gnm/h8_dependency_manifest.json").read_text())
    assert man["manifest_version"] in R.SUPPORTED_MANIFEST_VERSIONS
    ids = [d["id"] for d in man["dependencies"]]
    assert len(ids) == len(set(ids)) and all(d["path"] for d in man["dependencies"])
    # the resolver can LOAD the shipped manifest without error
    R.GitDependencyResolver(str(REPO)).load_dependency_manifest(man)
