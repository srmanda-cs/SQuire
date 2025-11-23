#!/usr/bin/env python3
"""
post_checker_eval.py
--------------------
Build the custom CSA checker, optionally run lightweight smoke tests,
and (by default) execute a kernel workflow that:

  * checks out Linux v5.9 in the `linux/` submodule,
  * generates a compile_commands.json for that revision,
  * runs the Null Pointer Dereference checker over the translation units,
  * repeats the process for v5.17,
  * compares the diagnostics to determine which reports disappeared or remained,
  * restores the submodule to its original (pinned) revision.

Requirements
------------
* clang / clang++ with static analyzer support
* Either `intercept-build` (preferred) or `bear` to capture compile commands
* A checked-out `linux/` submodule
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

BASE_DIR = Path(__file__).resolve().parent.parent
CHECKER_SOURCE = BASE_DIR / "GeneratedNPDChecker.cpp"
CHECKER_LIBRARY = BASE_DIR / "libNPDChecker.so"
LINUX_SUBMODULE = BASE_DIR / "linux"
DEFAULT_RESULTS_DIR = BASE_DIR / "analysis_results"
CHECKER_NAME = "squire.NPDChecker"


@dataclass
class AnalysisSummary:
    """Structured record for a single kernel revision analysis."""
    tag: str
    warnings: Set[str]
    warnings_text: Path
    warnings_json: Path
    log_dir: Path


class CommandError(RuntimeError):
    """Raised on non-zero subprocess return codes with captured output."""
    def __init__(self, message: str, returncode: int, stdout: str | None, stderr: str | None):
        super().__init__(message)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def run_command(
    cmd: Sequence[object],
    *,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    capture_output: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Wrapper around subprocess.run that prints the command and optionally raises on failure."""
    cmd_str = [str(part) for part in cmd]
    print(f"$ {' '.join(cmd_str)}", flush=True)
    result = subprocess.run(
        cmd_str,
        cwd=str(cwd) if cwd else None,
        env=env,
        check=False,
        text=True,
        capture_output=capture_output,
    )
    if check and result.returncode != 0:
        raise CommandError(
            message=f"Command failed with exit code {result.returncode}: {' '.join(cmd_str)}",
            returncode=result.returncode,
            stdout=result.stdout if capture_output else None,
            stderr=result.stderr if capture_output else None,
        )
    return result


def ensure_linux_submodule() -> None:
    """Initialize and/or update the linux submodule."""
    if LINUX_SUBMODULE.exists():
        return
    print("[setup] initializing linux submodule …")
    run_command(["git", "submodule", "update", "--init", "--recursive", "linux"], cwd=BASE_DIR)


def git(
    repo: Path,
    args: Sequence[object],
    *,
    capture_output: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Run a git command inside the given repository."""
    return run_command(
        ["git", *args],
        cwd=repo,
        capture_output=capture_output,
        check=check,
    )


def build_checker(force: bool = False) -> Path:
    """Compile (or reuse) the custom CSA checker shared object."""
    if not CHECKER_SOURCE.exists():
        raise FileNotFoundError(f"Checker source not found: {CHECKER_SOURCE}")

    rebuild_needed = (
        force
        or not CHECKER_LIBRARY.exists()
        or CHECKER_LIBRARY.stat().st_mtime < CHECKER_SOURCE.stat().st_mtime
    )

    if rebuild_needed:
        print("[build] compiling CSA checker …")
        run_command(
            [
                "clang++",
                "-fPIC",
                "-shared",
                "-std=c++17",
                "-I",
                "/usr/include",
                str(CHECKER_SOURCE),
                "-o",
                str(CHECKER_LIBRARY),
            ]
        )
    else:
        print(f"[build] reusing existing checker: {CHECKER_LIBRARY}")

    return CHECKER_LIBRARY.resolve()


def run_smoke_tests(checker_path: Path) -> None:
    """Run quick local tests in test/pre and test/post to ensure the checker is wired up."""
    print("[smoke] running analyzer on local fixtures …")
    test_root = BASE_DIR / "test"
    if not test_root.exists():
        raise FileNotFoundError("Missing test fixtures directory 'test/'.")
    for variant in ("pre", "post"):
        src = test_root / variant / "file.c"
        if not src.exists():
            raise FileNotFoundError(f"Missing smoke test source: {src}")
        print(f"[smoke] analyzing {src}")
        run_command(
            [
                "clang",
                "--analyze",
                "-Xclang",
                "-load",
                "-Xclang",
                str(checker_path),
                "-Xclang",
                f"-analyzer-checker={CHECKER_NAME}",
                "-Wno-everything",
                str(src),
            ],
            capture_output=True,
        )


def find_compile_db_tool() -> str:
    """Locate intercept-build or bear; prefer intercept-build."""
    for tool in ("intercept-build", "bear"):
        if shutil.which(tool):
            return tool
    raise RuntimeError(
        "Neither 'intercept-build' nor 'bear' was found in PATH. "
        "Install clang-tools or bear to capture compile_commands.json."
    )


def sanitize_for_filename(fragment: str) -> str:
    """Create a filesystem-safe token from a path-like fragment."""
    return (
        fragment.replace("/", "__")
        .replace("\\", "__")
        .replace(":", "_")
        .replace(" ", "_")
    )


def ensure_kernel_config(repo: Path, arch: str, defconfig: str, jobs: int) -> None:
    """Run make defconfig (after mrproper) to produce a clean configuration."""
    env = os.environ.copy()
    env["ARCH"] = arch
    # Use gcc for building (more compatible with older kernels)
    # We'll use clang only for static analysis
    run_command(["make", "mrproper"], cwd=repo, env=env)
    run_command(["make", f"-j{jobs}", defconfig], cwd=repo, env=env)


def generate_compile_commands(
    repo: Path,
    arch: str,
    jobs: int,
    target: str,
    tool: str,
) -> Path:
    """Invoke intercept-build or bear to capture compile commands."""
    env = os.environ.copy()
    env["ARCH"] = arch
    # Use gcc for building to avoid compatibility issues with older kernels

    cdb_path = repo / "compile_commands.json"
    if cdb_path.exists():
        cdb_path.unlink()

    if tool == "intercept-build":
        cmd = [
            "intercept-build",
            "--cdb",
            str(cdb_path),
            "make",
            f"-j{jobs}",
            f"ARCH={arch}",
            target,
        ]
    else:  # bear
        cmd = [
            "bear",
            "--cdb",
            str(cdb_path),
            "--",
            "make",
            f"-j{jobs}",
            f"ARCH={arch}",
            target,
        ]
    run_command(cmd, cwd=repo, env=env)

    if not cdb_path.exists():
        raise RuntimeError("Failed to create compile_commands.json; check build tool output.")
    return cdb_path


def extract_warnings(
    diagnostic_text: str,
    repo_root: Path,
    entry_directory: Path,
    pattern: re.Pattern[str],
) -> List[Dict[str, object]]:
    """Parse analyzer diagnostics for our checker and normalize paths."""
    warnings: List[Dict[str, object]] = []
    if not diagnostic_text:
        return warnings

    repo_root_resolved = repo_root.resolve(strict=False)
    entry_dir_resolved = entry_directory.resolve(strict=False)

    for line in diagnostic_text.splitlines():
        if "Possible NULL dereference" not in line:
            continue
        match = pattern.match(line.strip())
        if not match:
            continue

        raw_path = Path(match.group("path"))
        if not raw_path.is_absolute():
            abs_path = (entry_dir_resolved / raw_path).resolve(strict=False)
        else:
            abs_path = raw_path.resolve(strict=False)

        try:
            rel_path = abs_path.relative_to(repo_root_resolved)
        except ValueError:
            rel_path = abs_path

        message = match.group("message").strip()
        severity = match.group("severity")
        key = f"{rel_path}:{match.group('line')}:{message}"

        warnings.append(
            {
                "file": str(rel_path),
                "line": int(match.group("line")),
                "column": int(match.group("col")),
                "severity": severity,
                "message": message,
                "key": key,
                "raw": line.strip(),
            }
        )
    return warnings


def run_static_analyzer(
    repo: Path,
    compile_commands: Path,
    checker_so: Path,
    tag: str,
    limit: Optional[int],
    results_dir: Path,
) -> AnalysisSummary:
    """Replay compile commands with clang --analyze and collect diagnostics."""
    print(f"[analyze:{tag}] using compile_commands: {compile_commands}")
    data = json.loads(compile_commands.read_text())
    total_units = len(data)
    print(f"[analyze:{tag}] total compilation units in database: {total_units}")

    logs_dir = results_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    pattern = re.compile(
        r"^(?P<path>[^:\n]+):(?P<line>\d+):(?P<col>\d+):\s+"
        r"(?P<severity>warning|error):\s+(?P<message>Possible NULL dereference.*)$"
    )

    processed = 0
    diagnostics: List[Dict[str, object]] = []
    warning_keys: Set[str] = set()

    for idx, entry in enumerate(data):
        if limit is not None and processed >= limit:
            break

        file_path = entry.get("file")
        if not file_path:
            continue
        if not file_path.endswith((".c", ".cc", ".cpp")):
            continue

        directory = Path(entry.get("directory", str(repo)))
        arguments: List[str]
        if "arguments" in entry and entry["arguments"]:
            arguments = list(entry["arguments"])
        else:
            arguments = shlex.split(entry["command"])

        if not arguments:
            continue

        compiler = arguments[0]
        filtered_args: List[str] = [compiler, "--analyze"]
        filtered_args += [
            "-Xclang", "-load", "-Xclang", str(checker_so),
            "-Xclang", f"-analyzer-checker={CHECKER_NAME}",
            "-fno-color-diagnostics",
        ]

        skip_next = False
        for arg in arguments[1:]:
            if skip_next:
                skip_next = False
                continue
            if arg == "-c":
                continue
            if arg == "-o":
                skip_next = True
                continue
            if arg.startswith("-o"):
                continue
            filtered_args.append(arg)

        result = run_command(
            filtered_args,
            cwd=directory,
            capture_output=True,
            check=False,
        )

        combined_output = ""
        if result.stdout:
            combined_output += result.stdout
        if result.stderr:
            combined_output += result.stderr

        parsed = extract_warnings(combined_output, repo, directory, pattern)
        if parsed:
            processed_file = Path(file_path)
            try:
                rel_file = processed_file.resolve().relative_to(repo.resolve())
            except Exception:
                rel_file = processed_file
            log_name = f"{idx:05d}_{sanitize_for_filename(str(rel_file))}.log"
            (logs_dir / log_name).write_text(combined_output)

            for diag in parsed:
                if diag["key"] not in warning_keys:
                    warning_keys.add(diag["key"])
                    diagnostics.append(diag)

        processed += 1
        if processed % 50 == 0 or parsed:
            print(
                f"[analyze:{tag}] processed {processed} units "
                f"(warnings collected: {len(warning_keys)})",
                flush=True,
            )

    diagnostics.sort(key=lambda item: item["key"])
    warnings_txt = results_dir / "npd_warnings.txt"
    warnings_json = results_dir / "npd_warnings.json"

    warnings_txt.write_text("\n".join(sorted(warning_keys)) + ("\n" if warning_keys else ""))
    warnings_json.write_text(json.dumps(diagnostics, indent=2))

    print(
        f"[analyze:{tag}] completed {processed} units; "
        f"{len(warning_keys)} unique warnings recorded."
    )

    return AnalysisSummary(
        tag=tag,
        warnings=warning_keys,
        warnings_text=warnings_txt,
        warnings_json=warnings_json,
        log_dir=logs_dir,
    )


def analyze_kernel_revision(
    repo: Path,
    tag: str,
    checker_so: Path,
    arch: str,
    defconfig: str,
    jobs: int,
    make_target: str,
    limit: Optional[int],
    results_root: Path,
    reuse_cdb: bool,
    keep_cdb: bool,
    build_tool: str,
) -> AnalysisSummary:
    """Checkout a specific kernel tag, generate compile DB, run analyzer, and archive results."""
    print(f"\n[kernel] ===== Analyzing Linux {tag} =====")
    git(repo, ["checkout", tag])
    git(repo, ["reset", "--hard", "HEAD"])
    git(repo, ["clean", "-fdx"])

    per_tag_results = results_root / tag.replace("/", "_")
    per_tag_results.mkdir(parents=True, exist_ok=True)

    stored_cdb = per_tag_results / "compile_commands.json"
    repo_cdb = repo / "compile_commands.json"

    if reuse_cdb and stored_cdb.exists():
        print(f"[kernel:{tag}] reusing previously captured compile_commands.json")
        shutil.copy2(stored_cdb, repo_cdb)
    else:
        print(f"[kernel:{tag}] configuring kernel ({defconfig})")
        ensure_kernel_config(repo, arch, defconfig, jobs)
        print(f"[kernel:{tag}] capturing compile commands via {build_tool}")
        generate_compile_commands(repo, arch, jobs, make_target, build_tool)
        shutil.copy2(repo_cdb, stored_cdb)

    summary = run_static_analyzer(
        repo=repo,
        compile_commands=repo_cdb,
        checker_so=checker_so,
        tag=tag,
        limit=limit,
        results_dir=per_tag_results,
    )

    if not keep_cdb and repo_cdb.exists():
        repo_cdb.unlink()

    return summary


def restore_linux_repo(
    repo: Path,
    original_branch: Optional[str],
    original_commit: str,
) -> None:
    """Reset the linux submodule to its initial state."""
    print("\n[kernel] restoring linux submodule to original state …")
    git(repo, ["clean", "-fdx"])
    git(repo, ["checkout", original_commit])
    if original_branch and original_branch != "HEAD":
        git(repo, ["checkout", original_branch])
        git(repo, ["reset", "--hard", original_commit])
    git(repo, ["clean", "-fdx"])


def compare_summaries(
    summaries: Dict[str, AnalysisSummary],
    baseline_tag: str,
    latest_tag: str,
    results_root: Path,
) -> None:
    """Write comparison artifacts highlighting fixed and remaining warnings."""
    if baseline_tag not in summaries or latest_tag not in summaries:
        print("[compare] insufficient data to produce comparison.")
        return

    baseline = summaries[baseline_tag]
    latest = summaries[latest_tag]

    fixed = sorted(baseline.warnings - latest.warnings)
    persistent = sorted(baseline.warnings & latest.warnings)
    regressions = sorted(latest.warnings - baseline.warnings)

    comparison_md = results_root / f"comparison_{baseline_tag}_vs_{latest_tag}.md"
    with comparison_md.open("w") as fh:
        fh.write(f"# Checker comparison: {baseline_tag} → {latest_tag}\n\n")
        fh.write(f"* Baseline warnings ({baseline_tag}): {len(baseline.warnings)}\n")
        fh.write(f"* Latest warnings ({latest_tag}): {len(latest.warnings)}\n")
        fh.write(f"* Fixed warnings: {len(fixed)}\n")
        fh.write(f"* Persistent warnings: {len(persistent)}\n")
        fh.write(f"* New warnings / regressions: {len(regressions)}\n\n")

        def dump_section(title: str, items: List[str]) -> None:
            fh.write(f"## {title} ({len(items)})\n\n")
            if not items:
                fh.write("_None_\n\n")
                return
            for item in items:
                fh.write(f"- `{item}`\n")
            fh.write("\n")

        dump_section(f"Fixed warnings (present in {baseline_tag} only)", fixed)
        dump_section(f"Warnings persisting into {latest_tag}", persistent)
        dump_section(f"Regressions (new in {latest_tag})", regressions)

        fh.write("## Artifacts\n\n")
        fh.write(f"- {baseline_tag} warnings (text): {baseline.warnings_text}\n")
        fh.write(f"- {baseline_tag} warnings (JSON): {baseline.warnings_json}\n")
        fh.write(f"- {latest_tag} warnings (text): {latest.warnings_text}\n")
        fh.write(f"- {latest_tag} warnings (JSON): {latest.warnings_json}\n")

    print(
        f"[compare] comparison written to {comparison_md} "
        f"(fixed: {len(fixed)}, persistent: {len(persistent)}, regressions: {len(regressions)})"
    )


def run_kernel_workflow(args: argparse.Namespace, checker_path: Path) -> None:
    """Top-level orchestration for Linux kernel analysis."""
    ensure_linux_submodule()
    if not LINUX_SUBMODULE.exists():
        raise FileNotFoundError("linux/ submodule is missing after initialization attempt.")

    git(LINUX_SUBMODULE, ["fetch", "--tags"])

    original_commit = git(
        LINUX_SUBMODULE,
        ["rev-parse", "HEAD"],
        capture_output=True,
    ).stdout.strip()
    original_branch = git(
        LINUX_SUBMODULE,
        ["rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
    ).stdout.strip()

    results_root = args.output_dir.resolve()
    results_root.mkdir(parents=True, exist_ok=True)

    summaries: Dict[str, AnalysisSummary] = {}
    build_tool = find_compile_db_tool()

    try:
        for tag in args.tags:
            summary = analyze_kernel_revision(
                repo=LINUX_SUBMODULE,
                tag=tag,
                checker_so=checker_path,
                arch=args.arch,
                defconfig=args.defconfig,
                jobs=args.jobs,
                make_target=args.make_target,
                limit=args.analysis_limit,
                results_root=results_root,
                reuse_cdb=args.reuse_cdb,
                keep_cdb=args.keep_cdb,
                build_tool=build_tool,
            )
            summaries[tag] = summary
    finally:
        restore_linux_repo(LINUX_SUBMODULE, original_branch, original_commit)

    if len(args.tags) >= 2:
        compare_summaries(
            summaries,
            baseline_tag=args.tags[0],
            latest_tag=args.tags[-1],
            results_root=results_root,
        )


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Command-line interface."""
    parser = argparse.ArgumentParser(
        description="Build the custom CSA checker and run kernel analyses."
    )
    parser.add_argument(
        "--mode",
        choices=["kernel", "smoke"],
        default="kernel",
        help="Run the full kernel workflow (default) or local smoke tests.",
    )
    parser.add_argument(
        "--tags",
        nargs="+",
        default=["v5.9", "v5.17"],
        help="Kernel tags/commits to analyze in order (baseline → latest).",
    )
    parser.add_argument(
        "--arch",
        default="x86_64",
        help="ARCH passed to make (default: x86_64).",
    )
    parser.add_argument(
        "--defconfig",
        default="defconfig",
        help="Kernel defconfig target (default: defconfig).",
    )
    parser.add_argument(
        "--make-target",
        default="vmlinux",
        help="Primary make target to build while capturing compile commands (default: vmlinux).",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=os.cpu_count() or 4,
        help="Parallelism for make (default: number of CPUs).",
    )
    parser.add_argument(
        "--analysis-limit",
        type=int,
        default=None,
        help="Optional cap on the number of translation units analyzed per tag (for quick trials).",
    )
    parser.add_argument(
        "--reuse-cdb",
        action="store_true",
        help="Reuse stored compile_commands.json per tag if available.",
    )
    parser.add_argument(
        "--keep-cdb",
        action="store_true",
        help="Do not delete compile_commands.json from the repo after analysis.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
        help="Destination directory for analysis artifacts.",
    )
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Force recompilation of the checker shared object.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    try:
        checker_path = build_checker(force=args.force_rebuild)
        if args.mode == "smoke":
            run_smoke_tests(checker_path)
        else:
            run_kernel_workflow(args, checker_path)
    except CommandError as exc:
        if exc.stdout:
            sys.stderr.write(exc.stdout)
        if exc.stderr:
            sys.stderr.write(exc.stderr)
        sys.stderr.write(f"\nerror: {exc}\n")
        sys.exit(exc.returncode or 1)
    except Exception as exc:
        sys.stderr.write(f"\nUnhandled error: {exc}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
