import json
import subprocess
from lasv_main import LasvContext


def retrieve(crate, v1, v2 : str) -> None:
    """
    Retrieve two consecutive releases (given by their version strings).
    If not on disk, download them under 'releases/crate/'.
    """


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
            retrieve(crate, v1, v2)
            v2 = v1

        except Exception as e:
            print(f"Error checking crate {crate}<{v2}: {e}")
            return found_count
