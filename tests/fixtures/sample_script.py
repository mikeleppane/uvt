#!/usr/bin/env python3
# /// script
# dependencies = ["requests", "rich"]
# requires-python = ">=3.10"
# ///

"""Sample script with PEP 723 inline metadata."""

import sys


def main() -> None:
    print("Hello from sample script!")
    print(f"Arguments: {sys.argv[1:]}")


if __name__ == "__main__":
    main()
