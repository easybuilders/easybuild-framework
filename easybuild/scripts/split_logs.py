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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See
# the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with EasyBuild. If not, see <http://www.gnu.org/licenses/>.
#
"""
Script to split a build log into steps, with and without debug output

Authors:

* Alan O'Cais (Ghent University)
"""

import argparse
import re
import bz2
from pathlib import Path
from collections import defaultdict
# Making this compatible with Python 3.6+
from typing import Dict, List, Optional, Union


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


def parse_lines(lines) -> List[Dict]:
    events = []

    current_event = None

    step_counter = 0
    current_step_id = "0000_init"

    def flush() -> None:
        nonlocal current_event

        if current_event is not None:
            events.append(current_event)
            current_event = None

    for line in lines:
        line = line.rstrip("\n")

        log_start = LOG_START_RE.match(line)

        if log_start:
            step_match = STEP_RE.search(line)

            if step_match:
                step_counter += 1
                step_name = safe_name(step_match.group("step"))
                current_step_id = f"{step_counter:04d}_{step_name}"

            flush()

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

    flush()

    return events


def write_outputs(
    events: List[Dict],
    outdir: Path,
    include_debug: bool = False,
) -> None:
    outdir.mkdir(parents=True, exist_ok=True)

    full = []
    clean = []

    steps_with_debug = defaultdict(list)
    steps_no_debug = defaultdict(list)

    for event in events:
        text = "\n".join(event["raw"])

        full.append(text)
        steps_with_debug[event["step"]].append(text)

        if event["level"] != "DEBUG":
            clean.append(text)
            steps_no_debug[event["step"]].append(text)

    full_no_debug_file = outdir / "full.log"
    full_no_debug_file.write_text(
        "\n".join(clean) + "\n",
        encoding="utf-8",
    )

    if include_debug:
        full_file = outdir / "full_with_debug.log"
        full_file.write_text(
            "\n".join(full) + "\n",
            encoding="utf-8",
        )

        # Don't keep a debug file around if there is no debug output
        if full_file.read_bytes() == full_no_debug_file.read_bytes():
            full_file.unlink()

    step_dir = outdir / "steps"
    step_dir.mkdir(exist_ok=True)

    steps = steps_with_debug.keys() | steps_no_debug.keys()

    for step in sorted(steps):
        no_debug_file = step_dir / f"{step}_step.log"

        no_debug_file.write_text(
            "\n".join(steps_no_debug.get(step, [])) + "\n",
            encoding="utf-8",
        )

        if include_debug:
            with_debug_file = step_dir / f"{step}_step_with_debug.log"

            with_debug_file.write_text(
                "\n".join(steps_with_debug.get(step, [])) + "\n",
                encoding="utf-8",
            )

            if with_debug_file.read_bytes() == no_debug_file.read_bytes():
                with_debug_file.unlink()


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

    # Clean the name by stripping .bz2 and .log extensions
    name = get_log_name(path)

    outdir = output_root / f"{name}_parsed"

    # Choose the correct open function dynamically
    open_func = bz2.open if path.suffix.lower() == ".bz2" else open

    with open_func(
        path,
        "rt",
        encoding="utf-8",
        errors="replace",
    ) as file:
        events = parse_lines(file)

    write_outputs(events, outdir, include_debug=include_debug)

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

    main(args.file, args.output_dir, args.with_debug)
