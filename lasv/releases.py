"""
This module is responsible for handling and comparing different releases of Alire crates.
"""
import json
import os
import re
import shutil
import subprocess
from typing import Optional

from lasv_main import LasvContext, ChangeType, ChangeInfo
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

        # Remove extra whitespace
        cleaned_content = re.sub(r'\s+', ' ', cleaned_content)

        # Remove "private with", which are not package privacy indicators
        cleaned_content = re.sub(r'private with', '', cleaned_content)

        # Find positions of 'private', 'generic', 'package' keywords
        # Use word boundaries to avoid matching substrings
        private_match = re.search(r'\bprivate\b', cleaned_content)
        generic_match = re.search(r'\bgeneric\b', cleaned_content)
        package_match = re.search(r'\bpackage\b', cleaned_content)

        # Private must come before generic, not to be confused with "is private"
        # or "with private" formal specifications.
        if generic_match and private_match:
            if private_match.start() > generic_match.start():
                private_match = None  # Ignore this private occurrence

        if private_match and package_match:
            return private_match.start() < package_match.start()

        return False
    except (FileNotFoundError, UnicodeDecodeError):
        return False


def compare_specs(
    context: "LasvContext", crate: str, v1: str, v2: str
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

    print(f"      Comparing specs {v1} -> {v2} (model: {context.model})...")
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
        compare_spec_files(context, crate, v2, p1, p2)


def compare_spec_files(
    context: "LasvContext",
    crate: str,
    version: str,
    path1: Optional[str],
    path2: Optional[str],
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
        if context.model is None:
            context.emit_change(crate, version, 'files',
                                ChangeInfo(ChangeType.MINOR, 0, 0,
                                        f"Public spec file added: {os.path.basename(path2)}"))
        return

    if path2 is None:
        # File removed in v2. Check if it was a private package.
        if is_private_package(path1):
            # Private packages are not part of public API
            return
        # File removed in v2. Major change (backward incompatible removal).
        if context.model is None:
            context.emit_change(crate, version, 'files',
                                ChangeInfo(ChangeType.MAJOR, 0, 0,
                                           f"Public spec file removed: {os.path.basename(path1)}"))
        return

    # Both files exist - check privacy status
    is_private_1 = is_private_package(path1)
    is_private_2 = is_private_package(path2)

    # If both exist and private, no change.
    if is_private_1 and is_private_2:
        print(f"         Skipping private spec in {os.path.basename(path2)}")
        return

    # if file exists in both, but is private only in one case, this affects the public API.
    if is_private_1 != is_private_2:
        change_type = ChangeType.MINOR if is_private_1 else ChangeType.MAJOR
        action = "added" if is_private_1 else "removed"
        context.emit_change(crate, version, 'files',
                            ChangeInfo(change_type, 0, 0,
                                       f"Public spec file {action}: {os.path.basename(path2)}"))
        return

    # Both exist and are public, so we will compare their content.
    specs_module.compare_spec_content(context, crate, version, path1, path2)


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


def fix_version(v: str) -> str:
    """
    Fix version string to ensure it has proper format for alr.
    Adds '.0.0' if no dots, '.0' if only one dot.
    """
    # if a version doesn't contain dots, we add '.0.0' to circumvent alr issues
    if '.' not in v:
        return f"{v}.0.0"
    # If version has only one dot, add '.0'
    if v.count('.') == 1:
        return f"{v}.0"
    return v


def find_previous_version(crate: str, version: str) -> Optional[str]:
    """
    Find the previous version of a crate before the given version.
    Returns the previous version string, or None if not found.
    """
    try:
        prev_result = subprocess.run(
            ["alr", "--format", "show", f"{crate}<{version}"],
            capture_output=True,
            text=True,
            check=True,
        )

        if prev_result.stdout.strip() == "":
            return None

        prev_info = json.loads(prev_result.stdout)
        return fix_version(prev_info.get("version"))

    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error finding previous version for {crate}<{version}: {e}")
        return None


def find_pairs(context: "LasvContext", crate: str, redo: bool = False) -> int:
    """
    Find all pairs of consecutive releases for a given crate.
    For each pair, retrieve its sources using retrieve().
    If redo is True, remove existing diagnosis and redo it.
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

    last_version = fix_version(crate_info.get("last_version"))
    if last_version == "0.1.0":
        print("   Skipping: only 0.1.0 release exists.")
        return found_count

    v2 = last_version

    first_retrieved = False

    # Loop until no more previous versions
    while True:
        # Find previous release info with `alr show`
        v1 = find_previous_version(crate, v2)

        if v1 is None:
            if found_count == 0:
                print(f"   No release <{v2} found.")
            return found_count

        # Skip pairs where v1 is pre-1.0.0 (those don't have to respect semver)
        v1_parts = v1.split('.')
        if len(v1_parts) >= 1 and int(v1_parts[0]) < 1:
            print(f"   Skipping pair {v1} -> {v2} (v1 is pre-1.0.0)")
            v2 = v1
            continue

        print(f"   Found pair: {v1} -> {v2}")
        found_count += 1
        if not first_retrieved:
            retrieve(crate, v2)
            first_retrieved = True
        retrieve(crate, v1)

        # Perform the actual comparison of specs
        # Check if 'files' diagnosis already exists for this version
        files_diagnosis_exists = (
            'releases' in context.data['crates'][crate] and
            v2 in context.data['crates'][crate]['releases'] and
            'diagnosis' in context.data['crates'][crate]['releases'][v2] and
            'files' in context.data['crates'][crate]['releases'][v2]['diagnosis']
        )

        # If redo is True, remove existing diagnosis
        if redo and files_diagnosis_exists and not context.model:
            del context.data['crates'][crate]['releases'][v2]['diagnosis']['files']
            files_diagnosis_exists = False
            print(f"      Removed existing 'files' diagnosis")

        if not files_diagnosis_exists:
            context.start_diagnosis(crate, v2, "files")
            compare_specs(context, crate, v1, v2)
            context.finish_diagnosis(crate, v1, v2, "files")
        else:
            print(f"      Skipping 'files' diagnosis (already exists)")

        # If a model is provided, check if model diagnosis exists and run it if not
        if context.model:
            model_diagnosis_exists = (
                'releases' in context.data['crates'][crate] and
                v2 in context.data['crates'][crate]['releases'] and
                'diagnosis' in context.data['crates'][crate]['releases'][v2] and
                context.model in context.data['crates'][crate]['releases'][v2]['diagnosis']
            )

            # If redo is True, remove existing model diagnosis
            if redo and model_diagnosis_exists:
                del context.data['crates'][crate]['releases'][v2]['diagnosis'][context.model]
                model_diagnosis_exists = False
                print(f"      Removed existing '{context.model}' diagnosis")

            if not model_diagnosis_exists:
                context.start_diagnosis(crate, v2, context.model)
                compare_specs(context, crate, v1, v2)
                context.finish_diagnosis(crate, v1, v2, context.model)
            else:
                print(f"      Skipping '{context.model}' diagnosis (already exists)")

        v2 = v1
