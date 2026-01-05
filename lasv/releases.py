import json
import os
import shutil
import subprocess
from lasv_main import LasvContext
from typing import Optional


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
            for root, dirs, files in os.walk(dir_path):
                for file in files:
                    if file.endswith(".ads"):
                        # We use file name as key. Ambiguity if same filename
                        # in different subfolders is ignored for now.
                        specs[file] = os.path.join(root, file)
    return specs


def compare_specs(context: 'LasvContext', crate: str, v1: str, v2: str) -> None:
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
        compare_spec_files(context, p1, p2)


def compare_spec_files(context: 'LasvContext', path1: Optional[str], path2: Optional[str]) -> None:
    """
    Compare two paths to the same *.ads file.

    One path may be None if the file is missing in one of the releases.
    If not None, compares the content of the specs.
    """
    if path1 is None:
        # File added in v2. Minor change (backward compatible addition).
        print(f"minor (0, 0): New spec file added: {os.path.basename(path2)}")
        return

    if path2 is None:
        # File removed in v2. Major change (backward incompatible removal).
        print(f"MAJOR (0, 0): Spec file removed: {os.path.basename(path1)}")
        return

    # Both exist, so we will compare their content later
    pass


def retrieve(crate, version : str) -> None:
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
             shutil.rmtree(dest_path)
        return


def find_pairs(context : 'LasvContext', crate : str) -> int:
    """
    Find all pairs of consecutive releases for a given crate.
    For each pair, retrieve its sources using retrieve().
    Returns the count of pairs found.
    """

    found_count = 0

    # First, retrieve last version from context
    crate_info = context.data['crates'].get(crate, {})
    is_external = crate_info.get('external', False)
    is_binary = crate_info.get('binary', False)
    if is_external or is_binary:
        print("   Skipping: non-source crate.")
        return found_count

    last_version = crate_info.get('last_version')
    if last_version == '0.1.0':
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
                check=True
            )

            if 'external' in prev_result.stdout:
                print("   Skipping: external release.")
                return found_count
            elif 'Not found' in prev_result.stdout:
                if found_count == 0:
                    print(f"   No release <{v2} found.")
                return found_count

            prev_info = json.loads(prev_result.stdout)

            v1 = prev_info.get('version')
            print(f"   Found pair: {v1} -> {v2}")
            found_count += 1
            if not  first_retrieved:
                retrieve(crate, v2)
                first_retrieved = True
            retrieve(crate, v1)

            # Perform the actual comparison of specs
            compare_specs(context, crate, v1, v2)

            v2 = v1

        except Exception as e:
            print(f"Error checking crate {crate}<{v2}: {e}")
            return found_count
