import os
import sys
import argparse

# Constant variables:
VERSION_INDEX = 1
REVISION_INDEX = 2

# Command-line arguments:
parser = argparse.ArgumentParser(description="Arguments for the project's Unity version.", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("project-path", help="The path to the Unity project.")
parser.add_argument("value", choices=['version', 'revision', 'executable-path'], help="Whether to return the version number, the revision/changeset number, or the Unity executable path.")
args = vars(parser.parse_args())

# Global variables:
project_version_path = f'{args["project-path"]}/ProjectSettings/ProjectVersion.txt'

# Parsing the version and revision.
with open(project_version_path, 'r') as version_file:
    version_string = version_file.readlines()[1]

version_array = version_string.split()
version = version_array[VERSION_INDEX]
revision = version_array[REVISION_INDEX].strip("()")

# Printing out the requested value so the pipeline can retrieve it.
match args["value"]:
    case "version":
        sys.stdout.write(f"{version}")
    case "revision":
        sys.stdout.write(f"{revision}")
    case "executable-path":
        sys.stdout.write(f"C:/Program Files/Unity/Hub/Editor/{version}/Editor/Unity.exe")