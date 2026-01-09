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
import sys
import argparse

from lasv import crates
from lasv.context import LasvContext, normalize_model_name, fix_context_data


def lasv_main():
    """
    Load context if it exists. Obtain from it the 'crates' list.
    If a crate name is given as argument, process only that crate.
    """
    parser = argparse.ArgumentParser(
        description="Version compliance analysis using LLMs."
    )
    parser.add_argument(
        "crate",
        nargs="?",
        help="Crate name to process (optional).",
    )
    parser.add_argument(
        "--model",
        help="LLM model to use for analysis (optional)."
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Only list crates without performing pair detection and analysis."
    )
    parser.add_argument(
        "--redo",
        action="store_true",
        help="Remove existing diagnosis and redo it."
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Enable full analysis mode."
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Normalize stored model keys (remove ':free') and exit."
    )
    args = parser.parse_args()

    if args.model and not os.environ.get("OPENROUTER_API_KEY"):
        print("Error: --model requires OPENROUTER_API_KEY to be set.")
        sys.exit(1)

    context = LasvContext()
    context.load()
    context.load_config()

    if args.fix:
        fixed_count = fix_context_data(context)
        if fixed_count:
            context.save()
        print(f"Fixed {fixed_count} key(s).")
        return

    # Set the model in context if provided
    if args.model:
        context.model = args.model
        context.model_key = normalize_model_name(args.model)
    context.full = args.full

    if args.crate:
        print(f"Processing only crate: {args.crate}")
    else:
        print("Processing all crates.")
        crates.list_crates(context)

    crates.process(context, args.crate, list_only=args.list_only, redo=args.redo)
    context.save()

# Program entry point
if __name__ == "__main__":
    lasv_main()
