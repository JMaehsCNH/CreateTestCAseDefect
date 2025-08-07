import requests
import re
import os
import json

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


def extract_repro_steps(adf):
    # Handle plain string (fallback)
    if isinstance(adf, str):
        lines = adf.splitlines()
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

    # Handle ADF format
    steps = []
    try:
        for block in adf.get("content", []):
            if block["type"] == "orderedList":
                for item in block["content"]:
                    step_text = ""
                    for paragraph in item.get("content", []):
                        for part in paragraph.get("content", []):
                            if part["type"] == "text":
                                step_text += part.get("text", "")
                    if step_text.strip():
                        steps.append({"action": step_text.strip()})
    except Exception as e:
        print(f"⚠️ Error parsing ADF: {e}")
    return steps

print("📦 Payload being sent to Zephyr:")
print(json.dumps(payload, indent=2))

def create_test_case(project_key, name):
    url = f"{ZEPHYR_BASE_URL}/testcases"
    headers = {
        "Authorization": f"Bearer {ZEPHYR_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "projectKey": project_key,
        "name": name,
        "scriptType": "MANUAL",
        "automated": False
    }

    print("📤 Creating test case in Zephyr...")
    print("📤 Final Zephyr Payload:")
    print(json.dumps(payload, indent=2))  # 👈 For debug purposes

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()
    
def add_test_steps(test_case_key, steps):
    headers = {
        "Authorization": f"Bearer {ZEPHYR_TOKEN}",
        "Content-Type": "application/json"
    }

    for idx, step in enumerate(steps, 1):
        url = f"{ZEPHYR_BASE_URL}/testcases/{test_case_key}/teststeps"
        payload = {
            "mode": "APPEND",  # ✅ This line fixes the error
            "step": step.get("action", f"Step {idx}").strip(),
            "expectedResult": step.get("expectedResult", "No Expected Result").strip(),
            "testData": step.get("testData", "").strip(),
            "type": "INLINE"
        }

        print(f"➕ Adding step {idx} to {test_case_key}...")
        print(json.dumps(payload, indent=2))

        response = requests.post(url, headers=headers, json=payload)
        if response.status_code != 201:
            print(f"❌ Failed to add step {idx}: {response.status_code}")
            print(response.text)
        else:
            print(f"✅ Step {idx} added.")



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

        print(f"\n🐞 Issue Key: {key}")
        print(f"📝 Summary: {summary}")
        print(f"☑️ Checkbox Set: {checkbox}")
        print(f"📋 Repro Steps Field Type: {type(description)}")
        print(f"📋 Repro Steps Raw Value:\n{description}")

        if checkbox and description:
            print("🔍 Extracting steps...")
            steps = extract_repro_steps(description)
            print(f"📄 Extracted Steps: {json.dumps(steps, indent=2)}")

            if not steps:
                print("⚠️ No steps extracted! Repro format may be unsupported.")
            else:
                test_case = create_test_case(ZEPHYR_PROJECT_KEY, summary)
                print(f"✅ Created Zephyr Test Case: {test_case['key']}")
                add_test_steps(test_case['key'], steps)
        else:
            print(f"⚠️ Skipping {key}: Missing checkbox or repro steps.")
