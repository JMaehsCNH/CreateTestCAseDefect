import requests
import re
import os

# Configuration
JIRA_BASE_URL = "https://cnhpd.atlassian.net"
ZEPHYR_BASE_URL = "https://api.zephyrscale.smartbear.com/v2"
JIRA_EMAIL = "john.maehs@cnh.com"
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")  # Set in your environment
ZEPHYR_TOKEN = os.getenv("ZEPHYR_TOKEN")  # Set in your environment
ZEPHYR_PROJECT_KEY = "PREC"


# Authentication
JIRA_AUTH = (JIRA_EMAIL, JIRA_API_TOKEN)

print("🔐 Testing Jira authentication...")
print(f"📥 Env var JIRA_EMAIL: {JIRA_EMAIL}")
print(f"📥 Env var JIRA_API_TOKEN set: {'Yes' if JIRA_API_TOKEN else 'No'}")
print(f"🌐 Jira URL: {JIRA_BASE_URL}/rest/api/3/myself")

# Optionally show Authorization header for debugging
import base64
if JIRA_EMAIL and JIRA_API_TOKEN:
    token = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
    print(f"🧪 Base64 Authorization header (debug): Basic {token[:6]}...")

# Use basic auth in headers to match Jira expectations
headers = {
    "Authorization": f"Basic {token}",
    "Content-Type": "application/json"
}
auth_check = requests.get(f"{JIRA_BASE_URL}/rest/api/3/myself", headers=headers)

print(f"Auth status: {auth_check.status_code}")
if auth_check.status_code != 200:
    print("❌ Jira authentication failed.")
    print("Response body:")
    print(auth_check.text)
    exit(1)
else:
    print("✅ Jira authentication successful.")

url = f"{JIRA_BASE_URL}/rest/api/3/search"
payload = {
    "jql": "project = PREC AND issuetype = Bug",
    "maxResults": 1
}
response = requests.post(url, auth=JIRA_AUTH, json=payload, headers={"Content-Type": "application/json"})

print(response.status_code)
print(response.json())

# Update with your actual Jira custom field IDs
REPRO_STEPS_FIELD = "customfield_13101"      # <-- Replace with actual field ID
CHECKBOX_FIELD = "customfield_14242"         # <-- Replace with actual checkbox field ID
CHECKBOX_FIELD_NAME = "Create Test Case"  # ✅ Use the visible field label from Jira UI

def search_issues_jql(jql, max_results=25):
    url = f"{JIRA_BASE_URL}/rest/api/3/search"
    headers = {"Content-Type": "application/json"}
    payload = {
        "jql": jql,
        "maxResults": max_results,
        "fields": [REPRO_STEPS_FIELD, CHECKBOX_FIELD, "summary", "project", "issuetype"]
    }
    response = requests.post(url, auth=JIRA_AUTH, json=payload, headers=headers)

    if response.status_code != 200:
        print("❌ Jira Search Error:")
        print(f"Status Code: {response.status_code}")
        print(f"URL: {url}")
        print(f"JQL: {jql}")
        print(f"Response: {response.text}")
        
    response.raise_for_status()
    return response.json().get("issues", [])


def extract_repro_steps(adf_dict):
    if not isinstance(adf_dict, dict):
        return []

    try:
        content = adf_dict.get("content", [])
        steps = []

        for list_block in content:
            if list_block["type"] == "orderedList":
                for item in list_block["content"]:
                    step_text = ""
                    for para in item["content"]:
                        for part in para["content"]:
                            step_text += part.get("text", "")
                    steps.append({"action": step_text.strip()})
        return steps

    except Exception as e:
        print(f"⚠️ Error parsing ADF repro steps: {e}")
        return []


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
jql = 'project = PREC AND issuetype = Bug AND "Create Test Case" = "Create Test Case"'
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
