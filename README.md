# Friendly Python Code Checker (CLI)

A Python command-line tool that scans Python source files and reports common issues in a user-friendly format.

## Features

- Scans Python files for:
  - Trailing whitespace
  - Long lines
  - TODO / FIXME notes
  - Mixed indentation (tabs vs spaces)
  - Undefined names
  - Unused imports
- Shows line numbers and severity levels
- Groups results by Errors / Warnings / Notes
- Designed for junior DevOps / SysAdmin workflows

## How to Run

```bash
python code_checker.py

Enter a Python filename when prompted.

Example Output
Summary: 0 errors, 20 warnings, 4 notes
Line 154: Line is long (111 chars)
Line 136: Found TODO/FIXME note
