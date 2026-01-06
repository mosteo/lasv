#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compare two consecutive versions of a crate using meld.

This script takes a crate name and version, identifies the previous version
from the releases folder on disk, and launches meld to compare the two version folders.

Usage:
    python lasv_diff.py <crate_name> <version>

Example:
    python lasv_diff.py hello 1.0.2
"""

import argparse
import os
import re
import subprocess
import sys
from typing import Optional, List, Tuple


def parse_version(version_str: str) -> Tuple[int, ...]:
    """
    Parse a version string into a tuple of integers for comparison.
    Handles versions like '1.0.2', '0.1.0', etc.
    """
    try:
        return tuple(int(x) for x in version_str.split('.'))
    except (ValueError, AttributeError):
        return (0,)


def get_versions_from_disk(crate: str) -> List[Tuple[str, str]]:
    """
    Get all versions of a crate from the releases folder on disk.
    Returns a list of tuples: (version_string, full_path)
    Sorted by version in ascending order.
    """
    releases_dir = os.path.join("releases", crate)

    if not os.path.exists(releases_dir):
        return []

    versions = []
    # Pattern: {crate}_{version}_{hash}
    pattern = re.compile(rf"^{re.escape(crate)}_(.+?)_[a-f0-9]+$")

    for entry in os.listdir(releases_dir):
        full_path = os.path.join(releases_dir, entry)
        if os.path.isdir(full_path):
            match = pattern.match(entry)
            if match:
                version = match.group(1)
                versions.append((version, full_path))

    # Sort by version
    versions.sort(key=lambda x: parse_version(x[0]))

    return versions


def find_previous_version_on_disk(crate: str, version: str) -> Optional[Tuple[str, str]]:
    """
    Find the previous version of a crate before the given version,
    using only information from the releases folder on disk.
    Returns a tuple (version_string, full_path) or None if not found.
    """
    versions = get_versions_from_disk(crate)

    if not versions:
        return None

    target_version_tuple = parse_version(version)

    # Find all versions less than the target version
    previous_versions = [
        (v, p) for v, p in versions
        if parse_version(v) < target_version_tuple
    ]

    if not previous_versions:
        return None

    # Return the highest version that's still less than target
    return previous_versions[-1]


def find_version_path_on_disk(crate: str, version: str) -> Optional[str]:
    """
    Find the full path for a specific version on disk.
    Returns the path or None if not found.
    """
    versions = get_versions_from_disk(crate)

    for v, path in versions:
        if v == version:
            return path

    return None


def main():
    """Main entry point for lasv_diff."""
    parser = argparse.ArgumentParser(
        description="Compare two consecutive versions of a crate using meld."
    )
    parser.add_argument(
        "crate",
        help="Name of the crate to compare."
    )
    parser.add_argument(
        "version",
        help="Version to compare (will find the previous version automatically)."
    )
    args = parser.parse_args()

    crate_name = args.crate
    current_version = args.version

    # Check if releases folder exists
    releases_dir = os.path.join("releases", crate_name)
    if not os.path.exists(releases_dir):
        print(f"Error: Releases folder not found: {releases_dir}")
        print(f"No releases for crate '{crate_name}' found on disk.")
        sys.exit(1)

    # Find the current version path on disk
    print(f"Looking for {crate_name} version {current_version} on disk...")
    curr_path = find_version_path_on_disk(crate_name, current_version)

    if curr_path is None:
        print(f"Error: Version {current_version} not found on disk for crate '{crate_name}'.")
        print(f"Available versions:")
        versions = get_versions_from_disk(crate_name)
        for v, _ in versions:
            print(f"  - {v}")
        sys.exit(1)

    print(f"Found current version: {curr_path}")

    # Find the previous version
    print(f"Finding previous version for {crate_name} < {current_version}...")
    prev_result = find_previous_version_on_disk(crate_name, current_version)

    if prev_result is None:
        print(f"Error: No previous version found on disk for {crate_name} < {current_version}.")
        sys.exit(1)

    previous_version, prev_path = prev_result
    print(f"Found previous version: {previous_version}")

    # Launch meld
    print(f"\nLaunching meld to compare:")
    print(f"  Previous: {prev_path}")
    print(f"  Current:  {curr_path}")
    print()

    try:
        subprocess.run(["meld", prev_path, curr_path], check=True)
    except FileNotFoundError:
        print("Error: 'meld' command not found.")
        print("Please install meld: sudo apt install meld")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error running meld: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
