import os
import sys
import requests
import json
import argparse

# Command-line arguments:
parser = argparse.ArgumentParser(description="Arguments for retrieving a full commit hash from Bitbucket.", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("pr-commit", help="The short hash for the PR's commit.")
args = vars(parser.parse_args())

pr_commit = args["pr-commit"]

# Environment variables:
access_token = os.getenv('BITBUCKET_ACCESS_TOKEN')
pr_repo = os.getenv('JOB_REPO')

# Global variables:
url = f'{pr_repo}/commit/{pr_commit}/?fields=hash'

headers = {
    "Accept": "application/json",
    "Authorization": "Bearer " + access_token
}

# Retrieving the commit data from Bitbucket Cloud API.
try:
    response = requests.get(url, headers=headers)
    response.raise_for_status()  # Raise an error for bad status codes
    response_data = response.json()
    if "hash" in response_data:
        sys.stdout.write(response_data["hash"])
    else:
        sys.stderr.write("Error: 'hash' key not found in response.\n")
        sys.exit(1)
except requests.RequestException as e:
    sys.stderr.write(f"Error retrieving commit hash from Bitbucket: {e}\n")
    sys.exit(1)
