#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This program without arguments list all alr crates and,
for each one, obtains its releases, if there are at least two of them.
Then, for each pair of consecutive releases, it queries a LLM to print
all interface changes, classifying them as minor- or major-number changes.

Intermediate (and final) results are cached in a "lasv.yaml" file.

Data is outputted to a YAML file for further processing.

Input arguments: optional crate name to process only that crate.
"""


import os
import sys
import argparse
from dataclasses import dataclass
from enum import Enum

import semver
import yaml

from lasv import crates


class ChangeType(Enum):
    """Enumeration for the type of change."""
    MAJOR = "MAJOR"
    MINOR = "minor"


class Compliance(Enum):
    """Enumeration for compliance status."""
    STRICT = "strict"
    LAX = "lax"
    NO = "no"
    ERROR = "error" # Error during analysis


class BumpType(Enum):
    """Enumeration for version bump types."""
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"
    NONE = "none"


@dataclass
class ChangeInfo:
    """Information about a detected change."""
    severity: ChangeType
    line: int
    col: int
    description: str
    filename: str = ""  # Optional filename where the change occurred (new version)
    old_filename: str = ""  # Optional filename for the old version (for diffs)


class LasvContext:
    """Encapsulates lasv context data with load/save functionality."""

    def __init__(self, filename="lasv.yaml"):
        self.filename = filename
        self.data = {}
        self.model = None
        self.full = False

    def load(self):
        """Load context from YAML file."""
        if os.path.exists(self.filename):
            with open(self.filename, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                self.data = loaded if loaded else {}

        if 'crates' not in self.data:
            self.data['crates'] = {}

        return self.data

    def clear_diagnosis(self, crate: str) -> None:
        """Remove all diagnosis data for a given crate."""
        if 'crates' in self.data and crate in self.data['crates']:
            crate_data = self.data['crates'][crate]
            if 'releases' in crate_data:
                for release in crate_data['releases'].values():
                    if 'diagnosis' in release:
                        del release['diagnosis']
                self.save()

    def start_diagnosis(self, crate: str, version: str, analyzer: str) -> None:
        """Initialize diagnosis structure for a specific analyzer."""
        if 'crates' not in self.data:
            self.data['crates'] = {}
        if crate not in self.data['crates']:
            self.data['crates'][crate] = {}
        if 'releases' not in self.data['crates'][crate]:
            self.data['crates'][crate]['releases'] = {}
        if version not in self.data['crates'][crate]['releases']:
            self.data['crates'][crate]['releases'][version] = {}

        rel_data = self.data['crates'][crate]['releases'][version]
        if 'diagnosis' not in rel_data:
            rel_data['diagnosis'] = {}

        rel_data['diagnosis'][analyzer] = {'changes': []}
        self.save()

    def emit_change(self, crate: str, version: str, analyzer: str, change: ChangeInfo):
        """
        Record a detected change.
        """
        print(f"            {change.severity.value} ({change.line}, {change.col}): {change.description}")

        # Ensure all required parent keys exist before storing anything new.
        # Up to release must already exist as it was created during fetching.
        if 'diagnosis' not in self.data['crates'][crate]['releases'][version]:
            self.data['crates'][crate]['releases'][version]['diagnosis'] = {}
        if analyzer not in self.data['crates'][crate]['releases'][version]['diagnosis']:
            self.data['crates'][crate]['releases'][version]['diagnosis'][analyzer] = {'changes': []}

        changes = self.data['crates'][crate]['releases'][version]['diagnosis'][analyzer]['changes']
        change_dict = {
            'severity': change.severity.value,
            'line': change.line,
            'col': change.col,
            'description': change.description
        }
        if change.filename:
            change_dict['filename'] = change.filename
        if change.old_filename:
            change_dict['old_filename'] = change.old_filename
        changes.append(change_dict)

    def finish_diagnosis(self, crate: str, prev_version: str,
                        curr_version: str, analyzer: str) -> None:
        """
        Computes compliance based on stored changes and version bump.
        """
        try:
            v1 = semver.Version.parse(prev_version)
            v2 = semver.Version.parse(curr_version)
        except ValueError:
            print(f"Non-semver version found: {prev_version} -> {curr_version}")
            raise

        diag = self.data['crates'][crate]['releases'][curr_version]['diagnosis'][analyzer]
        major_changes = [c for c in diag['changes'] if c['severity'] == "MAJOR"]
        minor_changes = [c for c in diag['changes'] if c['severity'] == "minor"]

        bump_type = _detect_version_bump(v1, v2)
        compliance, reason = _calculate_compliance(
            bump_type, major_changes, minor_changes, analyzer
        )

        diag['compliant'] = compliance.value
        if compliance == Compliance.NO:
            diag['noncompliance'] = reason
            print(f"      [{analyzer}: NON-COMPLIANT] {reason}")
        elif compliance == Compliance.LAX:
            diag['noncompliance'] = reason
            print(f"      [{analyzer}: COMPLIANT (lax)] {reason}")
        else:  # strict
            if 'noncompliance' in diag:
                del diag['noncompliance']
            print(f"      [{analyzer}: COMPLIANT (strict)]")

        self.save()


    def finish_diagnosis_with_error(self, crate: str, curr_version: str,
                                   analyzer: str, error_message: str) -> None:
        """
        Mark diagnosis as errored with a message.
        """
        diag = self.data['crates'][crate]['releases'][curr_version] \
                        ['diagnosis'][analyzer]
        diag['compliant'] = Compliance.ERROR.value
        diag['error_message'] = error_message
        print(f"      [{analyzer}: ERROR] {error_message}")
        self.save()


    def save(self):
        """Save context to YAML file, with backup on failure."""
        old_filename = self.filename + ".old"
        if os.path.exists(self.filename):
            os.rename(self.filename, old_filename)

        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                yaml.safe_dump(self.data, f)
        except Exception as e:
            if os.path.exists(old_filename):
                os.rename(old_filename, self.filename)  # Restore the old file
            raise e


def _detect_version_bump(v1: semver.Version, v2: semver.Version) -> BumpType:
    """
    Detect the type of version bump between two versions.
    Returns a BumpType enum value.
    """
    is_major_bump = v2.major > v1.major
    is_minor_bump = v2.minor > v1.minor and v2.major == v1.major
    is_patch_bump = v2.patch > v1.patch and v2.major == v1.major and v2.minor == v1.minor

    result = BumpType.NONE

    if v1.major == 0:
        # 0.x.y semantic versioning:
        # - minor bump acts as MAJOR bump (breaking changes)
        # - patch bump acts as minor bump (backwards compatible additions)
        if is_minor_bump or is_major_bump:
            result = BumpType.MAJOR
        elif is_patch_bump:
            result = BumpType.MINOR
    else:
        if is_major_bump:
            result = BumpType.MAJOR
        elif is_minor_bump:
            result = BumpType.MINOR
        elif is_patch_bump:
            result = BumpType.PATCH

    return result


def _calculate_compliance(
    bump_type: BumpType,
    major_changes: list,
    minor_changes: list,
    analyzer: str
) -> tuple[Compliance, str]:
    """
    Calculate compliance status based on version bump type and detected changes.
    Returns (compliance, reason).
    """
    compliance = Compliance.STRICT
    reason = ""

    if bump_type == BumpType.MAJOR:
        if not major_changes and analyzer != 'files':
            compliance = Compliance.LAX
            reason = "Major version bump but no MAJOR changes found."
    elif bump_type == BumpType.MINOR:
        if major_changes:
            compliance = Compliance.NO
            reason = "Minor version bump but MAJOR changes found."
        elif not minor_changes and analyzer != 'files':
            compliance = Compliance.LAX
            reason = "Minor version bump but no minor changes found."
    elif bump_type == BumpType.PATCH:
        if major_changes or minor_changes:
            compliance = Compliance.NO
            reason = "Patch version bump but API changes found."

    return compliance, reason


def lasv_main():
    """
    Load context if it exists. Obtain from it the 'crates' list.
    If a crate name is given as argument, process only that crate.
    """
    parser = argparse.ArgumentParser(
        description="Version compliance analysis using LLMs."
    )
    parser.add_argument(
        "crate",
        nargs="?",
        help="Crate name to process (optional).",
    )
    parser.add_argument(
        "--model",
        help="LLM model to use for analysis (optional)."
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Only list crates without performing pair detection and analysis."
    )
    parser.add_argument(
        "--redo",
        action="store_true",
        help="Remove existing diagnosis and redo it."
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Enable full analysis mode."
    )
    args = parser.parse_args()

    if args.model and not os.environ.get("OPENROUTER_API_KEY"):
        print("Error: --model requires OPENROUTER_API_KEY to be set.")
        sys.exit(1)

    context = LasvContext()
    context.load()

    # Set the model in context if provided
    if args.model:
        context.model = args.model
    context.full = args.full

    if args.crate:
        print(f"Processing only crate: {args.crate}")
    else:
        print("Processing all crates.")
        crates.list_crates(context)

    crates.process(context, args.crate, list_only=args.list_only, redo=args.redo)
    context.save()

# Program entry point
if __name__ == "__main__":
    lasv_main()
