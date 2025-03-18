#!/bin/bash
# Script to format all Python files according to project rules that aren't ignored by gitignore

echo "===== Formatting Python Files ====="

# Check if tools are installed
command -v black >/dev/null 2>&1 || { echo "Error: black is not installed. Run: pip install black"; exit 1; }
command -v isort >/dev/null 2>&1 || { echo "Error: isort is not installed. Run: pip install isort"; exit 1; }
command -v flake8 >/dev/null 2>&1 || { echo "Error: flake8 is not installed. Run: pip install flake8"; exit 1; }
command -v git >/dev/null 2>&1 || { echo "Error: git is not installed."; exit 1; }

# Find all Python files tracked by git (respects .gitignore)
PYTHON_FILES=$(git ls-files "*.py")

if [ -z "$PYTHON_FILES" ]; then
    echo "No Python files found that are tracked by git."
    exit 0
fi

# Format files with black
echo "Running Black formatter..."
black $PYTHON_FILES

# Sort imports with isort (using black compatibility)
echo -e "\nSorting imports with isort..."
isort --profile black $PYTHON_FILES

# Check remaining issues with flake8
echo -e "\nChecking for remaining issues with flake8..."
flake8 $PYTHON_FILES

echo -e "\n===== Formatting complete ====="
