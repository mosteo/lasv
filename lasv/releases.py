import json
import subprocess
from lasv_main import LasvContext


def retrieve(crate, v1, v2 : str) -> None:
    """
    Retrieve two consecutive releases (given by their version strings).
    If not on disk, download them under 'releases/crate/'.
    """


def find_pairs(context : 'LasvContext', crate : str) -> None:
    """
    Find all pairs of consecutive releases for a given crate.
    For each pair, retrieve its sources using retrieve()
    """

    # First, retrieve last version from context
    crate_info = context.data['crates'].get(crate, {})
    last_version = crate_info.get('last_version')
    if last_version == '0.1.0':
        print("   Skipping: only 0.1.0 release exists.")
        return

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
            prev_info = json.loads(prev_result.stdout)

            v1 = prev_info.get('version')
            print(f"   Found pair: {v1} -> {v2}")
            retrieve(crate, v1, v2)
            v2 = v1

        except Exception as e:
            if 'external' in prev_result.stdout:
                continue
            elif 'Not found' in prev_result.stdout:
                return
            else:
                print(f"Error checking crate {crate}<{v2}: {e}")
                return

