"""Subprocess management — launch, stream logs, kill benchmark scripts."""
from __future__ import annotations

import asyncio
import os
import signal
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator


@dataclass
class Job:
    job_id: str
    script_key: str
    label: str
    cmd: list[str]
    cwd: Path
    status: str = "queued"    # queued | running | done | error | killed
    pid: int | None = None
    exit_code: int | None = None
    started_at: float | None = None
    finished_at: float | None = None
    _log_lines: list[str] = field(default_factory=list)
    _proc: asyncio.subprocess.Process | None = field(default=None, repr=False)

    def as_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "script_key": self.script_key,
            "label": self.label,
            "status": self.status,
            "pid": self.pid,
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    def tail(self, n: int = 200) -> list[str]:
        return self._log_lines[-n:]


class ProcessManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def list_jobs(self) -> list[dict]:
        return [j.as_dict() for j in reversed(list(self._jobs.values()))]

    def get_job(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    async def launch(self, script_key: str, label: str, cmd: list[str], cwd: Path) -> Job:
        job_id = str(uuid.uuid4())[:8]
        job = Job(job_id=job_id, script_key=script_key, label=label, cmd=cmd, cwd=cwd)
        self._jobs[job_id] = job
        self._subscribers[job_id] = []
        asyncio.create_task(self._run(job))
        return job

    async def kill(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job or job._proc is None:
            return False
        try:
            os.killpg(os.getpgid(job._proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        job.status = "killed"
        job.finished_at = time.time()
        await self._broadcast(job_id, "__KILLED__\n")
        return True

    async def subscribe(self, job_id: str) -> AsyncIterator[str]:
        """Yield log lines as they arrive; yields existing buffer first."""
        job = self._jobs.get(job_id)
        if not job:
            return
        q: asyncio.Queue = asyncio.Queue()
        # Drain existing buffer
        for line in job._log_lines:
            await q.put(line)
        if job.status in ("done", "error", "killed"):
            await q.put(None)  # sentinel
        else:
            self._subscribers[job_id].append(q)
        while True:
            item = await q.get()
            if item is None:
                break
            yield item

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _run(self, job: Job) -> None:
        job.status = "running"
        job.started_at = time.time()
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        try:
            proc = await asyncio.create_subprocess_exec(
                *job.cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(job.cwd),
                env=env,
                start_new_session=True,
            )
            job._proc = proc
            job.pid = proc.pid

            assert proc.stdout is not None
            async for raw in proc.stdout:
                line = raw.decode(errors="replace")
                job._log_lines.append(line)
                await self._broadcast(job.job_id, line)

            await proc.wait()
            job.exit_code = proc.returncode
            job.status = "done" if proc.returncode == 0 else "error"
        except Exception as exc:
            job.status = "error"
            err_line = f"[process_manager] ERROR: {exc}\n"
            job._log_lines.append(err_line)
            await self._broadcast(job.job_id, err_line)
        finally:
            job.finished_at = time.time()
            await self._broadcast(job.job_id, None)  # sentinel to close subscribers

    async def _broadcast(self, job_id: str, line: str | None) -> None:
        closed: list[asyncio.Queue] = []
        for q in self._subscribers.get(job_id, []):
            await q.put(line)
            if line is None:
                closed.append(q)
        for q in closed:
            self._subscribers[job_id].remove(q)


# Module-level singleton
process_manager = ProcessManager()
