#!/usr/bin/env python3
import os
import re
import datetime as dt
from pathlib import Path


README = Path(os.environ.get("README_PATH", "README.md"))
IMAGE_PATH = os.environ.get("STATS_IMAGE_PATH", "./profile/stats.svg")


def main():
    token = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
    text = README.read_text(encoding="utf-8")
    pattern = re.compile(
        r"(!\[Terry's GitHub Stats\]\()"
        + re.escape(IMAGE_PATH)
        + r"(?:\?cache_bust=[^)]+)?(\))"
    )
    updated, count = pattern.subn(
        rf"\g<1>{IMAGE_PATH}?cache_bust={token}\g<2>",
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError(f"Could not find stats image reference in {README}.")
    README.write_text(updated, encoding="utf-8", newline="\n")
    print(f"Updated stats cache_bust to {token}.")


if __name__ == "__main__":
    main()
