import requests
import re
import os

# Configuration
JIRA_BASE_URL = "https://cnhpd.atlassian.net"
ZEPHYR_BASE_URL = "https://api.zephyrscale.smartbear.com/v2"
JIRA_EMAIL = "john.maehs@cnh.com"
JIRA_API_TOKEN = os.getenv("jiraToken")  # Set in your environment
ZEPHYR_TOKEN = os.getenv("zephyrToken")  # Set in your environment
ZEPHYR_PROJECT_KEY = "PREC"

# Authentication
JIRA_AUTH = (JIRA_EMAIL, JIRA_API_TOKEN)

# Update with your actual Jira custom field IDs
REPRO_STEPS_FIELD = "issue.customfield_13101"      # <-- Replace with actual field ID
CHECKBOX_FIELD = "issue.customfield_14242"         # <-- Replace with actual checkbox field ID

def get_issue(issue_key):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}"
    response = requests.get(url, auth=JIRA_AUTH)
    response.raise_for_status()
    return response.json()

def extract_repro_steps(description):
    lines = description.splitlines()
    steps = []
    step = ""
    for line in lines:
        match = re.match(r"^\s*\d+\.\s*(.*)", line)
        if match:
            if step:
                steps.append({"action": step.strip()})
            step = match.group(1)
        else:
            step += "\n" + line
    if step:
        steps.append({"action": step.strip()})
    return steps

def create_test_case(project_key, name, steps):
    url = f"{ZEPHYR_BASE_URL}/testcases"
    headers = {
        "Authorization": f"Bearer {ZEPHYR_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "projectKey": project_key,
        "name": name,
        "testScript": {
            "type": "PLAIN_TEXT",
            "steps": [
                {"action": step["action"], "expectedResult": ""} for step in steps
            ]
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

# -------- MAIN EXECUTION --------
issue_key = "PREC-123"  # Replace or pass in dynamically (from webhook or arg)
issue = get_issue(issue_key)

project = issue["fields"]["project"]["key"]
issuetype = issue["fields"]["issuetype"]["name"]
checkbox = issue["fields"].get(CHECKBOX_FIELD, False)
description = issue["fields"].get(REPRO_STEPS_FIELD, "")

if project == "PREC" and issuetype == "Bug" and checkbox and description:
    steps = extract_repro_steps(description)
    test_case = create_test_case(ZEPHYR_PROJECT_KEY, f"Auto TC from {issue_key}", steps)
    print(f"✅ Created Zephyr test case: {test_case['key']}")
else:
    print("⚠️ Conditions not met. Not a PREC Bug with checkbox checked and repro steps filled.")
