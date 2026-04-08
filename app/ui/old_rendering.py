from io import StringIO
import re

import pandas as pd


def extract_first_markdown_table(markdown_text: str) -> pd.DataFrame | None:
    """
    Extract the first markdown table from text and return a DataFrame.
    """
    lines = markdown_text.splitlines()
    table_lines = []

    for i, line in enumerate(lines):
        if "|" not in line:
            if table_lines:
                break
            continue

        if i + 1 < len(lines):
            next_line = lines[i + 1]
            if re.match(r"^\s*\|?[\-\s\|:]+\|?\s*$", next_line):
                table_lines = [line, next_line]
                for extra in lines[i + 2:]:
                    if "|" in extra:
                        table_lines.append(extra)
                    else:
                        break
                break

    if len(table_lines) < 3:
        return None

    cleaned = []
    for row in table_lines:
        row = row.strip().strip("|")
        cleaned.append(",".join([cell.strip() for cell in row.split("|")]))

    csv_like = "\n".join([cleaned[0]] + cleaned[2:])

    try:
        return pd.read_csv(StringIO(csv_like))
    except Exception:
        return None