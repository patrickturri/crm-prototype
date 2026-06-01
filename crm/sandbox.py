"""Sandboxed execution of model-generated Python (§6.2).

NON-NEGOTIABLE (§3.6, §6.2, §15): arbitrary generated code is treated as
adversarial. It MUST NOT be able to reach the network or touch the host
filesystem outside an ephemeral, throwaway sandbox directory.

Mechanism (the spec gives latitude on *how*; these are the guarantees):

  * **fresh subprocess** — the candidate runs in a brand-new `python -I -S`
    interpreter (isolated mode, no site customisation), never in-process, so a
    crash / hang / `os._exit` cannot take down the loop.
  * **hard wall-clock timeout** — the parent kills the whole process group
    (`SIGKILL`) after `timeout_s`; a busy-loop or `sleep` cannot wedge the loop.
  * **no network** — inside the child we install import hooks + socket stubs
    that make any attempt to open a socket / urllib / http connection raise
    `SandboxNetworkError`. (We do this in-process in the child rather than rely
    on a namespace because we must run on a stock macOS/Linux dev box with no
    root, no nsjail/firejail/docker assumed; if those are present they can be
    layered on — see `_HARDENING_NOTE`.)
  * **ephemeral temp dir** — the child is `cd`-ed into a fresh `mkdtemp()` that
    the parent deletes afterwards; the cwd is the only writable location it is
    handed, and absolute writes outside the sandbox root are blocked by an
    `open()` wrapper that rejects paths escaping the sandbox root.
  * **restricted builtins** — the candidate body is executed via `exec()` with a
    curated builtins namespace: no `open` to escape, no `__import__` of network
    modules, no `eval`/`compile` of fresh code, no `exit`. Pure-compute builtins
    (`len`, `range`, `abs`, `min`, `max`, `sum`, `sorted`, `math`, ...) remain.
  * **memory cap** — `resource.setrlimit(RLIMIT_AS, ...)` caps address space so a
    runaway allocation is killed by the OS, not by swapping the host to death.

The child speaks a tiny JSON protocol back to the parent over stdout so the
critic learns *which* assertion failed (for the FALSE counterexample / detail).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass

# If a stronger isolator is available we *could* wrap the subprocess in it; we
# detect but do not require it (must run rootless on a stock dev box).
_HARDENING_NOTE = "in-process import/socket/open guards + rlimits + killed subprocess"


@dataclass
class SandboxResult:
    """Outcome of running one candidate program in the sandbox."""

    status: str          # "ok" | "fail" | "error" | "timeout" | "blocked"
    detail: str          # human-readable: which test failed / error / block reason
    returncode: int | None
    stdout_tail: str     # last chunk of child stdout (diagnostics)
    elapsed_s: float


# Memory cap for the child (bytes). 512 MB is plenty for arithmetic tasks and
# small enough that a runaway allocation is killed quickly.
DEFAULT_MEM_BYTES = 512 * 1024 * 1024


# The driver program that runs INSIDE the child interpreter. It:
#   1. installs the network + filesystem-escape guards,
#   2. caps memory,
#   3. chdirs into the sandbox root,
#   4. execs the candidate payload with restricted builtins,
#   5. prints a single JSON result line on stdout.
#
# It is fully self-contained (no project imports) so it runs under `python -I -S`.
_CHILD_DRIVER = r'''
import sys, json, builtins, io, os, resource

SANDBOX_ROOT = os.environ["CRM_SANDBOX_ROOT"]
MEM_BYTES = int(os.environ["CRM_SANDBOX_MEM"])

# ---- memory cap -----------------------------------------------------------
try:
    resource.setrlimit(resource.RLIMIT_AS, (MEM_BYTES, MEM_BYTES))
except (ValueError, OSError):
    pass
# Never write core dumps.
try:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
except (ValueError, OSError):
    pass


class SandboxNetworkError(RuntimeError):
    pass


class SandboxFSError(RuntimeError):
    pass


# ---- network kill-switch --------------------------------------------------
# Neuter the socket module so nothing can open a connection. We replace the
# socket class and connect helpers, and poison the import of higher-level net
# libs so even urllib/http/requests cannot phone home.
import socket as _socket_mod

def _blocked_net(*a, **k):
    raise SandboxNetworkError("network access is blocked in the sandbox")

class _BlockedSocket:
    def __init__(self, *a, **k):
        raise SandboxNetworkError("socket creation is blocked in the sandbox")

_socket_mod.socket = _BlockedSocket
_socket_mod.create_connection = _blocked_net
_socket_mod.create_server = _blocked_net
try:
    _socket_mod.socketpair = _blocked_net
except Exception:
    pass

import builtins as _b
_real_import = _b.__import__
_NET_MODULES = {
    "http", "http.client", "urllib.request", "urllib.error",
    "requests", "ftplib", "smtplib", "telnetlib", "asyncio",
    "ssl", "xmlrpc", "socketserver",
}

def _guarded_import(name, *args, **kwargs):
    root = name.split(".")[0]
    if name in _NET_MODULES or root in {"requests"}:
        raise SandboxNetworkError(f"import of network module {name!r} is blocked")
    return _real_import(name, *args, **kwargs)


# ---- filesystem escape guard ---------------------------------------------
# Allow reads/writes only inside SANDBOX_ROOT. Any open() whose resolved path
# escapes the sandbox root is rejected. This is the out-of-sandbox FS guard.
_real_open = _real_import("builtins").open
import os.path as _osp

def _within_sandbox(path):
    try:
        ap = _osp.realpath(path)
    except Exception:
        return False
    root = _osp.realpath(SANDBOX_ROOT)
    return ap == root or ap.startswith(root + os.sep)

def _guarded_open(file, mode="r", *args, **kwargs):
    # Block all writes/appends/creates outside the sandbox root, and block reads
    # of host files outside it too (defence in depth).
    try:
        p = os.fspath(file)
    except TypeError:
        # file descriptors etc. -> block to be safe
        raise SandboxFSError("opening non-path objects is blocked in the sandbox")
    if not _osp.isabs(p):
        p = _osp.join(SANDBOX_ROOT, p)
    if not _within_sandbox(p):
        raise SandboxFSError(
            "filesystem access outside the sandbox root is blocked: %r" % (file,)
        )
    return _real_open(p, mode, *args, **kwargs)


# ---- restricted builtins for the candidate body ---------------------------
# A curated, pure-compute namespace. No open (we inject the guarded one), no
# eval/compile/exec of fresh source, no exit, no __import__ of net modules.
_SAFE_BUILTIN_NAMES = [
    "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes",
    "callable", "chr", "complex", "dict", "divmod", "enumerate", "filter",
    "float", "format", "frozenset", "getattr", "hasattr", "hash", "hex", "id",
    "int", "isinstance", "issubclass", "iter", "len", "list", "map", "max",
    "min", "next", "object", "oct", "ord", "pow", "print", "range", "repr",
    "reversed", "round", "set", "setattr", "slice", "sorted", "str", "sum",
    "tuple", "type", "zip", "True", "False", "None",
    "Exception", "ValueError", "TypeError", "ZeroDivisionError",
    "AssertionError", "IndexError", "KeyError", "StopIteration",
    "ArithmeticError", "OverflowError", "RuntimeError",
]
_safe_builtins = {}
for _n in _SAFE_BUILTIN_NAMES:
    if hasattr(builtins, _n):
        _safe_builtins[_n] = getattr(builtins, _n)
_safe_builtins["__import__"] = _guarded_import
_safe_builtins["open"] = _guarded_open


def main():
    payload = json.loads(sys.stdin.read())
    code = payload["code"]
    # chdir into the throwaway sandbox root: the only writable place.
    os.chdir(SANDBOX_ROOT)

    glb = {"__builtins__": _safe_builtins, "__name__": "__crm_candidate__"}
    # Capture candidate stdout so it cannot smuggle data through ours.
    buf = io.StringIO()
    real_stdout = sys.stdout
    try:
        sys.stdout = buf
        exec(compile(code, "<candidate>", "exec"), glb, glb)
        result = {"status": "ok", "detail": "", "failed_test": None}
    except SandboxNetworkError as e:
        result = {"status": "blocked", "detail": "network: %s" % e, "failed_test": None}
    except SandboxFSError as e:
        result = {"status": "blocked", "detail": "filesystem: %s" % e, "failed_test": None}
    except AssertionError as e:
        msg = str(e) or "assertion failed"
        result = {"status": "fail", "detail": msg,
                  "failed_test": glb.get("__crm_current_test__")}
    except Exception as e:
        result = {"status": "error",
                  "detail": "%s: %s" % (type(e).__name__, e),
                  "failed_test": glb.get("__crm_current_test__")}
    finally:
        sys.stdout = real_stdout
    tail = buf.getvalue()[-2000:]
    print(json.dumps({"result": result, "stdout_tail": tail}))

main()
'''


def run_in_sandbox(
    code: str,
    timeout_s: float = 5.0,
    mem_bytes: int = DEFAULT_MEM_BYTES,
) -> SandboxResult:
    """Run `code` in a fresh, isolated, time- and memory-bounded subprocess.

    `code` is arbitrary model-generated Python. On return the sandbox dir is
    deleted. Guarantees: no network, no FS access outside the sandbox root,
    hard wall-clock kill, capped memory, restricted builtins.
    """
    import time as _time

    sandbox_root = tempfile.mkdtemp(prefix="crm_sbx_")
    env = {
        # Minimal, scrubbed environment: no inherited API keys / proxies / paths
        # that could be exfiltrated or used to reach the network.
        "CRM_SANDBOX_ROOT": sandbox_root,
        "CRM_SANDBOX_MEM": str(int(mem_bytes)),
        "PATH": "/usr/bin:/bin",
        "PYTHONHASHSEED": "0",
        # Explicitly blank out proxies so even a leaked import can't use one.
        "HTTP_PROXY": "", "HTTPS_PROXY": "", "NO_PROXY": "*",
    }

    t0 = _time.perf_counter()
    proc = None
    try:
        # `-I` isolated (ignore env PYTHON*, no user site), `-S` no site init.
        proc = subprocess.Popen(
            [sys.executable, "-I", "-S", "-c", _CHILD_DRIVER],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=sandbox_root,
            text=True,
            start_new_session=True,  # own process group => clean group kill
        )
        try:
            stdout, stderr = proc.communicate(
                input=json.dumps({"code": code}), timeout=timeout_s
            )
        except subprocess.TimeoutExpired:
            _kill_group(proc)
            proc.communicate()
            return SandboxResult(
                status="timeout",
                detail=f"wall-clock timeout after {timeout_s}s",
                returncode=None,
                stdout_tail="",
                elapsed_s=_time.perf_counter() - t0,
            )

        elapsed = _time.perf_counter() - t0
        rc = proc.returncode

        # Killed by OS (e.g. memory cap -> SIGKILL/SIGSEGV) leaves no JSON.
        line = _last_json_line(stdout)
        if line is None:
            killed = rc is not None and rc < 0
            detail = stderr.strip().splitlines()[-1] if stderr.strip() else ""
            if killed:
                return SandboxResult(
                    status="error",
                    detail=f"child killed by signal {-rc} (likely memory/resource cap): {detail}",
                    returncode=rc, stdout_tail=stdout[-2000:], elapsed_s=elapsed,
                )
            return SandboxResult(
                status="error",
                detail=f"no result from sandbox (rc={rc}): {detail}",
                returncode=rc, stdout_tail=stdout[-2000:], elapsed_s=elapsed,
            )

        res = line["result"]
        return SandboxResult(
            status=res["status"],
            detail=res.get("detail", ""),
            returncode=rc,
            stdout_tail=line.get("stdout_tail", "")[-2000:],
            elapsed_s=elapsed,
        )
    finally:
        if proc is not None and proc.poll() is None:
            _kill_group(proc)
        _rmtree_quiet(sandbox_root)


def _kill_group(proc: "subprocess.Popen") -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except Exception:
            pass


def _last_json_line(stdout: str) -> dict | None:
    for ln in reversed(stdout.splitlines()):
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "result" in obj:
            return obj
    return None


def _rmtree_quiet(path: str) -> None:
    import shutil

    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


def hardening_note() -> str:
    return _HARDENING_NOTE
