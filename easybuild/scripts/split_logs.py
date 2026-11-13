#!/usr/bin/env python
##
# Copyright 2016-2026 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# https://github.com/easybuilders/easybuild
#
# EasyBuild is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation v2.
#
# EasyBuild is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
# the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with EasyBuild. If not, see <http://www.gnu.org/licenses/>.
#
"""
Script to split an EasyBuild build log into steps, with and without debug output

Authors:

* Alan O'Cais (Ghent University)
"""

import argparse
import bz2
import re
from pathlib import Path
from typing import Dict, Optional, Union


# regex for start of log event
LOG_START_RE = re.compile(
    r"^==\s+(?P<timestamp>\d{4}-\d{2}-\d{2} [\d:,]+)\s+"
    r"(?P<file>[^:]+):(?P<line>\d+)\s+"
    r"(?P<level>DEBUG|INFO|WARNING|ERROR)\s*"
    r"(?P<msg>.*)$"
)

# regex to capture step name
STEP_RE = re.compile(
    r"easyblock\.py:\d+\s+INFO\s+Starting\s+(?P<step>.+?)\s+step"
)


def safe_name(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", s).strip("_")[:120]


def parse_events(lines):
    current_event = None

    step_counter = 0
    current_step_id = "0000_init"

    for line in lines:
        line = line.rstrip("\n")

        log_start = LOG_START_RE.match(line)

        if log_start:
            if current_event is not None:
                yield current_event

            step_match = STEP_RE.search(line)

            if step_match:
                step_counter += 1
                step_name = safe_name(step_match.group("step"))
                current_step_id = f"{step_counter:04d}_{step_name}"

            current_event = {
                "raw": [line],
                "level": log_start.group("level"),
                "step": current_step_id,
            }

        elif current_event is not None:
            current_event["raw"].append(line)

        else:
            current_event = {
                "raw": [line],
                "level": "UNKNOWN",
                "step": current_step_id,
            }

    if current_event is not None:
        yield current_event


def open_output(path: Path):
    return bz2.open(
        str(path) + ".bz2",
        "wt",
        encoding="utf-8",
    )


def write_event(
    event,
    full_file,
    clean_file,
    step_files: Dict[str, object],
    step_clean_files: Dict[str, object],
    step_dir: Path,
) -> None:
    text = "\n".join(event["raw"]) + "\n"
    step = event["step"]

    # Full output
    full_file.write(text)

    # No-debug full output
    if event["level"] != "DEBUG":
        clean_file.write(text)

    # Step output containing debug
    if step not in step_files:
        step_files[step] = open_output(
            step_dir / f"{step}_step_with_debug.log"
        )

    step_files[step].write(text)

    # Step output without debug
    if event["level"] != "DEBUG":
        if step not in step_clean_files:
            step_clean_files[step] = open_output(
                step_dir / f"{step}_step.log"
            )

        step_clean_files[step].write(text)


def process_log(
    lines,
    outdir: Path,
    include_debug: bool = False,
) -> None:
    outdir.mkdir(parents=True, exist_ok=True)

    step_dir = outdir / "steps"
    step_dir.mkdir(exist_ok=True)

    # Always create the no-debug full output.
    clean_file = open_output(outdir / "full.log")

    # Only create the full debug output when requested.
    full_file = None

    if include_debug:
        full_file = open_output(outdir / "full_with_debug.log")

    step_files: Dict[str, object] = {}
    step_clean_files: Dict[str, object] = {}

    try:
        for event in parse_events(lines):
            if include_debug:
                write_event(
                    event,
                    full_file,
                    clean_file,
                    step_files,
                    step_clean_files,
                    step_dir,
                )
            else:
                text = "\n".join(event["raw"]) + "\n"
                step = event["step"]

                if event["level"] != "DEBUG":
                    clean_file.write(text)

                    if step not in step_clean_files:
                        step_clean_files[step] = open_output(
                            step_dir / f"{step}_step.log"
                        )

                    step_clean_files[step].write(text)

    finally:
        clean_file.close()

        if full_file is not None:
            full_file.close()

        for file in step_files.values():
            file.close()

        for file in step_clean_files.values():
            file.close()


def remove_identical_debug_files(outdir: Path) -> None:
    full_debug = outdir / "full_with_debug.log.bz2"
    full_clean = outdir / "full.log.bz2"

    if full_debug.exists() and full_clean.exists():
        if full_debug.read_bytes() == full_clean.read_bytes():
            full_debug.unlink()

    step_dir = outdir / "steps"

    for clean_file in step_dir.glob("*_step.log.bz2"):
        debug_file = step_dir / (
            clean_file.name[:-len("_step.log.bz2")]
            + "_step_with_debug.log.bz2"
        )

        if debug_file.exists():
            if debug_file.read_bytes() == clean_file.read_bytes():
                debug_file.unlink()


def get_log_name(path: Path) -> str:
    name = path.name

    if name.lower().endswith(".bz2"):
        name = name[:-4]

    if name.lower().endswith(".log"):
        name = name[:-4]

    return name


def main(
    file_path: Union[str, Path],
    output_dir: Optional[Union[str, Path]] = None,
    include_debug: bool = False,
) -> None:
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"Input file does not exist: {path}")

    output_root = Path(output_dir) if output_dir else Path.cwd()

    name = get_log_name(path)
    outdir = output_root / f"{name}_parsed"

    open_func = bz2.open if path.suffix.lower() == ".bz2" else open

    with open_func(
        str(path),
        "rt",
        encoding="utf-8",
        errors="replace",
    ) as file:
        process_log(file, outdir, include_debug=include_debug)

    if include_debug:
        remove_identical_debug_files(outdir)

    print(f"Output written to: {outdir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Parse EasyBuild log files"
    )

    parser.add_argument(
        "file",
        type=Path,
        help="Input log file (.log or .bz2)",
    )

    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        help=(
            "Output directory "
            "(default: <input_name>_parsed in the current directory)"
        ),
    )

    parser.add_argument(
        "--with-debug",
        action="store_true",
        help="Also generate output files containing debug messages",
    )

    args = parser.parse_args()

    main(
        args.file,
        args.output_dir,
        args.with_debug,
    )
