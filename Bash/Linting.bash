#!/bin/bash

# Function to display error messages and exit
error_exit() {
    echo "$1" >&2
    exit 1
}

# Check args + usage
if [ $# -ne 2 ]; then
    error_exit "incorrect args USAGE: $0 <project directory> <report directory>, Script needs access to the project files to check linting"
fi

echo "Linting started with args: $1 $2"

# Check if dotnet is installed
if ! command -v dotnet &> /dev/null; then
    error_exit "Error: dotnet is not installed or not found in PATH."
fi

# Check if dotnet-format is installed
if ! dotnet tool list -g | grep -q 'dotnet-format'; then
    echo "dotnet-format not found, installing..."
    dotnet tool install -g dotnet-format
    export PATH="$PATH:$HOME/.dotnet/tools"
fi

# Search for solution file
DIR_PATH=$(echo "$1" | sed 's/\\/\//g')

SOLUTION_FILE=$(ls "$DIR_PATH"/*.sln 2>/dev/null)

# Check if a solution file was found
if [ -z "$SOLUTION_FILE" ]; then
    error_exit "Solution File not found in directory: $DIR_PATH"
else
    echo "Solution File found: $SOLUTION_FILE"
fi

#format first to get rid of whitespace
dotnet format "$SOLUTION_FILE" > /dev/null
# Run dotnet format on the solution file to check out custom rules 
dotnet format "$SOLUTION_FILE" --verify-no-changes -v q

RETVAL=$?

# Handle based on retval
if [ $RETVAL -eq 0 ]; then
    echo "Format check passed."
    exit 0
else
    # create report in the report directory supplied by $2
    dotnet format "$SOLUTION_FILE" --report "$2" -v q
    exit 2
fi






