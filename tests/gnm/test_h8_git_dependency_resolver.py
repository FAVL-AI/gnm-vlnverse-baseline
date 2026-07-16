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


# =====================================================================================
# G1R REMEDIATION (H8-G1REV-F-001 / -F-002 / -F-003) — trust-boundary hardening
# A canonical fixture repo self-lists its manifest at CANONICAL_MANIFEST_REL and carries every
# mandatory dependency id, so resolve_canonical / trusted_provider_tree_state can be exercised end to end.
# =====================================================================================
import json as _json  # noqa: E402

# id -> repo-relative path for a self-consistent canonical fixture (manifest self-lists at the canonical rel)
_CANON_PATHS = {
    "h8-dataset-config": "configs/gnm/dataset.json",
    "h8-evidence-schema": "scripts/gnm/schema.py",
    "h8-evidence-provider": "scripts/gnm/provider.py",
    "h8-recorded-mode": "scripts/gnm/recorded.py",
    "h8-drive-validate": "scripts/gnm/drive.py",
    "h8-scene-usda": "assets/scene.usda",
    "h8-evidence-schema-json": "docs/schema.json",
    "h8-resolver": "scripts/gnm/resolver.py",
    "h8-manifest-schema": "docs/manifest.schema.json",
    "h8-dependency-manifest": R.CANONICAL_MANIFEST_REL,
}


_UNSET = object()


def _canonical_repo(tmp_path, *, drop=None, self_path=None, required_overrides=None, dup_id=None):
    """Build a temp repo whose canonical manifest self-lists at CANONICAL_MANIFEST_REL and covers every
    mandatory id. `drop` removes one dependency id (MANIFEST_INCOMPLETE); `self_path` overrides the
    manifest-self dependency path (MANIFEST_NOT_CANONICAL); `required_overrides` maps id → replacement value
    for `required` (use `_UNSET` to omit the key entirely — G1R2 required-flag tests); `dup_id` appends a
    duplicate entry for that id (G1R2 duplicate test)."""
    required_overrides = required_overrides or {}
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "frankleroyvan@gmail.com")
    _git(repo, "config", "user.name", "Frank Asante Van Laarhoven")
    deps = []
    for id_, rel in _CANON_PATHS.items():
        if drop and id_ == drop:
            continue
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if rel.endswith(".json"):
            p.write_text("{}\n")
        elif rel.endswith(".usda"):
            p.write_text("#usda 1.0\n")
        else:
            p.write_text("x = 1\n")
        path = self_path if (id_ == "h8-dependency-manifest" and self_path) else rel
        entry = {"id": id_, "path": path, "type": "file", "required": True}
        if id_ in required_overrides:
            if required_overrides[id_] is _UNSET:
                entry.pop("required")
            else:
                entry["required"] = required_overrides[id_]
        deps.append(entry)
        if dup_id and id_ == dup_id:
            deps.append(dict(entry))
    canon = repo / R.CANONICAL_MANIFEST_REL

    def _write_manifest(root):
        man = {"manifest_version": MV,
               "expected_repository": {"canonical_name": repo.name, "root_commit": root,
                                       "identity_policy": "root_commit_and_name"},
               "dependencies": deps}
        canon.write_text(_json.dumps(man, indent=2) + "\n")

    _write_manifest(None)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    root = subprocess.run(["git", "-C", str(repo), "rev-list", "--max-parents=0", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    _write_manifest(root)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "pin root")
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    return repo, root, head


# ── F-001: report authentication + trusted construction ─────────────────────────────
def test_g1r_forged_report_without_marker_rejected():
    # An ordinary caller-forged dict with the APPROVED resolver id + overall_accepted True but NO
    # in-process authenticity marker is now rejected (this was the F-001 bypass).
    forged = {"resolver_id": R.RESOLVER_ID, "overall_accepted": True, "closure_digest": "sha256:" + "0" * 64}
    ok, code = R.report_binding_ok(forged)
    assert ok is False and code == R.REPORT_UNAUTHENTIC


def test_g1r_genuine_report_carries_authenticity_marker(tmp_path):
    repo, root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    rep = _resolve(repo, root, [_dep("a", "a.txt")])
    assert rep["authenticity"] == R._REPORT_AUTHENTICITY
    ok, code = R.report_binding_ok(rep)
    assert ok is True and code == R.ACCEPTED           # genuine report still accepted — not reject-all


def test_g1r_module_access_forgery_is_documented_residual():
    # HONEST residual: code WITH module access can copy the marker constant; in-process authentication is
    # NOT cryptographic. Full authentication is deferred to G2. The primary control is that protected
    # callers use trusted_provider_tree_state (which never accepts a caller report at all).
    forged = {"resolver_id": R.RESOLVER_ID, "overall_accepted": True,
              "authenticity": R._REPORT_AUTHENTICITY}
    ok, _code = R.report_binding_ok(forged)
    assert ok is True                                  # documents the residual, does not hide it


def test_g1r_trusted_factory_has_no_report_or_manifest_injection():
    import inspect
    params = set(inspect.signature(R.trusted_provider_tree_state).parameters)
    # structurally NO way to inject a fabricated resolution, report, manifest, or assume-clean flag
    for forbidden in ("resolver", "report", "manifest", "assume_clean", "tree_state"):
        assert forbidden not in params


def test_g1r_trusted_factory_clean_canonical_accepts(tmp_path):
    repo, _root, head = _canonical_repo(tmp_path)
    ts = R.trusted_provider_tree_state(str(repo))()
    assert ts["dependency_dirty"] is False and ts["resolution_reason"] == R.ACCEPTED
    assert ts["commit"] == head
    assert ts["resolution"]["canonical_manifest"] == R.CANONICAL_MANIFEST_REL


def test_g1r_trusted_factory_dirty_canonical_blocks(tmp_path):
    repo, _root, _ = _canonical_repo(tmp_path)
    (repo / "scripts/gnm/resolver.py").write_text("x = 2  # tamper\n")   # worktree modification
    ts = R.trusted_provider_tree_state(str(repo))()
    assert ts["dependency_dirty"] is True
    assert R.DEPENDENCY_WORKTREE_MODIFICATION in (ts["resolution"]["failures"] or [])


# ── F-002: canonical-manifest enforcement ───────────────────────────────────────────
def test_g1r_canonical_missing_mandatory_id_incomplete(tmp_path):
    repo, _root, _ = _canonical_repo(tmp_path, drop="h8-resolver")
    rep = R.GitDependencyResolver(str(repo)).resolve_canonical()
    assert rep["overall_accepted"] is False and rep["reason_code"] == R.MANIFEST_INCOMPLETE


def test_g1r_canonical_manifest_must_self_list_at_canonical_path(tmp_path):
    # manifest-self dependency points somewhere other than the canonical rel → rejected
    repo, _root, _ = _canonical_repo(tmp_path, self_path="configs/gnm/other_manifest.json")
    rep = R.GitDependencyResolver(str(repo)).resolve_canonical()
    assert rep["overall_accepted"] is False and rep["reason_code"] == R.MANIFEST_NOT_CANONICAL


def test_g1r_canonical_tampered_manifest_file_blocks(tmp_path):
    # editing the canonical manifest file in the worktree makes the manifest-self dependency dirty
    repo, _root, _ = _canonical_repo(tmp_path)
    man = _json.loads((repo / R.CANONICAL_MANIFEST_REL).read_text())
    man["dependencies"].append({"id": "h8-extra", "path": "scripts/gnm/schema.py", "type": "file",
                                "required": True})
    (repo / R.CANONICAL_MANIFEST_REL).write_text(_json.dumps(man, indent=2) + "\n")
    rep = R.GitDependencyResolver(str(repo)).resolve_canonical()
    assert rep["overall_accepted"] is False
    self_res = next(r for r in rep["results"] if r["dependency_id"] == "h8-dependency-manifest")
    assert self_res["accepted"] is False


def test_g1r_canonical_missing_file_fails_closed(tmp_path):
    repo, _root, _ = _canonical_repo(tmp_path)
    # canonical manifest present, but a required tracked dependency file removed from the worktree
    (repo / "assets/scene.usda").unlink()
    rep = R.GitDependencyResolver(str(repo)).resolve_canonical()
    assert rep["overall_accepted"] is False


def test_g1r_provider_uses_trusted_factory_clean_permits_preflight(tmp_path):
    repo, _root, _ = _canonical_repo(tmp_path)
    ts = R.trusted_provider_tree_state(str(repo))
    p = prov.H8EvidenceProvider(mode="preflight", clock=lambda: CLK, tree_state=ts)
    r = p.emit_evidence("sfork_00", kind="both")
    assert r["provider_code"] == prov.PROVIDER_OK_PREFLIGHT and r["ok"] is True
    env = r["evidence"]["render_valid"]
    assert env["provenance"]["dependency_resolution_digest"].startswith("sha256:")


def test_g1r_provider_uses_trusted_factory_dirty_blocks(tmp_path):
    repo, _root, _ = _canonical_repo(tmp_path)
    (repo / "scripts/gnm/provider.py").write_text("x = 2  # tamper\n")
    sink = prov.InMemorySink()
    p = prov.H8EvidenceProvider(mode="preflight", clock=lambda: CLK,
                                tree_state=R.trusted_provider_tree_state(str(repo)), sink=sink)
    r = p.emit_evidence("sfork_00")
    assert r["provider_code"] == prov.PROVIDER_DIRTY_TREE and sink.atomic_ops == 0


# ── F-003: git-config neutralisation + object-identity substitution ─────────────────
def test_g1r_safe_overrides_are_pinned():
    ov = R._GIT_SAFE_OVERRIDES
    for pair in ("core.fileMode=true", "core.symlinks=true", "core.ignorecase=false",
                 "core.autocrlf=false"):
        assert pair in ov
    assert "--no-replace-objects" in ov


def test_g1r_local_filemode_false_does_not_mask_mode_change(tmp_path):
    # repo sets core.fileMode=false locally; a chmod +x on a tracked file would normally be hidden.
    # The pinned override forces detection → the dependency is NOT accepted.
    repo, root, _ = _init_repo(tmp_path, {"s.sh": "echo hi\n"})
    _git(repo, "config", "core.fileMode", "false")
    os.chmod(repo / "s.sh", 0o755)
    rep = _resolve(repo, root, [_dep("s", "s.sh")])
    res = rep["results"][0]
    assert res["accepted"] is False
    assert res["reason_code"] in (R.DEPENDENCY_MODE_CHANGED, R.DEPENDENCY_WORKTREE_MODIFICATION)


def test_g1r_replace_objects_rejected(tmp_path):
    repo, _root, head = _init_repo(tmp_path, {"a.txt": "a\n"})
    _git(repo, "update-ref", f"refs/replace/{head}", head)   # a replace ref exists
    ok, code, _why = R.GitDependencyResolver(str(repo)).inspect_git_config()
    assert ok is False and code == R.GIT_REPLACE_OBJECTS
    rep = R.GitDependencyResolver(str(repo)).resolve_canonical()
    assert rep["overall_accepted"] is False and rep["reason_code"] == R.GIT_REPLACE_OBJECTS


def test_g1r_alternate_object_db_rejected(tmp_path):
    repo, _root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    gdir = subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-dir"],
                          capture_output=True, text=True).stdout.strip()
    gdir = gdir if os.path.isabs(gdir) else os.path.join(str(repo), gdir)
    info = Path(gdir) / "objects" / "info"
    info.mkdir(parents=True, exist_ok=True)
    (info / "alternates").write_text("/some/other/objects\n")
    ok, code, _why = R.GitDependencyResolver(str(repo)).inspect_git_config()
    assert ok is False and code == R.GIT_ALTERNATE_OBJECTS


def test_g1r_clean_repo_passes_git_config_inspection(tmp_path):
    repo, _root, _ = _init_repo(tmp_path, {"a.txt": "a\n"})
    ok, code, _why = R.GitDependencyResolver(str(repo)).inspect_git_config()
    assert ok is True and code == R.ACCEPTED           # inspection is not reject-all


# ── taxonomy / constants ─────────────────────────────────────────────────────────────
def test_g1r_new_reason_codes_registered():
    for c in (R.REPORT_UNAUTHENTIC, R.MANIFEST_NOT_CANONICAL, R.MANIFEST_INCOMPLETE,
              R.GIT_CONFIG_UNSUPPORTED, R.GIT_REPLACE_OBJECTS, R.GIT_ALTERNATE_OBJECTS):
        assert c in R.REASON_CODES and c in R.ACTIVE_CODES


def test_g1r_canonical_constants_bind_shipped_manifest():
    assert R.CANONICAL_MANIFEST_REL == "configs/gnm/h8_dependency_manifest.json"
    man = _json.loads((REPO / R.CANONICAL_MANIFEST_REL).read_text())
    ids = {d["id"] for d in man["dependencies"]}
    # every machine-enforced mandatory id is present in the SHIPPED canonical manifest
    assert R.REQUIRED_DEPENDENCY_IDS.issubset(ids)
    # the shipped manifest self-lists at the canonical path
    self_dep = next(d for d in man["dependencies"] if d["id"] == "h8-dependency-manifest")
    assert self_dep["path"] == R.CANONICAL_MANIFEST_REL


# =====================================================================================
# G1R2 REMEDIATION (H8-G1RREV-F-001 / -F-003) — required-flag + Git-environment hardening
# =====================================================================================
def _rc(repo):
    return R.GitDependencyResolver(str(repo)).resolve_canonical()


# ── F-001: exact `required is True` for mandatory ids (no truthiness coercion) ───────
def test_g1r2_mandatory_required_true_accepted(tmp_path):
    repo, _r, _h = _canonical_repo(tmp_path)                    # baseline: all required True, clean
    assert _rc(repo)["overall_accepted"] is True


@pytest.mark.parametrize("val", [False, _UNSET, None, 0, 1, "true", "false"])
def test_g1r2_mandatory_required_weakened_rejected(tmp_path, val):
    # a mandatory id whose `required` is anything other than exactly True is rejected, even if the file is
    # clean — presence + weakening must never count toward mandatory coverage.
    repo, _r, _h = _canonical_repo(tmp_path, required_overrides={"h8-evidence-provider": val})
    rep = _rc(repo)
    assert rep["overall_accepted"] is False
    assert rep["reason_code"] == R.MANDATORY_DEPENDENCY_NOT_REQUIRED


def test_g1r2_mandatory_required_false_plus_dirty_rejected(tmp_path):
    # the original F-001 exploit: weaken to false AND dirty the file → must now fail closed
    repo, _r, _h = _canonical_repo(tmp_path, required_overrides={"h8-resolver": False})
    (repo / "scripts/gnm/resolver.py").write_text("x = 2  # tamper\n")
    rep = _rc(repo)
    assert rep["overall_accepted"] is False and rep["reason_code"] == R.MANDATORY_DEPENDENCY_NOT_REQUIRED


def test_g1r2_non_mandatory_optional_still_allowed(tmp_path):
    # a NON-mandatory dependency may legitimately be required=false (control is scoped to the mandatory set)
    repo, root, _h = _canonical_repo(tmp_path)
    man = _json.loads((repo / R.CANONICAL_MANIFEST_REL).read_text())
    man["dependencies"].append({"id": "h8-optional-extra", "path": "scripts/gnm/schema.py",
                                "type": "file", "required": False})
    (repo / R.CANONICAL_MANIFEST_REL).write_text(_json.dumps(man, indent=2) + "\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add optional")
    assert _rc(repo)["overall_accepted"] is True


# ── duplicate dependency id ──────────────────────────────────────────────────────────
def test_g1r2_duplicate_mandatory_id_rejected(tmp_path):
    repo, _r, _h = _canonical_repo(tmp_path, dup_id="h8-resolver")
    rep = _rc(repo)
    assert rep["overall_accepted"] is False and rep["reason_code"] == R.MANIFEST_DUPLICATE_DEPENDENCY


def test_g1r2_generic_duplicate_still_manifest_invalid():
    # the generic build_resolution_report path keeps DEPENDENCY_MANIFEST_INVALID for duplicates
    res = R.GitDependencyResolver(str(REPO))
    rep = res.build_resolution_report({"manifest_version": MV, "dependencies": [{"id": "x"}, {"id": "x"}]})
    assert rep["reason_code"] == R.DEPENDENCY_MANIFEST_INVALID


# ── F-003: prohibited GIT_* environment fails closed + is scrubbed from the child ────
_PROHIBITED_ENV = [
    ("GIT_DIR", "/tmp/evil.git"), ("GIT_WORK_TREE", "/tmp/evil-wt"),
    ("GIT_COMMON_DIR", "/tmp/evil-common"), ("GIT_INDEX_FILE", "/tmp/evil-index"),
    ("GIT_OBJECT_DIRECTORY", "/tmp/evil-obj"), ("GIT_ALTERNATE_OBJECT_DIRECTORIES", "/tmp/evil-alt"),
    ("GIT_REPLACE_REF_BASE", "refs/evil"), ("GIT_NAMESPACE", "evil"),
    ("GIT_CONFIG_GLOBAL", "/tmp/evil-cfg"), ("GIT_CONFIG_SYSTEM", "/tmp/evil-sys"),
    ("GIT_CONFIG_COUNT", "1"),
]


@pytest.mark.parametrize("var,val", _PROHIBITED_ENV)
def test_g1r2_prohibited_git_env_fails_closed(tmp_path, monkeypatch, var, val):
    repo, _r, _h = _canonical_repo(tmp_path)
    assert _rc(repo)["overall_accepted"] is True               # clean baseline first
    monkeypatch.setenv(var, val)
    rep = _rc(repo)
    assert rep["overall_accepted"] is False and rep["reason_code"] == R.GIT_ENV_UNSUPPORTED


def test_g1r2_git_config_key_value_injection_rejected(tmp_path, monkeypatch):
    repo, _r, _h = _canonical_repo(tmp_path)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.fileMode")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")
    rep = _rc(repo)
    assert rep["overall_accepted"] is False and rep["reason_code"] == R.GIT_ENV_UNSUPPORTED


def test_g1r2_combined_config_and_env_attack_rejected(tmp_path, monkeypatch):
    repo, _r, _h = _canonical_repo(tmp_path)
    _git(repo, "config", "core.fileMode", "false")             # hostile local config
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/tmp/evil-cfg")   # + hostile global via env
    rep = _rc(repo)
    assert rep["overall_accepted"] is False and rep["reason_code"] == R.GIT_ENV_UNSUPPORTED


def test_g1r2_child_env_scrubbed_behaviourally(tmp_path, monkeypatch):
    # even bypassing the reject, the runner must not let GIT_DIR redirect git to a decoy repository
    real = tmp_path / "real"
    real.mkdir(); _git(real, "init", "-q"); (real / "a.txt").write_text("a\n")
    _git(real, "add", "-A"); _git(real, "commit", "-q", "-m", "i")
    decoy = tmp_path / "decoy"
    decoy.mkdir(); _git(decoy, "init", "-q"); (decoy / "b.txt").write_text("b\n")
    _git(decoy, "add", "-A"); _git(decoy, "commit", "-q", "-m", "i")
    monkeypatch.setenv("GIT_DIR", str(decoy / ".git"))
    out = R.SubprocessGitRunner().run(str(real), ["rev-parse", "--absolute-git-dir"])["out"].decode().strip()
    assert os.path.realpath(out) == os.path.realpath(str(real / ".git"))


def test_g1r2_build_git_env_scrubs_and_forces(monkeypatch):
    monkeypatch.setenv("GIT_DIR", "/x")
    monkeypatch.setenv("GIT_CONFIG_KEY_3", "k")
    env = R._build_git_env()
    assert "GIT_DIR" not in env and "GIT_CONFIG_KEY_3" not in env
    assert env["GIT_CONFIG_NOSYSTEM"] == "1" and env["LC_ALL"] == "C"
    assert env["GIT_CONFIG_GLOBAL"] == os.devnull
    assert "PATH" in env                                       # ordinary vars preserved


def test_g1r2_benign_env_preserves_closure_digest(tmp_path, monkeypatch):
    repo, _r, _h = _canonical_repo(tmp_path)
    d1 = _rc(repo)["closure_digest"]
    monkeypatch.setenv("SOME_BENIGN_VAR", "hello")
    assert _rc(repo)["closure_digest"] == d1                   # benign var neither rejects nor changes state


def test_g1r2_clean_positive_path_still_works(tmp_path):
    # not reject-all: a fully clean canonical repo with a safe environment still ACCEPTS
    repo, _r, head = _canonical_repo(tmp_path)
    ts = R.trusted_provider_tree_state(str(repo))()
    assert ts["dependency_dirty"] is False and ts["resolution_reason"] == R.ACCEPTED and ts["commit"] == head


def test_g1r2_new_reason_codes_registered():
    for c in (R.MANDATORY_DEPENDENCY_NOT_REQUIRED, R.MANIFEST_DUPLICATE_DEPENDENCY, R.GIT_ENV_UNSUPPORTED):
        assert c in R.REASON_CODES and c in R.ACTIVE_CODES


def test_g1r2_env_policy_shape():
    # forced-safe + removed sets are disjoint in intent; prohibited redirection vars are removed too
    assert "GIT_CONFIG_NOSYSTEM" in R._GIT_ENV_FORCE and "LC_ALL" in R._GIT_ENV_FORCE
    for v in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
        assert v in R._GIT_ENV_REMOVE and v in R._GIT_ENV_PROHIBITED


# ── F-002 remains a DOCUMENTED LIMITATION (not silently closed) ──────────────────────
def test_g1r2_path_substitution_remains_documented_limitation(tmp_path):
    # re-pointing a mandatory id's path at another tracked/clean file is still accepted: the resolver binds
    # path+tracked+clean+HEAD, not semantic content identity. Kept explicit so it is not disguised as solved.
    repo, root, _h = _canonical_repo(tmp_path)
    man = _json.loads((repo / R.CANONICAL_MANIFEST_REL).read_text())
    for d in man["dependencies"]:
        if d["id"] == "h8-resolver":
            d["path"] = "scripts/gnm/schema.py"
    (repo / R.CANONICAL_MANIFEST_REL).write_text(_json.dumps(man, indent=2) + "\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "substitute path")
    assert _rc(repo)["overall_accepted"] is True               # documented F-002 residual, deferred to G2
