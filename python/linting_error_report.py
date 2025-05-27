import json
import sys
import os
import argparse
import requests
import uuid

# Function summary: This takes a file path to a json file, normalizes it and returns the loaded JSON data
def get_json_normalized(json_file):
    normalizedPath = os.path.normpath(json_file)

    if not os.path.isfile(normalizedPath):
        raise FileNotFoundError(f"File not found: {normalizedPath}")

    # Load file
    with open(normalizedPath, 'r') as f:
        data = json.load(f)

    return data

# Function summary: This function takes a JSON file/file path, and will build the string 
# That is included in the report details on bitbucket
def count_errors(json_file):
    data = get_json_normalized(json_file)

    # Counters
    total_errors = 0
    file_error_count= {} # To add error count per file

    # Get the num of errors and errors per file
    for object in data:
        if 'FileName' in object and 'FileChanges' in object: # FileName and FileChanges are key in the JSON report made by dotnet format
            file_name = object['FileName']

            # Add error count for file, the report appears to make objects for each error so each mention of filename = 1 error
            if file_name in file_error_count:
                file_error_count[file_name] += 1
            else:
                file_error_count[file_name] = 1

            total_errors += 1

    # Build string to return
    retstr = f"Total number of errors: {total_errors}"
    for file, errors in file_error_count.items():
        retstr += (f"\n{file} errors = {errors}")

    return retstr

# Command-line arguments: 
parser = argparse.ArgumentParser(description="Arguments for Bitbucket test reports.", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

parser.add_argument("lint-report-path", help="The path in the Jenkins workspace where the linting report is located.")
parser.add_argument("commit", help="The commit hash the report will be sent to.")
parser.add_argument("Result", choices=['Pass', 'Fail'], help="pass or fail, indicating what type of report.")
parser.add_argument("Unity-Project", help="The path to the unity project") #DONT FORGET TO ADD ARGS TO JENKINS FILE!!!

args = vars(parser.parse_args())

# Environment variables:
access_token = os.getenv('BITBUCKET_ACCESS_TOKEN')
ticket_number = os.getenv('TICKET_NUMBER')
pr_repo = os.getenv('JOB_REPO')
folder_name = os.getenv('FOLDER_NAME')
report_id = 'lint-test-report'
# Global variables:
url = f'{pr_repo}/commit/{args["commit"]}/reports/{report_id}'

headers = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Authorization": "Bearer " + access_token
}

result = "PASSED" if args["Result"] == "Pass" else "FAILED"
details = "0 Formatting errors" if args["Result"] == "Pass" else "Formatting Errors Detected"
datastring = "No report" if args["Result"] == "Pass" else count_errors(args["lint-report-path"])

# Sending the report to Bitbucket Cloud API.
report = json.dumps( {
    "title": f"Linting Report",
    "details": f"{details}", 
    "report_type": "TEST",
    "reporter": "Jenkins",
    "result": f"{result}",
    #"link": f"",# Do we want a link to the json? in which case may have to scp the report over to the apache server
    "data": [
        {
            "type": "TEXT",
            "title": "Report Details",
            "value": datastring
        },
        {
            "type": "BOOLEAN",
            "title": "Linting check passed?",
            "value": True  if args["Result"] == "Pass" else False 
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

#Early exit, if pass no annotations to add to report
if(args["Result"]== "Pass"): exit(0)

#probably best to keep the annotations sending seperate from that report request, still in the same script as we need the report path anyway

# Function definitions
# Function Summary: This function takes a file and path, to give you the relative path to file from the given path
def find_file_path(filename, search_path):
    for root, dirs, files in os.walk(search_path):
        if filename in files:
            return os.path.relpath(os.path.join(root, filename), search_path)
    return None

# Function summary: This function takes the total annotations, and a batch size then slices the list
# According to the batch size yield returning the chunk and repeating
def chunk_annotations(annotations, batch_size):
    for i in range(0, len(annotations), batch_size):
        yield annotations[i:i + batch_size] # List slices ie 0:100, 100:200, yield can return multiple times

# Variable declarations
data = get_json_normalized(args["lint-report-path"])
search_path = os.path.normpath(args["Unity-Project"])
annotations = []
external_ids = set() # Holds ids to check against, ensures unique ID's

# Loop to build json array of Annotations
for document in data:
    filename = document['FileName']
    file_changes = document['FileChanges']
    
    # Find the relative path using the provided function
    relative_path = find_file_path(filename, search_path)

    relative_path = relative_path.replace("\\", "/") # replace slashes to match git repo slashes 
    print(f"Processing file: {filename}, relative path: {relative_path}")

    if(relative_path == None): 
        print("File Not Found")
        continue #if path not found skip annotation
    
    # Process each file change
    for change in file_changes:
        line_number = change['LineNumber']
        summary = change['FormatDescription']
        id = f"{relative_path} + {line_number}"

        # If ID found concat a UUID on
        if id in external_ids:
            id += f"-{uuid.uuid4()}"
        else:
            external_ids.add(id)
        
        # Create the annotation object
        # "type": "<string>", not sure if needed is on REST API doc
        annotation = {
            "external_id": id,
            "annotation_type": "CODE_SMELL",
            "path": relative_path,
            "line": line_number,
            "summary": summary,
            "result": "FAILED",
            "severity": "LOW"
        }
        
        # Add the annotation to the list
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