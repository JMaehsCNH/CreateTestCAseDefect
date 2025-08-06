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

def search_issues_jql(jql, max_results=25):
    url = f"{JIRA_BASE_URL}/rest/api/3/search"
    headers = {"Content-Type": "application/json"}
    payload = {
        "jql": jql,
        "maxResults": max_results,
        "fields": [REPRO_STEPS_FIELD, CHECKBOX_FIELD, "summary", "project", "issuetype"]
    }
    response = requests.post(url, auth=JIRA_AUTH, json=payload, headers=headers)
    response.raise_for_status()
    return response.json().get("issues", [])

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
            "steps": [{"action": step["action"], "expectedResult": ""} for step in steps]
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

# Main logic
jql = f'project = PREC AND issuetype = Bug AND "{CHECKBOX_FIELD}" = true'
issues = search_issues_jql(jql, max_results=50)

if not issues:
    print("ℹ️ No matching Bugs found with Test Case checkbox checked.")
else:
    for issue in issues:
        key = issue["key"]
        summary = issue["fields"]["summary"]
        checkbox = issue["fields"].get(CHECKBOX_FIELD, False)
        description = issue["fields"].get(REPRO_STEPS_FIELD, "")

        if checkbox and description:
            print(f"🔄 Processing issue: {key} - {summary}")
            steps = extract_repro_steps(description)
            test_case = create_test_case(ZEPHYR_PROJECT_KEY, f"Auto TC from {key}", steps)
            print(f"✅ Created Zephyr Test Case: {test_case['key']}")
        else:
            print(f"⚠️ Skipping {key}: Missing checkbox or repro steps.")
