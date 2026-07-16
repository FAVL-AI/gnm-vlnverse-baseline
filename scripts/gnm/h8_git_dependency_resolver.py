"""scripts/gnm/h8_git_dependency_resolver.py

H8 Git DEPENDENCY RESOLVER (gate G1) — deterministic, fail-closed provenance authority.

Answers, for one H8 evidence decision:

    "Are all files, policies, schemas, plans and artefacts required for this evidence decision present,
     tracked, unmodified, bound to the EXPECTED repository and commit, and free from ambiguous
     substitution?"

BOUNDARY — this module does NOT and CANNOT:
  * launch Isaac Sim / Omniverse Kit, start ROS 2, render, drive, capture, run inference or train;
  * implement the Isaac worker, runtime observers, capture token or dataset writer;
  * AUTHORISE CAPTURE. It produces a structured dependency-resolution REPORT only. A clean report permits
    ONLY non-authorising preflight document generation (via the injected provider seam); it never yields
    runtime-valid evidence and never authorises footage/trajectory collection.

Design: pure/narrowly-side-effect-free. All external effects are injected (Git runner, filesystem reader,
digest function, clock). Git is invoked with ARGUMENT ARRAYS (never shell strings). Any unresolved,
ambiguous, missing, substituted, modified or Git-unavailable MANDATORY dependency fails the aggregate
CLOSED. "Could not inspect" is never treated as clean.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import PurePosixPath

# ── resolver trust identity (§22) ───────────────────────────────────────────────────
RESOLVER_ID = "h8-git-dependency-resolver"
RESOLVER_VERSION = "h8-git-dependency-resolver/1.0.0"
DEPENDENCY_POLICY_VERSION = "h8-dependency-policy/1.0.0"
SUPPORTED_MANIFEST_VERSIONS = frozenset({"h8-dependency-manifest/1.0.0"})
# Only an APPROVED (non-fixture) resolver identity may back a protected provider mode. A fixture resolver
# is rejected in preflight/production (mirrors the positive producer-authorisation design).
APPROVED_RESOLVER_IDS = frozenset({RESOLVER_ID})
FIXTURE_RESOLVER_ID = "h8-fixture-resolver"

# ── stable reason-code taxonomy (§20) ───────────────────────────────────────────────
ACCEPTED = "ACCEPTED"
GIT_REPOSITORY_NOT_FOUND = "GIT_REPOSITORY_NOT_FOUND"
GIT_REPOSITORY_MISMATCH = "GIT_REPOSITORY_MISMATCH"
GIT_COMMAND_FAILED = "GIT_COMMAND_FAILED"
GIT_COMMAND_TIMEOUT = "GIT_COMMAND_TIMEOUT"
GIT_HEAD_UNRESOLVED = "GIT_HEAD_UNRESOLVED"
GIT_HISTORY_INSUFFICIENT = "GIT_HISTORY_INSUFFICIENT"          # shallow/partial where provenance needed
DEPENDENCY_MANIFEST_INVALID = "DEPENDENCY_MANIFEST_INVALID"
DEPENDENCY_PATH_INVALID = "DEPENDENCY_PATH_INVALID"
DEPENDENCY_MISSING = "DEPENDENCY_MISSING"
DEPENDENCY_UNTRACKED = "DEPENDENCY_UNTRACKED"
DEPENDENCY_STAGED_MODIFICATION = "DEPENDENCY_STAGED_MODIFICATION"
DEPENDENCY_WORKTREE_MODIFICATION = "DEPENDENCY_WORKTREE_MODIFICATION"
DEPENDENCY_DELETED = "DEPENDENCY_DELETED"
DEPENDENCY_RENAMED = "DEPENDENCY_RENAMED"
DEPENDENCY_MODE_CHANGED = "DEPENDENCY_MODE_CHANGED"
DEPENDENCY_SYMLINK_UNEXPECTED = "DEPENDENCY_SYMLINK_UNEXPECTED"
DEPENDENCY_SYMLINK_ESCAPE = "DEPENDENCY_SYMLINK_ESCAPE"
DEPENDENCY_OBJECT_TYPE_MISMATCH = "DEPENDENCY_OBJECT_TYPE_MISMATCH"
DEPENDENCY_BLOB_MISMATCH = "DEPENDENCY_BLOB_MISMATCH"
DEPENDENCY_LFS_UNAVAILABLE = "DEPENDENCY_LFS_UNAVAILABLE"
DEPENDENCY_SUBMODULE_MISMATCH = "DEPENDENCY_SUBMODULE_MISMATCH"
DEPENDENCY_SKIP_WORKTREE = "DEPENDENCY_SKIP_WORKTREE"
DEPENDENCY_ASSUME_UNCHANGED = "DEPENDENCY_ASSUME_UNCHANGED"
DEPENDENCY_DIGEST_FAILED = "DEPENDENCY_DIGEST_FAILED"
DEPENDENCY_REQUIRED_UNRESOLVED = "DEPENDENCY_REQUIRED_UNRESOLVED"
# integration-layer report-binding codes (§21/§28) — consumed by the provider adapter
RESOLVER_UNAVAILABLE = "RESOLVER_UNAVAILABLE"
RESOLVER_FIXTURE_IN_PROTECTED = "RESOLVER_FIXTURE_IN_PROTECTED"
REPORT_REPO_MISMATCH = "REPORT_REPO_MISMATCH"
REPORT_HEAD_MISMATCH = "REPORT_HEAD_MISMATCH"
REPORT_CLOSURE_DIGEST_MISMATCH = "REPORT_CLOSURE_DIGEST_MISMATCH"
REPORT_STALE = "REPORT_STALE"
# G1R remediation (H8-G1REV-F-001/-F-002/-F-003)
REPORT_UNAUTHENTIC = "REPORT_UNAUTHENTIC"                 # ordinary caller-forged report (no authenticity marker)
MANIFEST_NOT_CANONICAL = "MANIFEST_NOT_CANONICAL"        # protected mode selected a non-canonical manifest
MANIFEST_INCOMPLETE = "MANIFEST_INCOMPLETE"              # a machine-enforced mandatory dependency id is absent
GIT_CONFIG_UNSUPPORTED = "GIT_CONFIG_UNSUPPORTED"        # security-relevant config in an unsupported state
GIT_REPLACE_OBJECTS = "GIT_REPLACE_OBJECTS"             # refs/replace present — object identity can be forged
GIT_ALTERNATE_OBJECTS = "GIT_ALTERNATE_OBJECTS"        # unapproved alternate object database present

REASON_CODES = frozenset({
    ACCEPTED, GIT_REPOSITORY_NOT_FOUND, GIT_REPOSITORY_MISMATCH, GIT_COMMAND_FAILED, GIT_COMMAND_TIMEOUT,
    GIT_HEAD_UNRESOLVED, GIT_HISTORY_INSUFFICIENT, DEPENDENCY_MANIFEST_INVALID, DEPENDENCY_PATH_INVALID,
    DEPENDENCY_MISSING, DEPENDENCY_UNTRACKED, DEPENDENCY_STAGED_MODIFICATION,
    DEPENDENCY_WORKTREE_MODIFICATION, DEPENDENCY_DELETED, DEPENDENCY_RENAMED, DEPENDENCY_MODE_CHANGED,
    DEPENDENCY_SYMLINK_UNEXPECTED, DEPENDENCY_SYMLINK_ESCAPE, DEPENDENCY_OBJECT_TYPE_MISMATCH,
    DEPENDENCY_BLOB_MISMATCH, DEPENDENCY_LFS_UNAVAILABLE, DEPENDENCY_SUBMODULE_MISMATCH,
    DEPENDENCY_SKIP_WORKTREE, DEPENDENCY_ASSUME_UNCHANGED, DEPENDENCY_DIGEST_FAILED,
    DEPENDENCY_REQUIRED_UNRESOLVED, RESOLVER_UNAVAILABLE, RESOLVER_FIXTURE_IN_PROTECTED,
    REPORT_REPO_MISMATCH, REPORT_HEAD_MISMATCH, REPORT_CLOSURE_DIGEST_MISMATCH, REPORT_STALE,
    REPORT_UNAUTHENTIC, MANIFEST_NOT_CANONICAL, MANIFEST_INCOMPLETE, GIT_CONFIG_UNSUPPORTED,
    GIT_REPLACE_OBJECTS, GIT_ALTERNATE_OBJECTS,
})

# ── G1R: canonical manifest + mandatory dependency set + authenticity marker ────────
# The ONE repository-tracked manifest that protected provider modes may use (H8-G1REV-F-002). Protected
# modes never accept a caller-selected manifest path or an in-memory manifest dict.
CANONICAL_MANIFEST_REL = "configs/gnm/h8_dependency_manifest.json"

# Machine-enforced mandatory dependency IDs (H8-G1REV-F-002). A canonical manifest that omits any of these
# is rejected MANIFEST_INCOMPLETE — a caller cannot silently drop a known decision-critical dependency.
# NOTE: future decision-critical dependencies must be added here when introduced.
REQUIRED_DEPENDENCY_IDS = frozenset({
    "h8-dataset-config", "h8-evidence-schema", "h8-evidence-provider", "h8-recorded-mode",
    "h8-drive-validate", "h8-scene-usda", "h8-evidence-schema-json", "h8-resolver",
    "h8-dependency-manifest", "h8-manifest-schema",
})

# Deterministic security-relevant Git config overrides applied to EVERY protected git invocation so that
# repository-local configuration (H8-G1REV-F-003) cannot mask mode/symlink/case/EOL differences or redirect
# object identity. `--no-replace-objects` neutralises refs/replace substitution at read time.
_GIT_SAFE_OVERRIDES = ("-c", "core.fileMode=true", "-c", "core.symlinks=true", "-c",
                       "core.ignorecase=false", "-c", "core.autocrlf=false", "--no-replace-objects")

# In-process authenticity marker (H8-G1REV-F-001). The genuine resolver stamps this on every report it
# produces; `report_binding_ok` requires it, so an ORDINARY caller-forged dict (no marker) is rejected.
# This is NOT cryptographic: code with module access could copy the constant — cross-process/persisted
# authentication is deferred to G2 signing. The primary control is `trusted_provider_tree_state`, which
# NEVER accepts a caller report and re-resolves current state in-process.
_REPORT_AUTHENTICITY = "h8-resolver-authentic/1.0.0"
# Reserved: `REPORT_STALE` is reserved for a future dedicated time-based staleness path that requires the
# (not-yet-built) trusted clock; stale reports are currently rejected via REPORT_CLOSURE_DIGEST_MISMATCH
# (a content-bound staleness check). Reserved codes are excluded from active-coverage accounting.
RESERVED_CODES = frozenset({REPORT_STALE})
ACTIVE_CODES = REASON_CODES - RESERVED_CODES


# ── injected Git runner (argument arrays, no shell) ─────────────────────────────────
class GitError(Exception):
    def __init__(self, code, detail=""):
        super().__init__(detail)
        self.code = code
        self.detail = detail


class SubprocessGitRunner:
    """Default Git runner: runs `git -C <repo> <args...>` with a timeout, no shell, capturing rc/out/err.
    Raises GitError(GIT_COMMAND_TIMEOUT/GIT_COMMAND_FAILED) rather than ever returning an ambiguous state."""

    def __init__(self, timeout_s=15.0, git_bin="git"):
        self.timeout_s = float(timeout_s)
        self.git_bin = git_bin

    def run(self, repo_root, args, *, check=True):
        if not isinstance(args, (list, tuple)) or any(not isinstance(a, str) for a in args):
            raise GitError(GIT_COMMAND_FAILED, "git args must be a list of strings (no shell)")
        # G1R (H8-G1REV-F-003): pin security-relevant config on every invocation and neutralise
        # refs/replace so repository-local settings cannot mask mode/symlink/case/EOL differences or
        # redirect object identity. Overrides precede the subcommand as required by git's option grammar.
        cmd = [self.git_bin, "-C", str(repo_root), *_GIT_SAFE_OVERRIDES, *args]
        # Force a deterministic C locale so porcelain/plumbing text is machine-stable across hosts.
        env = dict(os.environ)
        env["LC_ALL"] = "C"
        env["LANG"] = "C"
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=self.timeout_s, check=False,  # noqa: S603
                               env=env)
        except subprocess.TimeoutExpired as e:
            raise GitError(GIT_COMMAND_TIMEOUT, f"git timed out after {self.timeout_s}s: {args}") from e
        except (OSError, ValueError) as e:
            raise GitError(GIT_COMMAND_FAILED, f"git exec failed: {e}") from e
        if check and p.returncode != 0:
            raise GitError(GIT_COMMAND_FAILED,
                           f"git {args} rc={p.returncode}: {p.stderr.decode('utf-8', 'replace')[:200]}")
        return {"rc": p.returncode, "out": p.stdout, "err": p.stderr}


class DefaultFS:
    """Injected filesystem reader. Refuses absolute / traversal paths; never follows symlinks silently."""

    def lexists(self, abs_path):
        return os.path.lexists(abs_path)

    def is_symlink(self, abs_path):
        return os.path.islink(abs_path)

    def readlink(self, abs_path):
        return os.readlink(abs_path)

    def lstat_mode(self, abs_path):
        return os.lstat(abs_path).st_mode

    def read_bytes(self, abs_path):
        with open(abs_path, "rb") as fh:
            return fh.read()


def default_digest(data: bytes) -> str:
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("digest input must be bytes")
    return "sha256:" + hashlib.sha256(bytes(data)).hexdigest()


# ── path safety (§13) ───────────────────────────────────────────────────────────────
def _validate_rel_path(rel: str):
    """Return (ok, reason). A dependency path must be repository-relative, POSIX, no NUL, no traversal."""
    if not isinstance(rel, str) or not rel:
        return False, "empty path"
    if "\x00" in rel:
        return False, "NUL in path"
    if rel.startswith("/") or (len(rel) > 1 and rel[1] == ":"):
        return False, "absolute path"
    if "\\" in rel:
        return False, "backslash separator"
    parts = PurePosixPath(rel).parts
    if ".." in parts or any(p == "" for p in parts):
        return False, "path traversal / empty segment"
    if PurePosixPath(rel).is_absolute():
        return False, "absolute path"
    return True, "ok"


LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/"


def _dep_result(dep, accepted, code, explanation, **extra):
    r = {
        "dependency_id": dep.get("id"), "path": dep.get("path"), "accepted": bool(accepted),
        "reason_code": code, "required": bool(dep.get("required", True)),
        "dependency_type": dep.get("type"), "explanation": explanation,
        "head_object_id": None, "index_object_id": None, "worktree_digest": None,
        "git_status": None, "tracked": None, "object_type": None, "file_mode": None,
        "symlink": None, "lfs": None, "submodule": None,
        "dependency_policy_version": DEPENDENCY_POLICY_VERSION, "resolver_version": RESOLVER_VERSION,
    }
    r.update(extra)
    return r


class GitDependencyResolver:
    """Deterministic, fail-closed Git dependency resolver. All effects injected."""

    def __init__(self, repo_root, *, git=None, fs=None, digest_fn=default_digest, clock=None,
                 resolver_id=RESOLVER_ID):
        self.repo_root = str(repo_root)
        self.git = git or SubprocessGitRunner()
        self.fs = fs or DefaultFS()
        self.digest_fn = digest_fn
        self.clock = clock                      # optional () -> RFC3339 str (report metadata only)
        self.resolver_id = resolver_id

    # -- repository identity (§7) ---------------------------------------------------
    def resolve_repository_identity(self, expected):
        """expected: {root, canonical_name?, root_commit?}. Identity is bound by (toplevel path + root
        commit), NOT by folder name / cwd / mere .git presence alone."""
        try:
            top = self.git.run(self.repo_root, ["rev-parse", "--show-toplevel"])
        except GitError as e:
            if e.code == GIT_COMMAND_TIMEOUT:
                return False, GIT_COMMAND_TIMEOUT, e.detail, {}
            return False, GIT_REPOSITORY_NOT_FOUND, e.detail, {}
        toplevel = top["out"].decode("utf-8", "replace").strip()
        if not toplevel:
            return False, GIT_REPOSITORY_NOT_FOUND, "no worktree toplevel", {}
        exp_root = expected.get("root")
        if exp_root and os.path.realpath(toplevel) != os.path.realpath(str(exp_root)):
            return False, GIT_REPOSITORY_MISMATCH, f"toplevel {toplevel!r} != expected {exp_root!r}", {}
        name = expected.get("canonical_name")
        if name and os.path.basename(os.path.normpath(toplevel)) != name:
            return False, GIT_REPOSITORY_MISMATCH, f"repo name != {name!r}", {}
        want_root = expected.get("root_commit")
        info = {"toplevel": toplevel}
        if want_root:
            try:
                roots = self.git.run(self.repo_root, ["rev-list", "--max-parents=0", "HEAD"])
            except GitError as e:
                return False, GIT_REPOSITORY_MISMATCH, f"root-commit unresolved: {e.detail}", {}
            root_set = set(roots["out"].decode().split())
            if want_root not in root_set:
                return False, GIT_REPOSITORY_MISMATCH, "expected root commit not in history", info
            info["root_commit"] = want_root
        return True, ACCEPTED, "repository identity bound", info

    def resolve_head(self):
        try:
            head = self.git.run(self.repo_root, ["rev-parse", "HEAD"])
        except GitError as e:
            return None, (GIT_COMMAND_TIMEOUT if e.code == GIT_COMMAND_TIMEOUT else GIT_HEAD_UNRESOLVED)
        return head["out"].decode().strip(), ACCEPTED

    def is_shallow(self):
        try:
            r = self.git.run(self.repo_root, ["rev-parse", "--is-shallow-repository"])
        except GitError:
            return True   # cannot prove non-shallow → fail closed for provenance
        return r["out"].decode().strip() == "true"

    def is_detached(self):
        try:
            r = self.git.run(self.repo_root, ["symbolic-ref", "-q", "HEAD"], check=False)
        except GitError:
            return True
        return r["rc"] != 0

    # -- per-path git inspection ----------------------------------------------------
    def _status_map(self, paths):
        """One porcelain pass over the closure paths → {path: 'XY'}; includes ignored (!!)."""
        args = ["status", "--porcelain=v1", "-z", "--ignored", "--", *paths]
        out = self.git.run(self.repo_root, args)["out"]
        m = {}
        tokens = out.split(b"\x00")
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if not tok:
                i += 1
                continue
            xy = tok[:2].decode("utf-8", "replace")
            rest = tok[3:].decode("utf-8", "replace")
            if xy[0] == "R" or xy[0] == "C":
                # rename/copy: 'XY <to>\0<from>\0' — the <from> token follows
                m[rest] = xy
                if i + 1 < len(tokens):
                    m[tokens[i + 1].decode("utf-8", "replace")] = xy
                i += 2
                continue
            m[rest] = xy
            i += 1
        return m

    def _ls_tree(self, path):
        r = self.git.run(self.repo_root, ["ls-tree", "-z", "HEAD", "--", path])
        raw = r["out"].split(b"\x00")[0]
        if not raw:
            return None
        meta, _, _name = raw.partition(b"\t")
        parts = meta.decode().split()
        if len(parts) < 3:
            return None
        return {"mode": parts[0], "type": parts[1], "sha": parts[2]}

    def _ls_files_stage(self, path):
        r = self.git.run(self.repo_root, ["ls-files", "-s", "-z", "--", path])
        raw = r["out"].split(b"\x00")[0]
        if not raw:
            return None
        meta, _, _name = raw.partition(b"\t")
        parts = meta.decode().split()
        if len(parts) < 3:
            return None
        return {"mode": parts[0], "sha": parts[1], "stage": parts[2]}

    def _ls_files_flags(self, path):
        r = self.git.run(self.repo_root, ["ls-files", "-v", "-z", "--", path])
        raw = r["out"].split(b"\x00")[0]
        if not raw:
            return None
        return raw.decode()[:1]   # tag letter: lowercase=assume-unchanged, 'S'=skip-worktree

    # -- evaluate one dependency ----------------------------------------------------
    def evaluate_dependency(self, dep, status_map):
        path = dep.get("path")
        ok, why = _validate_rel_path(path)
        if not ok:
            return _dep_result(dep, False, DEPENDENCY_PATH_INVALID, why)
        allow_symlink = bool(dep.get("allow_symlink", False))
        abs_path = os.path.join(self.repo_root, path)
        try:
            head = self._ls_tree(path)
            stage = self._ls_files_stage(path)
            flag = self._ls_files_flags(path)
        except GitError as e:
            code = GIT_COMMAND_TIMEOUT if e.code == GIT_COMMAND_TIMEOUT else GIT_COMMAND_FAILED
            return _dep_result(dep, False, code, e.detail)

        xy = status_map.get(path)
        tracked = head is not None or stage is not None

        # submodule (gitlink) / object-type
        if head is not None and head["type"] == "commit":
            return self._resolve_submodule(dep, head)
        if head is not None and head["type"] == "tree":
            return _dep_result(dep, False, DEPENDENCY_OBJECT_TYPE_MISMATCH,
                               "dependency resolves to a tree, not a blob", object_type="tree")

        # not committed at HEAD
        if head is None:
            if self.fs.lexists(abs_path) or stage is not None:
                return _dep_result(dep, False, DEPENDENCY_UNTRACKED,
                                   "path present but not committed at HEAD", tracked=bool(stage))
            return _dep_result(dep, False, DEPENDENCY_MISSING, "required dependency absent", tracked=False)

        # index flags (assume-unchanged / skip-worktree) — forbidden for protected deps
        if flag and flag.islower():
            return _dep_result(dep, False, DEPENDENCY_ASSUME_UNCHANGED,
                               "assume-unchanged set on protected dependency", tracked=True)
        if flag == "S":
            return _dep_result(dep, False, DEPENDENCY_SKIP_WORKTREE,
                               "skip-worktree set on protected dependency", tracked=True)

        # worktree/index status (rename/delete/modify caught here with a specific code)
        if xy is not None and xy not in (None, "  "):
            X, Y = xy[0], xy[1]
            if xy == "!!":
                return _dep_result(dep, False, DEPENDENCY_UNTRACKED, "dependency is ignored", tracked=True,
                                   git_status=xy)
            if X in ("R", "C"):
                return _dep_result(dep, False, DEPENDENCY_RENAMED, "dependency renamed/copied",
                                   git_status=xy)
            if "D" in (X, Y):
                return _dep_result(dep, False, DEPENDENCY_DELETED, "dependency deleted", git_status=xy)
            if X == "T" or Y == "T":
                return _dep_result(dep, False, DEPENDENCY_MODE_CHANGED, "type/mode change", git_status=xy)
            if X in ("M", "A"):
                return _dep_result(dep, False, DEPENDENCY_STAGED_MODIFICATION,
                                   "staged modification/addition differs from HEAD", git_status=xy)
            if Y == "M":
                return _dep_result(dep, False, DEPENDENCY_WORKTREE_MODIFICATION,
                                   "worktree content differs from index/HEAD", git_status=xy)

        # committed at HEAD but absent from the index → staged deletion / index removal not surfaced by
        # status above (e.g. tracked file removed from index and recreated as untracked content).
        if stage is None:
            return _dep_result(dep, False, DEPENDENCY_DELETED,
                               "tracked at HEAD but removed from the index", head_object_id=head["sha"])

        # symlink handling
        is_link = self.fs.is_symlink(abs_path)
        head_is_link = head["mode"] == "120000"
        if (is_link or head_is_link) and not allow_symlink:
            return _dep_result(dep, False, DEPENDENCY_SYMLINK_UNEXPECTED,
                               "unexpected symlink for a protected dependency", symlink=True)
        if is_link and allow_symlink:
            esc = self._symlink_escapes(abs_path)
            if esc:
                return _dep_result(dep, False, DEPENDENCY_SYMLINK_ESCAPE, esc, symlink=True)

        # object type must be blob
        if head["type"] != "blob":
            return _dep_result(dep, False, DEPENDENCY_OBJECT_TYPE_MISMATCH,
                               f"HEAD object type {head['type']!r} is not a blob", object_type=head["type"])

        # file-mode policy
        exp_mode = dep.get("expected_mode")
        if exp_mode and head["mode"] != exp_mode:
            return _dep_result(dep, False, DEPENDENCY_MODE_CHANGED,
                               f"HEAD mode {head['mode']} != expected {exp_mode}", file_mode=head["mode"])

        # LFS policy
        try:
            data = self.fs.read_bytes(abs_path)
        except OSError as e:
            return _dep_result(dep, False, DEPENDENCY_MISSING, f"unreadable worktree file: {e}")
        if data.startswith(LFS_POINTER_PREFIX):
            lfs_ok, lfs_why = self._resolve_lfs(dep, data)
            if not lfs_ok:
                return _dep_result(dep, False, DEPENDENCY_LFS_UNAVAILABLE, lfs_why, lfs="pointer")

        # blob identity (optional pinned sha) + worktree digest
        try:
            wt_digest = self.digest_fn(data)
        except Exception as e:  # noqa: BLE001 - a raising digest fails closed
            return _dep_result(dep, False, DEPENDENCY_DIGEST_FAILED, f"digest failed: {e}")
        pinned = dep.get("expected_blob_sha")
        if pinned and head["sha"] != pinned:
            return _dep_result(dep, False, DEPENDENCY_BLOB_MISMATCH,
                               f"HEAD blob {head['sha'][:12]} != pinned {pinned[:12]}",
                               head_object_id=head["sha"])

        return _dep_result(dep, True, ACCEPTED, "tracked, clean, bound to HEAD",
                           head_object_id=head["sha"], index_object_id=(stage or {}).get("sha"),
                           worktree_digest=wt_digest, git_status="  ", tracked=True,
                           object_type="blob", file_mode=head["mode"], symlink=bool(is_link), lfs=None)

    def _symlink_escapes(self, abs_path):
        try:
            target = self.fs.readlink(abs_path)
        except OSError as e:
            return f"broken symlink: {e}"
        if os.path.isabs(target):
            return "absolute symlink target"
        resolved = os.path.realpath(abs_path)
        root = os.path.realpath(self.repo_root)
        if not (resolved == root or resolved.startswith(root + os.sep)):
            return "symlink target escapes repository"
        if not os.path.exists(resolved):
            return "symlink target missing"
        return None

    def _resolve_submodule(self, dep, head):
        exp = dep.get("submodule")
        if not exp:
            return _dep_result(dep, False, DEPENDENCY_SUBMODULE_MISMATCH,
                               "gitlink present but no submodule policy declared", submodule="gitlink")
        if exp.get("expected_commit") and head["sha"] != exp["expected_commit"]:
            return _dep_result(dep, False, DEPENDENCY_SUBMODULE_MISMATCH,
                               "submodule commit != expected", submodule=head["sha"])
        return _dep_result(dep, True, ACCEPTED, "submodule bound", submodule=head["sha"],
                           object_type="commit")

    def _resolve_lfs(self, dep, data):
        """LFS pointer detected. Fail closed unless policy accepts the pointer itself as the dependency.
        git-lfs materialisation is NOT checked/downloaded in this gate (documented limitation)."""
        policy = (dep.get("lfs") or {}).get("policy", "materialised_required")
        if b"\noid sha256:" not in data:
            return False, "malformed LFS pointer (no oid)"
        if policy == "pointer_ok":
            return True, "pointer accepted by policy"
        return False, "LFS materialised object required but git-lfs unavailable — failing closed"

    # -- manifest + aggregate (§5,§18,§19) ------------------------------------------
    def load_dependency_manifest(self, manifest):
        if isinstance(manifest, (str, os.PathLike)):
            try:
                with open(manifest, "rb") as fh:
                    manifest = json.loads(fh.read())
            except (OSError, ValueError) as e:
                raise GitError(DEPENDENCY_MANIFEST_INVALID, f"manifest unreadable: {e}") from e
        if not isinstance(manifest, dict):
            raise GitError(DEPENDENCY_MANIFEST_INVALID, "manifest is not an object")
        if manifest.get("manifest_version") not in SUPPORTED_MANIFEST_VERSIONS:
            raise GitError(DEPENDENCY_MANIFEST_INVALID,
                           f"unsupported manifest_version {manifest.get('manifest_version')!r}")
        deps = manifest.get("dependencies")
        if not isinstance(deps, list) or not deps:
            raise GitError(DEPENDENCY_MANIFEST_INVALID, "manifest has no dependencies")
        ids = [d.get("id") for d in deps]
        if len(ids) != len(set(ids)) or any(not i for i in ids):
            raise GitError(DEPENDENCY_MANIFEST_INVALID, "duplicate/empty dependency id")
        return manifest

    def _closure_digest(self, per_dep):
        """Deterministic digest over (id, path, reason, head_object_id) sorted — EXCLUDES volatile metadata
        (timestamps, host paths) so identical repo state yields an identical closure digest (§25)."""
        canon = sorted(({"id": d["dependency_id"], "path": d["path"], "reason": d["reason_code"],
                         "head": d.get("head_object_id"), "required": d["required"]}
                        for d in per_dep), key=lambda x: x["id"])
        blob = json.dumps(canon, sort_keys=True, separators=(",", ":")).encode()
        return self.digest_fn(blob)

    def build_resolution_report(self, manifest, *, expected_repository=None):
        """Resolve the whole closure. Returns a structured aggregate report (§19). Mandatory dependency
        failure, unresolved state, repo mismatch or Git unavailability → overall accepted False."""
        # metadata clock (report only; not in the closure digest)
        gen_at = None
        clock_trust = "untrusted"
        if self.clock is not None:
            try:
                gen_at = self.clock()
                clock_trust = "injected"
            except Exception:  # noqa: BLE001
                gen_at = None
        base = {
            "resolver_id": self.resolver_id, "resolver_version": RESOLVER_VERSION,
            "dependency_policy_version": DEPENDENCY_POLICY_VERSION,
            "generated_at": gen_at, "clock_trust": clock_trust,
            # G1R (H8-G1REV-F-001): in-process authenticity marker stamped by the genuine resolver. Every
            # return path spreads **base, so both accepted and rejected reports carry it; report_binding_ok
            # requires it, so an ordinary caller-forged dict (approved id, no marker) is rejected.
            "authenticity": _REPORT_AUTHENTICITY,
        }
        try:
            manifest = self.load_dependency_manifest(manifest)
        except GitError as e:
            return {**base, "overall_accepted": False, "reason_code": e.code, "explanation": e.detail,
                    "repository": None, "head_commit": None, "manifest_digest": None,
                    "dependency_count": 0, "accepted_count": 0, "rejected_count": 0, "unresolved_count": 0,
                    "results": [], "closure_digest": None, "failures": [e.code]}
        try:
            manifest_digest = self.digest_fn(
                json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode())
        except Exception as e:  # noqa: BLE001 - a raising digest fails closed, never crashes the resolver
            return {**base, "overall_accepted": False, "reason_code": DEPENDENCY_DIGEST_FAILED,
                    "explanation": f"digest implementation failed: {e}", "repository": None,
                    "head_commit": None, "manifest_digest": None,
                    "dependency_count": len(manifest["dependencies"]), "accepted_count": 0,
                    "rejected_count": 0, "unresolved_count": len(manifest["dependencies"]),
                    "results": [], "closure_digest": None, "failures": [DEPENDENCY_DIGEST_FAILED]}

        exp = dict(expected_repository or manifest.get("expected_repository") or {})
        exp.setdefault("root", self.repo_root)
        id_ok, id_code, id_why, id_info = self.resolve_repository_identity(exp)
        if not id_ok:
            return {**base, "overall_accepted": False, "reason_code": id_code, "explanation": id_why,
                    "repository": id_info, "head_commit": None, "manifest_digest": manifest_digest,
                    "dependency_count": len(manifest["dependencies"]), "accepted_count": 0,
                    "rejected_count": 0, "unresolved_count": len(manifest["dependencies"]),
                    "results": [], "closure_digest": None, "failures": [id_code]}
        head, head_code = self.resolve_head()
        if head is None:
            return {**base, "overall_accepted": False, "reason_code": head_code,
                    "explanation": "HEAD unresolved", "repository": id_info, "head_commit": None,
                    "manifest_digest": manifest_digest, "dependency_count": len(manifest["dependencies"]),
                    "accepted_count": 0, "rejected_count": 0,
                    "unresolved_count": len(manifest["dependencies"]), "results": [],
                    "closure_digest": None, "failures": [head_code]}
        # provenance requires full history for any dependency with provenance_requires_history
        if any(d.get("provenance_requires_history") for d in manifest["dependencies"]) and self.is_shallow():
            return {**base, "overall_accepted": False, "reason_code": GIT_HISTORY_INSUFFICIENT,
                    "explanation": "shallow repository cannot prove required provenance",
                    "repository": id_info, "head_commit": head, "manifest_digest": manifest_digest,
                    "dependency_count": len(manifest["dependencies"]), "accepted_count": 0,
                    "rejected_count": 0, "unresolved_count": len(manifest["dependencies"]),
                    "results": [], "closure_digest": None, "failures": [GIT_HISTORY_INSUFFICIENT]}

        # only pass VALID repo-relative paths to `git status` (absolute/traversal paths would make git
        # error; they are still caught per-dependency as DEPENDENCY_PATH_INVALID).
        paths = [d["path"] for d in manifest["dependencies"]
                 if isinstance(d.get("path"), str) and _validate_rel_path(d["path"])[0]]
        try:
            status_map = self._status_map(paths) if paths else {}
        except GitError as e:
            code = GIT_COMMAND_TIMEOUT if e.code == GIT_COMMAND_TIMEOUT else GIT_COMMAND_FAILED
            return {**base, "overall_accepted": False, "reason_code": code, "explanation": e.detail,
                    "repository": id_info, "head_commit": head, "manifest_digest": manifest_digest,
                    "dependency_count": len(manifest["dependencies"]), "accepted_count": 0,
                    "rejected_count": 0, "unresolved_count": len(manifest["dependencies"]),
                    "results": [], "closure_digest": None, "failures": [code]}

        results = [self.evaluate_dependency(d, status_map) for d in manifest["dependencies"]]
        accepted = [r for r in results if r["accepted"]]
        rejected = [r for r in results if not r["accepted"]]
        # a REQUIRED dependency that is rejected (or unresolved) fails the aggregate closed
        mandatory_failures = [r for r in rejected if r["required"]]
        overall = not mandatory_failures
        closure_digest = self._closure_digest(results)
        return {
            **base, "overall_accepted": overall,
            "reason_code": ACCEPTED if overall else DEPENDENCY_REQUIRED_UNRESOLVED,
            "explanation": ("all mandatory dependencies clean and bound to HEAD" if overall else
                            f"{len(mandatory_failures)} mandatory dependency(ies) failed closed"),
            "repository": id_info, "head_commit": head, "manifest_digest": manifest_digest,
            "dependency_count": len(results), "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "unresolved_count": len(mandatory_failures), "results": results,
            "closure_digest": closure_digest,
            "failures": sorted({r["reason_code"] for r in mandatory_failures}),
        }

    # -- G1R: security-relevant Git state inspection (H8-G1REV-F-003) ----------------
    def inspect_git_config(self):
        """Explicitly inspect security-relevant Git state that could redirect object identity. The config
        values fileMode/symlinks/ignorecase/autocrlf are PINNED on EVERY invocation via _GIT_SAFE_OVERRIDES;
        here we additionally REJECT a repository that carries replace refs or an alternate object database,
        because their mere presence is an object-identity substitution surface even when
        `--no-replace-objects` bypasses replacement at read time. Returns (ok, code, detail)."""
        # (1) replace refs (refs/replace/*) — object substitution surface
        try:
            r = self.git.run(self.repo_root,
                             ["for-each-ref", "--format=%(refname)", "refs/replace/"], check=False)
        except GitError as e:
            return (False, GIT_COMMAND_TIMEOUT if e.code == GIT_COMMAND_TIMEOUT else GIT_COMMAND_FAILED,
                    e.detail)
        if r["out"].strip():
            return False, GIT_REPLACE_OBJECTS, "refs/replace present (object substitution surface)"
        # (2) alternate object databases — object source outside this repository
        try:
            gp = self.git.run(self.repo_root, ["rev-parse", "--git-path", "objects/info/alternates"])
        except GitError as e:
            return (False, GIT_COMMAND_TIMEOUT if e.code == GIT_COMMAND_TIMEOUT else GIT_COMMAND_FAILED,
                    e.detail)
        alt_rel = gp["out"].decode("utf-8", "replace").strip()
        alt_path = alt_rel if os.path.isabs(alt_rel) else os.path.join(self.repo_root, alt_rel)
        try:
            if self.fs.lexists(alt_path):
                content = self.fs.read_bytes(alt_path)
                if content.strip():
                    return False, GIT_ALTERNATE_OBJECTS, "alternate object database configured"
        except OSError as e:
            return False, GIT_ALTERNATE_OBJECTS, f"alternates unreadable — failing closed: {e}"
        return True, ACCEPTED, "no replace refs or alternate object DBs"

    # -- G1R: canonical-manifest enforcement (H8-G1REV-F-002) -----------------------
    def _canonical_reject(self, code, detail, manifest=None):
        n = len(manifest.get("dependencies", [])) if isinstance(manifest, dict) else 0
        return {
            "resolver_id": self.resolver_id, "resolver_version": RESOLVER_VERSION,
            "dependency_policy_version": DEPENDENCY_POLICY_VERSION,
            "generated_at": None, "clock_trust": "untrusted", "authenticity": _REPORT_AUTHENTICITY,
            "overall_accepted": False, "reason_code": code, "explanation": detail,
            "repository": None, "head_commit": None, "manifest_digest": None,
            "dependency_count": n, "accepted_count": 0, "rejected_count": 0, "unresolved_count": n,
            "results": [], "closure_digest": None, "failures": [code],
            "canonical_manifest": CANONICAL_MANIFEST_REL,
        }

    def resolve_canonical(self, *, expected_repository=None):
        """Resolve the ONE repository-tracked canonical manifest. Protected callers use THIS — never a
        caller-selected manifest path or an in-memory manifest dict. Enforces, in order: security-relevant
        Git state clean; the canonical path is the only manifest source; the manifest self-lists AT the
        canonical path; the mandatory dependency-id set is present (a caller cannot silently drop a known
        decision-critical dependency); then delegates to build_resolution_report so the canonical manifest
        FILE itself is resolved (tracked + unmodified + bound to HEAD). Any violation fails closed."""
        cfg_ok, cfg_code, cfg_why = self.inspect_git_config()
        if not cfg_ok:
            return self._canonical_reject(cfg_code, f"git state rejected: {cfg_why}")
        canonical_path = os.path.join(self.repo_root, CANONICAL_MANIFEST_REL)
        try:
            manifest = self.load_dependency_manifest(canonical_path)
        except GitError as e:
            return self._canonical_reject(e.code, f"canonical manifest: {e.detail}")
        by_id = {d.get("id"): d for d in manifest.get("dependencies", [])}
        # the manifest must describe ITSELF at the canonical path (defeats a substituted manifest body)
        self_dep = by_id.get("h8-dependency-manifest")
        if not self_dep or self_dep.get("path") != CANONICAL_MANIFEST_REL:
            return self._canonical_reject(
                MANIFEST_NOT_CANONICAL,
                f"manifest does not self-list at {CANONICAL_MANIFEST_REL!r}", manifest)
        # mandatory dependency-id set present
        missing = sorted(REQUIRED_DEPENDENCY_IDS - set(by_id))
        if missing:
            return self._canonical_reject(
                MANIFEST_INCOMPLETE, f"canonical manifest missing mandatory ids: {missing}", manifest)
        # delegate: resolves the canonical manifest FILE + the whole closure, bound to HEAD
        report = self.build_resolution_report(canonical_path, expected_repository=expected_repository)
        report["canonical_manifest"] = CANONICAL_MANIFEST_REL
        # defence in depth: the manifest-self dependency must itself have RESOLVED clean
        self_res = next((r for r in report.get("results", [])
                         if r.get("dependency_id") == "h8-dependency-manifest"), None)
        if report.get("overall_accepted") and (not self_res or not self_res.get("accepted")):
            report["overall_accepted"] = False
            report["reason_code"] = MANIFEST_NOT_CANONICAL
            report["explanation"] = "canonical manifest file did not self-verify"
            report["failures"] = sorted({*report.get("failures", []), MANIFEST_NOT_CANONICAL})
        return report


# ── provider integration boundary (§21) ─────────────────────────────────────────────
def report_binding_ok(report, *, expected_repo=None, expected_head=None, expected_closure_digest=None):
    """Verify a resolver report is well-formed, from an APPROVED resolver, accepted, and (optionally)
    bound to the expected repo/HEAD/closure. Returns (ok, code). Fixture resolvers are rejected here for
    protected use; stale/mismatched reports fail closed."""
    if not isinstance(report, dict):
        return False, RESOLVER_UNAVAILABLE
    # G1R (H8-G1REV-F-001): an ordinary caller-forged dict presenting an approved resolver_id but lacking
    # the in-process authenticity marker is rejected before any acceptance is honoured. This is an
    # in-process control (module-access forgery remains a documented residual → G2 cryptographic signing).
    if report.get("authenticity") != _REPORT_AUTHENTICITY:
        return False, REPORT_UNAUTHENTIC
    if report.get("resolver_id") not in APPROVED_RESOLVER_IDS:
        return False, RESOLVER_FIXTURE_IN_PROTECTED
    if not report.get("overall_accepted"):
        return False, report.get("reason_code", DEPENDENCY_REQUIRED_UNRESOLVED)
    if expected_head is not None and report.get("head_commit") != expected_head:
        return False, REPORT_HEAD_MISMATCH
    if expected_closure_digest is not None and report.get("closure_digest") != expected_closure_digest:
        return False, REPORT_CLOSURE_DIGEST_MISMATCH
    if expected_repo is not None:
        repo = report.get("repository") or {}
        if repo.get("toplevel") and expected_repo not in (repo.get("toplevel"),
                                                           os.path.realpath(repo.get("toplevel"))):
            return False, REPORT_REPO_MISMATCH
    return True, ACCEPTED


def provider_tree_state(resolver, manifest, *, mode="preflight", expected_head=None,
                        expected_closure_digest=None):
    """Adapter for the evidence-provider `tree_state` injection seam. Runs the resolver and returns the
    provider's expected `{commit, dependency_dirty, resolution_digest, resolution}` dict — FAIL CLOSED
    (`dependency_dirty=True`) for any non-clean/unavailable/fixture/HEAD-mismatch/stale/digest-mismatch
    condition. This adapter cannot authorise capture; a clean report only permits preflight documents.

    Returns a callable (the provider calls `tree_state()`)."""
    def _ts():
        try:
            report = resolver.build_resolution_report(manifest)
        except Exception as e:  # noqa: BLE001 - resolver crash fails closed
            return {"commit": "unknown", "dependency_dirty": True,
                    "resolution_digest": None, "resolution": {"reason_code": RESOLVER_UNAVAILABLE,
                                                               "detail": str(e)}}
        ok, code = report_binding_ok(report, expected_head=expected_head,
                                     expected_closure_digest=expected_closure_digest)
        return {
            "commit": report.get("head_commit") or "unknown",
            "dependency_dirty": not ok,           # provider requires exactly False to proceed
            "resolution_digest": report.get("closure_digest"),
            "resolution_reason": code,
            "resolution": {"reason_code": report.get("reason_code"),
                           "closure_digest": report.get("closure_digest"),
                           "failures": report.get("failures")},
        }
    return _ts


def trusted_provider_tree_state(repo_root, *, mode="preflight", expected_head=None,
                                expected_closure_digest=None, git=None, fs=None):
    """TRUSTED construction path for protected provider modes (H8-G1REV-F-001/-F-002).

    Constructs the genuine resolver IN-PROCESS and resolves the ONE canonical repository-tracked manifest
    on every call. There is deliberately NO injection surface for a caller-supplied resolver, resolution
    report, manifest object/path, or assume-clean flag — a caller cannot substitute a fabricated
    resolution or select a reduced manifest. Fail closed (`dependency_dirty=True`) on any
    non-clean/unavailable/mismatch condition. Cannot authorise capture; a clean result permits ONLY
    non-authorising preflight document generation.

    `git`/`fs` are a DOCUMENTED, TEST-ONLY seam so fixture tests can drive this path against a temporary
    repository. They carry no acceptance authority (the resolver still fails closed on any dirty/missing/
    substituted dependency) and are never supplied by the real provider construction path, which calls
    `trusted_provider_tree_state(repo_root)` with defaults. Cross-process authentication of a low-level
    Git runner is out of scope here and is a documented residual (→ G2)."""
    if mode not in ("preflight", "production"):
        raise ValueError(f"unsupported protected mode {mode!r}")

    def _ts():
        try:
            resolver = GitDependencyResolver(repo_root, git=git, fs=fs)
            report = resolver.resolve_canonical()
        except Exception as e:  # noqa: BLE001 - any resolver crash fails closed
            return {"commit": "unknown", "dependency_dirty": True, "resolution_digest": None,
                    "resolution": {"reason_code": RESOLVER_UNAVAILABLE, "detail": str(e)}}
        ok, code = report_binding_ok(report, expected_head=expected_head,
                                     expected_closure_digest=expected_closure_digest)
        return {
            "commit": report.get("head_commit") or "unknown",
            "dependency_dirty": not ok,
            "resolution_digest": report.get("closure_digest"),
            "resolution_reason": code,
            "resolution": {"reason_code": report.get("reason_code"),
                           "closure_digest": report.get("closure_digest"),
                           "failures": report.get("failures"),
                           "canonical_manifest": report.get("canonical_manifest")},
        }
    return _ts
