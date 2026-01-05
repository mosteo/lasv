"""
This module is responsible for handling and comparing different releases of Alire crates.
"""
import json
import os
import re
import shutil
import subprocess
from typing import Optional

from lasv_main import LasvContext, ChangeType
from lasv import specs as specs_module


def get_release_path(crate: str, version: str) -> str:
    """
    Helper to get the local path where a release is stored.
    Downloads it if not present is NOT handled here, it assumes retrieve() was called.
    But we need to know the directory name alure uses.
    """
    # We re-run alr get --dirname to know the folder name.
    # This is slightly inefficient but safe.
    result = subprocess.run(
        ["alr", "get", "--dirname", f"{crate}={version}"],
        capture_output=True,
        text=True,
        check=True
    )
    return os.path.join("releases", crate, result.stdout.strip())


def get_specs(release_path: str) -> dict[str, str]:
    """
    Scans the release path for *.ads files in immediate 'src' or 'source'
    subdirectories.
    Returns a dict mapping {filename: full_path}.
    """
    specs = {}
    for subdir in ["src", "source"]:
        dir_path = os.path.join(release_path, subdir)
        if os.path.exists(dir_path):
            for root, _, files in os.walk(dir_path):
                for file in files:
                    if file.endswith(".ads"):
                        # We use file name as key. Ambiguity if same filename
                        # in different subfolders is ignored for now.
                        specs[file] = os.path.join(root, file)
    return specs


def is_private_package(spec_path: str) -> bool:
    """
    Check if a spec file declares a private package.
    Returns True if 'private' keyword appears before 'package' keyword.
    Handles multi-line declarations and generic packages.
    """
    try:
        with open(spec_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Remove comments (-- to end of line)
        lines = content.split('\n')
        cleaned_lines = []
        for line in lines:
            comment_pos = line.find('--')
            if comment_pos >= 0:
                line = line[:comment_pos]
            cleaned_lines.append(line)

        cleaned_content = ' '.join(cleaned_lines).lower()

        # Find positions of 'private' and 'package' keywords
        # Use word boundaries to avoid matching substrings
        private_match = re.search(r'\bprivate\b', cleaned_content)
        package_match = re.search(r'\bpackage\b', cleaned_content)

        if private_match and package_match:
            return private_match.start() < package_match.start()

        return False
    except (FileNotFoundError, UnicodeDecodeError):
        return False


def compare_specs(
    context: "LasvContext", crate: str, v1: str, v2: str, model: str = None
) -> None:
    """
    Compare public specifications (*.ads files) between two releases to identify
    backwards compatible (minor bump) or incompatible (major bump) changes.

    1. Obtain checkout folder using `alr get --dirname`.
    2. Identify all *.ads files in immediate source/ or src/ folders in both releases.
    3. Compare matching spec files:
       - Identify changes in non-generic units (between "package ... is" and "private").
    4. Handle missing specs (minor or major change depending on which version is missing it).
    """

    print(f"      Comparing specs {v1} -> {v2}...")
    try:
        path_v1 = get_release_path(crate, v1)
        path_v2 = get_release_path(crate, v2)
    except subprocess.CalledProcessError:
        print("      Error: Could not determine release paths.")
        return

    specs_v1 = get_specs(path_v1)
    specs_v2 = get_specs(path_v2)

    all_specs = set(specs_v1.keys()) | set(specs_v2.keys())

    for spec in all_specs:
        p1 = specs_v1.get(spec)
        p2 = specs_v2.get(spec)
        compare_spec_files(context, crate, v2, p1, p2, model)


def compare_spec_files(
    context: "LasvContext",
    crate: str,
    version: str,
    path1: Optional[str],
    path2: Optional[str],
    model: str = None,
) -> None:
    """
    Compare two paths to the same *.ads file.

    One path may be None if the file is missing in one of the releases.
    If not None, compares the content of the specs.
    """
    if path1 is None:
        # File added in v2. Check if it's a private package first.
        if is_private_package(path2):
            # Private packages are not part of public API
            return
        # File added in v2. Minor change (backward compatible addition).
        context.emit_change(crate, version, 'files', ChangeType.MINOR, 0, 0,
                            f"Public spec file added: {os.path.basename(path2)}")
        return

    if path2 is None:
        # File removed in v2. Check if it was a private package.
        if is_private_package(path1):
            # Private packages are not part of public API
            return
        # File removed in v2. Major change (backward incompatible removal).
        context.emit_change(crate, version, 'files', ChangeType.MAJOR, 0, 0,
                            f"Public spec file removed: {os.path.basename(path1)}")
        return

    # if file exists in both, but is private only in one case, this affects
    # the public API.
    if is_private_package(path1) != is_private_package(path2):
        if is_private_package(path1):
            # Private packages are not part of public API, so this is a minor change.
            context.emit_change(crate, version, 'files', ChangeType.MINOR, 0, 0,
                                f"Public spec file added: {os.path.basename(path2)}")
            return
        # File removed in v2. Major change (backward incompatible removal).
        context.emit_change(crate, version, 'files', ChangeType.MAJOR, 0, 0,
                            f"Public spec file removed: {os.path.basename(path1)}")
        return

    # If both exist and private, no change.
    if is_private_package(path1) and is_private_package(path2):
        return

    # Both exist, so we will compare their content later.
    specs_module.compare_spec_content(context, crate, version, path1, path2, model)


def retrieve(crate, version: str) -> None:
    """
    Retrieve two consecutive releases (given by their version strings).
    If not on disk, download them under 'releases/crate/'.
    """

    try:
        dest_path = get_release_path(crate, version)
        if os.path.exists(dest_path):
            return

        parent_path = os.path.dirname(dest_path)
        os.makedirs(parent_path, exist_ok=True)

        print(f"      Retrieving {crate}={version}...")
        subprocess.run(
            ["alr", "-C", parent_path, "get", "--only", f"{crate}={version}"],
            check=True,
            capture_output=True,
            text=True
        )
    except subprocess.CalledProcessError as e:
        print(f"      Error retrieving {crate}={version}: {e.stderr}")
        # Clean up partial download
        # dest_path might not be defined if first subprocess fails, handle carefully
        # But here we are inside try block where dest_path is computed.
        if 'dest_path' in locals() and os.path.exists(dest_path):
            shutil.rmtree(dest_path, ignore_errors=True)
        return


def find_pairs(context: "LasvContext", crate: str, model: str = None) -> int:
    """
    Find all pairs of consecutive releases for a given crate.
    For each pair, retrieve its sources using retrieve().
    Returns the count of pairs found.
    """

    found_count = 0

    # First, retrieve last version from context
    crate_info = context.data["crates"].get(crate, {})
    is_external = crate_info.get("external", False)
    is_binary = crate_info.get("binary", False)
    if is_external or is_binary:
        print("   Skipping: non-source crate.")
        return found_count

    last_version = crate_info.get("last_version")
    if last_version == "0.1.0":
        print("   Skipping: only 0.1.0 release exists.")
        return found_count

    v2 = last_version

    first_retrieved = False

    # Loop until no more previous versions
    while True:
        # Find previous release info with `alr show`
        try:
            prev_result = subprocess.run(
                ["alr", "--format", "show", f"{crate}<{v2}"],
                capture_output=True,
                text=True,
                check=True,
            )

            if "external" in prev_result.stdout:
                print("   Skipping: external release.")
                return found_count
            if "Not found" in prev_result.stdout:
                if found_count == 0:
                    print(f"   No release <{v2} found.")
                return found_count

            prev_info = json.loads(prev_result.stdout)

            v1 = prev_info.get("version")
            print(f"   Found pair: {v1} -> {v2}")
            found_count += 1
            if not first_retrieved:
                retrieve(crate, v2)
                first_retrieved = True
            retrieve(crate, v1)

            # Perform the actual comparison of specs
            # Clear previous diagnosis for this crate
            context.clear_diagnosis(crate)
            context.start_diagnosis(crate, v2, "files")

            compare_specs(context, crate, v1, v2, model)

            # Finish diagnosis for 'files' analyzer
            context.finish_diagnosis(crate, v1, v2, "files")

            v2 = v1

        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            json.JSONDecodeError,
        ) as e:
            print(f"Error checking crate {crate}<{v2}: {e}")
            return found_count
