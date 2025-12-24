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

    crates_list = []

    # Go over crate.name and use `alr show` to check if it is binary. A crate
    # is binary if its 'origin' contains a 'case(*)' key.
    for crate in tqdm(crates_info, desc="Identifying binary crates"):
        crate_name = crate.get('name')
        try:
            show_result = subprocess.run(
                ["alr", "--format", "show", crate_name],
                capture_output=True,
                text=True,
                check=True
            )
            show_info = json.loads(show_result.stdout)

            is_binary = False
            origins = show_info.get('origins', [])
            for origin in origins:
                if 'case(' in origin:
                    is_binary = True
                    break

            if is_binary:
                continue

            crates_list.append(crate_name)

        except Exception as e:
            if 'external' in show_result.stdout:
                continue
            else:
                print(f"Error checking crate {crate_name}: {e}")
                continue

    context.data['crates'] = crates_list
    context.save()
    print(f"Found {len(crates_list)} source crates with 2+ releases.")