from lasv_main import LasvContext


def list(context : 'LasvContext'):
    """
    Do nothing if context already contains a non-empty 'crates' list.
    Else list crates using `alr`, filter out binary crates, and store the
    result in context under 'crates' key.
    """

    if 'crates' in context.data and context.data['crates']:
        print("Crates already listed in context.")
        return

    import subprocess
    import json
    from tqdm import tqdm

    try:
        result = subprocess.run(
            ["alr", "--format", "search", "--crates"],
            capture_output=True,
            text=True,
            check=True
        )
        crates_info = json.loads(result.stdout)
        print(f"Listed {len(crates_info)} crates using alr.")

    except Exception as e:
        print(f"Error listing crates: {e}")
        context.data['crates'] = []
        return

    crates_list = {}

    # Go over crate.name and use `alr show` to check if it is binary. A crate
    # is binary if its 'origin' contains a 'case(*)' key.
    for crate in tqdm(crates_info, desc="Identifying binary crates"):
        crate_name = crate.get('name')
        try:
            crate_entry = {}

            show_result = subprocess.run(
                ["alr", "--format", "show", crate_name],
                capture_output=True,
                text=True,
                check=True
            )
            show_info = json.loads(show_result.stdout)

            is_external = False
            is_binary = False
            origins = show_info.get('origin', [])
            for origin in origins:
                if 'case(' in origin:
                    is_binary = True
                    break

            # Add the 'version' field under the crate name, as 'last_version'
            crate_entry['last_version'] = show_info.get('version')

        except Exception as e:
            if 'external' in show_result.stdout:
                is_external = True
            else:
                print(f"Error checking crate {crate_name}: {e}")
        finally:
            crate_entry['binary'] = is_binary
            crate_entry['external'] = is_external
            crates_list[crate_name] = crate_entry

    context.data['crates'] = crates_list
    context.save()
    print(f"Found {len(crates_list)} source crates out of {len(crates_info)}.")


def process(context : 'LasvContext', target_crate : str = None) -> None:
    """
    For each crate in context's 'crates' list (or only target_crate if given),
    find all pairs of consecutive releases and retrieve their sources.
    """

    crates_to_process = []
    if target_crate:
        crates_to_process = [target_crate]
    else:
        crates_to_process = context.data.get('crates', [])

    total_pairs = 0

    for crate in crates_to_process:
        print(f"Processing crate: {crate}")
        from lasv import releases
        total_pairs += releases.find_pairs(context, crate)

    print(f"Total release pairs: {total_pairs}")