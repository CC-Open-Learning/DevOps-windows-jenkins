import os
import sys
import requests
import json
import xml.etree.ElementTree as ET
import argparse

# Command-line arguments: 
parser = argparse.ArgumentParser(description="Arguments for Bitbucket test reports.", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

parser.add_argument("commit", help="The commit hash the report will be sent to.")
parser.add_argument("test-results-path", help="The path in the Jenkins workspace where the test results are located.")

args = vars(parser.parse_args())

# Environment variables:
access_token = os.getenv('BITBUCKET_ACCESS_TOKEN')
ticket_number = os.getenv('TICKET_NUMBER')
pr_repo = os.getenv('JOB_REPO')
folder_name = os.getenv('FOLDER_NAME')

# Global variables:
url = f'{pr_repo}/commit/{args["commit"]}/reports/Test-report'

headers = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Authorization": "Bearer " + access_token
}

# Parses the number of tests failed from the results XML file.
def get_number_of_tests_failed(result_file):
    tree_root = ET.parse(result_file).getroot()
    total_tests = tree_root.attrib['total']
    total_failed = tree_root.attrib['failed']
    results = {
        "total_tests": total_tests,
        "total_failed": total_failed
    }
    return results

results_file_name = "Summary.xml"

# Parses the line coverage percentage from the code coverage HTML report.
def get_line_coverage(result_file):
    tree_root = ET.parse(result_file).getroot()
    line_coverage = tree_root.find('Summary').find('Linecoverage').text
    return line_coverage

result = get_line_coverage(f'{args["test-results-path"]}/coverage_results/Report/{results_file_name}')
result_float = float(result)

# Request variables:
editmode_failed = get_number_of_tests_failed(f'{args["test-results-path"]}/test_results/EditMode-results.xml')
playmode_failed = get_number_of_tests_failed(f'{args["test-results-path"]}/test_results/PlayMode-results.xml')

# Sending the report to Bitbucket Cloud API.
report = json.dumps( {
    "title": f"{ticket_number}: Consolidated Test Report",
    "details": f"EditMode: {editmode_failed['total_failed']}/{editmode_failed['total_tests']} failed, "
               f"PlayMode: {playmode_failed['total_failed']}/{playmode_failed['total_tests']} failed",
    "report_type": "TEST",
    "reporter": "Jenkins",
    "result": "FAILED" if int(editmode_failed['total_failed']) > 0 or int(playmode_failed['total_failed']) > 0 else "PASSED",
    "link": f"https://webdlx.vconestoga.com/{folder_name}/Reports/{ticket_number}/CodeCoverage-report/index.html",
    "data": [
        {
            "type": "BOOLEAN",
            "title": "All EditMode tests passed?",
            "value": int(editmode_failed['total_failed']) == 0
        },
        {
            "type": "BOOLEAN",
            "title": "All PlayMode tests passed?",
            "value": int(playmode_failed['total_failed']) == 0
        },
        {
            "type": "PERCENTAGE",
            "title": "Line coverage",
            "value": result_float
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

# Function summary: This function takes the total annotations, and a batch size then slices the list
# According to the batch size yield returning the chunk and repeating
def chunk_annotations(annotations, batch_size):
    for i in range(0, len(annotations), batch_size):
        yield annotations[i:i + batch_size] # List slices ie 0:100, 100:200, yield can return multiple times

mode = ["PlayMode", "EditMode"]

for testmode in mode:
    # Variables
    testXML = f'{args["test-results-path"]}/test_results/{testmode}-results.xml'
    tree = ET.parse(testXML)
    root = tree.getroot()
    annotations = []


    # Loop to build json array 
    for test in root.iter('test-case'):
        if(test.get('result') == "Failed"):
            id = test.get('methodname')
            summary = f"The test method {id} has failed."
            annotation = {
                    "external_id": id,
                    "annotation_type": "VULNERABILITY",
                    "summary": summary,
                    "result": "FAILED",
                    "severity": "HIGH"
                }
            
            annotations.append(annotation)

    # Limits according to Bitbucket REST API docs
    max_annotations = 1000  # The total max number of annotations allowed per report
    batch_size = 100        # Limit of annotations per request

    # Request stuff below here
    AnnotationUrl = url + f'/annotations'
    # Can re use headers
    # Only send up to 1000 annotations, Slices excess off limit of REST API
    annotations_to_send = annotations[:max_annotations]

    # Loop through the chunks and send requests
    for idx, annotation_batch in enumerate(chunk_annotations(annotations_to_send, batch_size)):
        # Create the JSON body for this batch
        AnnotationReport = json.dumps(annotation_batch)

        
        # Send the request
        try:
            response = requests.post(AnnotationUrl, data=AnnotationReport, headers=headers)
            response.raise_for_status()  # This will raise an exception for HTTP errors
            print(f"Batch {idx+1} sent successfully") # Remove later for debugging
        except requests.exceptions.RequestException as e:
            print(f"Error with batch {idx+1}: {e.request.body}")
            if e.response:
                print(f"Response Error: {json.dumps(e.response.json())}")
            else:
                print(f"General Exception: {e}")
            exit(0)  # Exit on error

            