import json
import os
import sys
import requests
import argparse

def categorize_vulnerabilities(file_path):
    try:
        with open(file_path) as file:
            data = json.load(file)
    except FileNotFoundError:
        print(f"Audit report file not found: {file_path}")
        return
    
    vulnerabilities = data.get('vulnerabilities', {})
    if not vulnerabilities:
        print("No vulnerabilities found.")
        return
    
    categorized = {}

    for package, details in vulnerabilities.items():
        for vulnerability in details.get('via', []):
            severity = vulnerability.get('severity', 'unknown')
            categorized.setdefault(severity, []).append({
                'package': package,
                'issue': vulnerability.get('title', 'Unknown issue'),
                'url': vulnerability.get('url', 'No URL provided')
            })

    for severity, issues in categorized.items():
        print(f"Severity: {severity}")
        for issue in issues:
            print(f" - Package: {issue['package']}, Issue: {issue['issue']}, URL: {issue['url']}")

    return categorized

def chunk_annotations(annotations, batch_size):
    for i in range(0, len(annotations), batch_size):
        yield annotations[i:i + batch_size]  # List slices ie 0:100, 100:200, etc.


# Command-line arguments: 
parser = argparse.ArgumentParser(description="Arguments for Bitbucket test reports.", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

parser.add_argument("commit", help="The commit hash the report will be sent to.")
parser.add_argument("path_to_report", help="The path to the report of the audit.")

args = vars(parser.parse_args())

access_token = os.getenv('BITBUCKET_ACCESS_TOKEN')
ticket_number = os.getenv('TICKET_NUMBER')
pr_repo = os.getenv('JOB_REPO')
folder_name = os.getenv('FOLDER_NAME')

if not access_token or not ticket_number or not pr_repo:
    print("Missing required environment variables.")
    exit(1)

# Global variables:
url = f'{pr_repo}/commit/{args["commit"]}/reports/Audit-report'
annotation_url = url + f'/annotations'

headers = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Authorization": "Bearer " + access_token
}

vulnerabilities = categorize_vulnerabilities(args["path_to_report"])
num_of_vuln = num_of_vuln = len(vulnerabilities or {})


# Sending the report to Bitbucket Cloud API.
report = json.dumps( {
    "title": f"{ticket_number}: Consolidated Audit Report",
    "details": "Audit Report",
    "report_type": "SECURITY",
    "reporter": "Jenkins",
    "data": [
        {
            "type": "NUMBER",
            "title": "Number of vulnerabilities",
            "value": num_of_vuln
        }
    ]
} )

try:
    response = requests.put(url, data=report, headers=headers)
    response.raise_for_status()
except requests.exceptions.RequestException as e:
    print(f"Initial Request: {e.request.body}")
    print(f"Response Error: {json.dumps(e.response.json())}")
    exit(1)


# Preparing annotations for vulnerabilities
annotations = []
if vulnerabilities:
    for severity, issues in vulnerabilities.items():
        for issue in issues:
            annotation = {
                "external_id": f"{issue['package']}_{issue['issue']}",  # Unique identifier for the annotation
                "annotation_type": "VULNERABILITY",
                "summary": f"Vulnerability in {issue['package']}: {issue['issue']}",
                "result": "FAILED",
                "severity": severity.upper(),
                "url": issue["url"]
            }
            annotations.append(annotation)
else:
    exit(0)

# Limit annotations to comply with Bitbucket REST API
max_annotations = 1000
batch_size = 100
annotations_to_send = annotations[:max_annotations]

# Sending annotations in batches
for idx, annotation_batch in enumerate(chunk_annotations(annotations_to_send, batch_size)):
    annotation_report = json.dumps(annotation_batch)
    try:
        response = requests.post(annotation_url, data=annotation_report, headers=headers)
        response.raise_for_status()
        print(f"Batch {idx + 1} sent successfully")
    except requests.exceptions.RequestException as e:
        print(f"Error with batch {idx + 1}: {e.request.body}")
        if e.response:
            print(f"Response Error: {json.dumps(e.response.json())}")
        else:
            print(f"General Exception: {e}")
        exit(0)  # Exit on error




