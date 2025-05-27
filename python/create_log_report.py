import os
import argparse
import requests
import sys
from jinja2 import Environment, FileSystemLoader
from urllib.parse import urlparse


#Environment variables:
jenkins_token = os.getenv('JENKINS_API_KEY')
build_url = os.getenv('BUILD_URL')
working_dir = os.getenv('REPORT_DIR')
ticket = os.getenv('TICKET_NUMBER')
workspace = os.getenv('WORKSPACE')

#Global variables
user_pass = jenkins_token.split(":")

# Localhost and port configuration
local_host_ip = "127.0.0.1"
local_host_port = "80"

# Parse the existing build_url
parsed_url = urlparse(build_url)

# Reconstruct the build_url to use localhost and port 80
local_build_url = f"http://{local_host_ip}:{local_host_port}{parsed_url.path}"


def get_log_lines(path):
    log = []
    if (os.path.isfile(path)):
        with open(path, 'r') as test_log:
            log = test_log.readlines()
        
    return log

editmode_log = get_log_lines(f"{working_dir}/test_results/EditMode-tests.log")
playmode_log = get_log_lines(f"{working_dir}/test_results/PlayMode-tests.log")
unity_build_log = get_log_lines(f"{working_dir}/build_project_results/build_project.log")

jenkins_log = requests.get(f"{local_build_url}consoleText", auth=(user_pass[0], user_pass[1]))

environment = Environment(loader=FileSystemLoader(f"{workspace}/python/log-template/"))
template = environment.get_template("logs.html")

logs_file = f"{working_dir}/logs.html"
content = template.render(
    ticket=ticket,
    jenkins=jenkins_log.iter_lines(),
    editMode=editmode_log,
    playMode=playmode_log,
    build=unity_build_log
)

with open(logs_file, mode="w+", encoding="utf-8") as logs:
    logs.write(content)