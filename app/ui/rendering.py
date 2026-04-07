import re

import pandas as pd


def extract_first_markdown_table(text: str):
    if not text or "|" not in text:
        return None

    lines = text.splitlines()

    table_start = None
    for i in range(len(lines) - 1):
        if "|" in lines[i] and "|" in lines[i + 1]:
            separator = lines[i + 1].strip().replace(" ", "")
            if re.fullmatch(r"\|?[:\-|]+\|?", separator):
                table_start = i
                break

    if table_start is None:
        return None

    table_lines = []
    for line in lines[table_start:]:
        if "|" not in line:
            break
        table_lines.append(line.strip())

    if len(table_lines) < 2:
        return None

    header = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
    data_rows = []

    for row in table_lines[2:]:
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        if len(cells) == len(header):
            data_rows.append(cells)

    if not data_rows:
        return None

    return pd.DataFrame(data_rows, columns=header)