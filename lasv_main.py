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
import semver
import sys
import yaml
from enum import Enum
from lasv import crates


class ChangeType(Enum):
    MAJOR = "MAJOR"
    MINOR = "minor"


class LasvContext:
    """Encapsulates lasv context data with load/save functionality."""

    def __init__(self, filename="lasv.yaml"):
        self.filename = filename
        self.data = {}

    def load(self):
        """Load context from YAML file."""
        if os.path.exists(self.filename):
            with open(self.filename, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                self.data = loaded if loaded else {}
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

    def emit_change(self, crate: str, version: str, analyzer: str,
                   severity: ChangeType, line: int, col: int, description: str):
        """
        Record a detected change.
        severity: ChangeType.MAJOR or ChangeType.MINOR
        line, col: location in the new file
        description: explanation of the change
        """
        print(f"{severity.value} ({line}, {col}): {description}")

        # Ensure all required parent keys exist before storing anything new.
        # Up to release must already exist as it was created during fetching.
        if 'diagnosis' not in self.data['crates'][crate]['releases'][version]:
            self.data['crates'][crate]['releases'][version]['diagnosis'] = {}
        if analyzer not in self.data['crates'][crate]['releases'] \
                                    [version]['diagnosis']:
            self.data['crates'][crate]['releases'][version] \
                     ['diagnosis'][analyzer] = {'changes': []}

        changes = self.data['crates'][crate]['releases'][version] \
                           ['diagnosis'][analyzer]['changes']
        changes.append({
            'severity': severity.value,
            'line': line,
            'col': col,
            'description': description
        })

    def finish_diagnosis(self, crate: str, prev_version: str,
                        curr_version: str, analyzer: str) -> None:
        """
        Computes compliance based on stored changes and version bump.
        """
        try:
            v1 = semver.Version.parse(prev_version)
            v2 = semver.Version.parse(curr_version)
        except ValueError:
            # Fallback for non-semver versions? Or raise?
            # For now assume compliance cannot be determined if not semver.
            print(f"Non-semver version found: {prev_version} -> {curr_version}")
            raise

        diag = self.data['crates'][crate]['releases'][curr_version] \
                        ['diagnosis'][analyzer]
        changes = diag['changes']

        major_changes = [c for c in changes if c['severity'] == "MAJOR"]
        minor_changes = [c for c in changes if c['severity'] == "minor"]

        is_major_bump = v2.major > v1.major
        is_minor_bump = v2.minor > v1.minor and v2.major == v1.major
        is_patch_bump = v2.patch > v1.patch and v2.major == v1.major \
                        and v2.minor == v1.minor

        if v1.major == 0:
            # 0.x.y semantic versioning:
            # - minor bump acts as MAJOR bump (breaking changes)
            # - patch bump acts as minor bump (backwards compatible additions)
            # - there is no patch level equivalent (all changes are either min or maj)
            is_major_bump = is_minor_bump or is_major_bump # 0.1 -> 0.2 is MAJOR
            is_minor_bump = is_patch_bump # 0.1.1 -> 0.1.2 is minor
            is_patch_bump = False # No patch level in 0.x

        compliant = True
        reason = ""

        if is_major_bump:
            if not major_changes:
                compliant = False
                reason = "Major version bump but no MAJOR changes found."
        elif is_minor_bump:
            if major_changes:
                compliant = False
                reason = "Minor version bump but MAJOR changes found."
            elif not minor_changes:
                # This is debatable, but user said:
                # "E.g., finding only minor changes in a major bump will be declared non-compliant."
                # Does minor bump require minor changes? Usually yes, otherwise it's a patch.
                # Assuming yes for strict compliance.
                compliant = (v1.major == 0) # For 0.x, minor/patch bumps are looser?
                # Actually, user logic implies we expect changes matching the bump.
                # If it's a minor bump (0.x patch), we expect minor changes.
                # If we have 0 changes, it's non-compliant?
                # Let's stick to the previous logic but with remapped bumps.
                compliant = False
                reason = "Minor version bump but no minor changes found."
        elif is_patch_bump:
             # Should not happen for 0.x based on above remapping
            if major_changes or minor_changes:
                compliant = False
                reason = "Patch version bump but API changes found."

        diag['compliant'] = compliant
        if not compliant:
            diag['noncompliance'] = reason
            print(f"      [{analyzer}: NON-COMPLIANT] {reason}")
        else:
            print(f"      [{analyzer}: COMPLIANT]")

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


def lasv_main():
    """
    Load context if it exists. Obtain from it the 'crates' list.
    If a crate name is given as argument, process only that crate.
    """
    context = LasvContext()
    data = context.load()

    target_crate = sys.argv[1] if len(sys.argv) > 1 else None

    if target_crate:
        print(f"Processing only crate: {target_crate}")
    else:
        print("Processing all crates.")
        crates.list(context)

    crates.process(context, target_crate)

# Program entry point
if __name__ == "__main__":
    lasv_main()