"""
This module handles the listing and processing of Alire crates.
"""
import subprocess
import json
from tqdm import tqdm
from lasv_main import LasvContext
from lasv import releases


def list_crate(context: 'LasvContext', crate_name: str) -> None:
    """
    Retrieve information about a single crate using 'alr show' and add it to context.

    Args:
        context: The LasvContext to store the crate information in
        crate_name: The name of the crate to query
    """
    is_external = False
    is_binary = False
    crate_entry = {}

    # If the crate is already listed, skip it
    if 'crates' in context.data and crate_name in context.data['crates']:
        print(f"Crate {crate_name} already listed in context.")
        return

    try:
        show_result = subprocess.run(
            ["alr", "--format", "show", crate_name],
            capture_output=True,
            text=True,
            check=True
        )
        show_info = json.loads(show_result.stdout)

        origins = show_info.get('origin', [])
        for origin in origins:
            if 'case(' in origin:
                is_binary = True
                break

        # Add the 'version' field under the crate name, as 'last_version'
        crate_entry['last_version'] = show_info.get('version')

    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError) as e:
        if show_result.stdout == '' or 'external' in show_result.stdout:
            is_external = True
        else:
            print(f"Error checking crate {crate_name}: {e}")
    finally:
        crate_entry['binary'] = is_binary
        crate_entry['external'] = is_external

    # Initialize 'crates' dict if it doesn't exist
    if 'crates' not in context.data:
        context.data['crates'] = {}

    context.data['crates'][crate_name] = crate_entry


def list_crates(context : 'LasvContext'):
    """
    Do nothing if context already contains a non-empty 'crates' list.
    Else list crates using `alr`, filter out binary crates, and store the
    result in context under 'crates' key.
    """

    if 'crates' in context.data and context.data['crates']:
        print("Crates already listed in context.")
        return

    try:
        result = subprocess.run(
            ["alr", "--format", "search", "--crates"],
            capture_output=True,
            text=True,
            check=True
        )
        crates_info = json.loads(result.stdout)
        print(f"Listed {len(crates_info)} crates using alr.")

    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error listing crates: {e}")
        context.data['crates'] = []
        return

    # Initialize crates dict in context
    context.data['crates'] = {}

    # Go over crate.name and use `alr show` to check if it is binary. A crate
    # is binary if its 'origin' contains a 'case(*)' key.
    for crate in tqdm(crates_info, desc="Identifying source crates"):
        crate_name = crate.get('name')
        list_crate(context, crate_name)

    context.save()
    # Crates with binary or external set to True are not source crates:
    source_crates = {
        name: info for name, info in context.data['crates'].items()
        if not info.get('binary', False) and not info.get('external', False)
    }
    print(f"Found {len(source_crates)} source crates out of {len(crates_info)}.")


def process(
    context: "LasvContext", target_crate: str | None = None,
    list_only: bool = False, redo: bool = False
) -> None:
    """
    For each crate in context's 'crates' list (or only target_crate if given),
    find all pairs of consecutive releases and retrieve their sources.

    If list_only is True, skip pair detection and analysis.
    If redo is True, remove existing diagnosis and redo it.
    """

    crates_to_process = []
    if target_crate:
        crates_to_process = [target_crate]
        list_crate(context, target_crate)
    else:
        crates_to_process = context.data.get('crates', [])

    if list_only:
        print(f"Listed {len(crates_to_process)} crate(s).")
        return

    total_pairs = 0

    for crate in crates_to_process:
        print(f"Processing crate: {crate}")
        total_pairs += releases.find_pairs(context, crate, redo=redo)

    print(f"Total release pairs: {total_pairs}")
