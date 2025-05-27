import os
import sys
import requests
import json
import argparse

# Command-line arguments:
parser = argparse.ArgumentParser(description="Arguments for sending Bitbucket build statuses.", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("pr-commit", help="The full SHA hash of the commit where the build status will be sent.")
parser.add_argument("pr-status", choices=['SUCCESSFUL', 'FAILED', 'STOPPED', 'INPROGRESS'])
parser.add_argument("-d", "--deployment", action='store_true', help="Flag to use if we are updating a deployment build status.")
parser.add_argument("-js", "--javascript",action='store_true', help="An optional argument to set the different build_url.")
parser.add_argument("-desc", "--description", help="An optional argument for adding additional information to the build description.")
parser.add_argument("-key", "--projeckey", help="An argument for sonarqube project key.")
args = vars(parser.parse_args())

# Environment variables:
access_token = os.getenv('BITBUCKET_ACCESS_TOKEN')
pr_repo = os.getenv('JOB_REPO')
build_id = os.getenv('BUILD_ID')
ticket = os.getenv('TICKET_NUMBER')
build_number = os.getenv('BUILD_NUMBER')
folder_path = os.getenv('JOB_NAME')

if folder_path:
    folder_path_parts = folder_path.split('/')
    job_name = folder_path_parts[-1]
    folder_name = '/'.join(folder_path_parts[:-1]) if len(folder_path_parts) > 1 else ''


# Global variables:
url = f'{pr_repo}/commit/{args["pr-commit"]}/statuses/build'
description = f"{args['pr-status']}: {args['description']}" if (args['description'] != None) else args['pr-status']
sonar_project_key = args['projeckey'] if (args['projeckey'] != None) else None

# No need to change argument parsing since `action='store_true'` handles boolean values
if args['pr-status'] == "INPROGRESS":
    build_url = f"https://jenkins.vconestoga.com/blue/organizations/jenkins/{folder_name}%2F{job_name}/detail/{job_name}/{build_number}/pipeline/"
else:
    if not args['javascript']:
        build_url = f"https://webdlx.vconestoga.com/{folder_path}/Reports/{ticket}/logs.html"
    else:
        build_url = f"https://jenkins.vconestoga.com/sonarqube/dashboard?id={sonar_project_key}"

headers = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Authorization": "Bearer " + access_token
}

# Sending the build status to Bitbucket Cloud API.
build_status = json.dumps( {
    "key": build_id,
    "state": args['pr-status'],
    "description": description,
    "url": build_url
} )

try:
    response = requests.post(url, data=build_status, headers=headers)
    response.raise_for_status()
except requests.exceptions.RequestException as e:
    print(f"Initial Request: {e.request.body}")
    print(f"Response Error: {json.dumps(e.response.json())}")
    exit(1)