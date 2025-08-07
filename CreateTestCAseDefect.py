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

def zephyr_key_already_commented(issue_key, keyword="PREC-T"):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment"
    headers = {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json"
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"⚠️ Could not fetch comments for {issue_key}")
        return False

    comments = response.json().get("comments", [])
    for comment in comments:
        body = comment.get("body")
        if isinstance(body, dict):  # ADF format
            body_text = json.dumps(body)
            if keyword in body_text:
                return True
        elif isinstance(body, str):  # plain string fallback
            if keyword in body:
                return True
    return False



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
        "scriptType": "STEP_BY_STEP",
        "automated": False
    }

    print("📤 Creating test case in Zephyr...")
    print("📤 Final Zephyr Payload:")
    print(json.dumps(payload, indent=2))  # 👈 For debug purposes

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()
    
def rich_text_paragraph(text):
    return {
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": text
                    }
                ]
            }
        ]
    }
def to_adf(text):
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": text
                    }
                ]
            }
        ]
    }

def post_zephyr_comment(issue_key, zephyr_key):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment"
    headers = {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json"
    }
    body = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": f"🧪 Linked Zephyr Test Case: {zephyr_key}"
                        }
                    ]
                }
            ]
        }
    }

    response = requests.post(url, headers=headers, json=body)
    if response.status_code == 201:
        print(f"✅ Comment added to {issue_key}")
    else:
        print(f"❌ Failed to comment on {issue_key}")
        print(response.text)


def add_test_steps(test_case_key, steps):
    url = f"{ZEPHYR_BASE_URL}/testcases/{test_case_key}/teststeps"
    headers = {
        "Authorization": f"Bearer {ZEPHYR_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "mode": "OVERWRITE",
        "items": []
    }

    for idx, step in enumerate(steps, 1):
        step_text = (step.get("action") or "").strip()
        expected = (step.get("expectedResult") or "No Expected Result").strip()
        data = (step.get("testData") or "").strip()
        
        # 🛑 Skip if step text is empty
        if not step_text:
            print(f"⚠️ Skipping Step {idx} – empty step text")
            continue


        print(f"🧪 Step {idx}:")
        print(f"    step = '{step_text}'")
        print(f"    expectedResult = '{expected}'")
        print(f"    testData = '{data}'")

        payload["items"].append({
            "inline": {
                "description": step_text,
                "expectedResult": expected,
                "testData": data
            }
        })





    print(f"📤 URL: {url}")
    print(f"📤 Headers:\n{json.dumps(headers, indent=2)}")
    print(f"📤 Payload:\n{json.dumps(payload, indent=2)}")

    response = requests.post(url, headers=headers, json=payload)

    print(f"📥 Raw Response Status: {response.status_code}")
    print(f"📥 Raw Response Text:\n{response.text}")

    if response.status_code != 201:
        try:
            print("❌ Zephyr API Error:")
            print(json.dumps(response.json(), indent=2))
        except:
            print("❌ Non-JSON error response.")
    else:
        print("✅ Steps added successfully.")
def fetch_test_steps(test_case_key):
    url = f"{ZEPHYR_BASE_URL}/testcases/{test_case_key}/teststeps"
    headers = {
        "Authorization": f"Bearer {ZEPHYR_TOKEN}",
        "Content-Type": "application/json"
    }

    print(f"🔍 Fetching test steps from {url} ...")
    response = requests.get(url, headers=headers)

    print(f"📥 Fetch Status: {response.status_code}")
    try:
        response.raise_for_status()
        steps = response.json().get("values", [])
        print("📋 Stored Steps in Zephyr:")
        for i, step in enumerate(steps, 1):
            inline = step.get("inline", {})
            print(f"  Step {i}:")
            print(f"    Description: {inline.get('description')}")
            print(f"    Test Data: {inline.get('testData')}")
            print(f"    Expected Result: {inline.get('expectedResult')}")

    except Exception as e:
        print("❌ Failed to fetch stored steps.")
        print(response.text)


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

            if checkbox and description:
                print("🔍 Extracting steps...")
                steps = extract_repro_steps(description)
                print(f"📄 Extracted Steps: {json.dumps(steps, indent=2)}")
            
                if not steps:
                    print("⚠️ No steps extracted! Repro format may be unsupported.")
                    continue
            
                # ✅ Skip if test case already linked
                if zephyr_key_already_commented(key, "PREC-T"):
                    print(f"ℹ️ Zephyr test case already linked in {key}. Skipping...")
                    continue
            
                # ✅ Now safe to create a new Zephyr test case
                test_case = create_test_case(ZEPHYR_PROJECT_KEY, summary)
                zephyr_key = test_case['key']
                print(f"✅ Created Zephyr Test Case: {zephyr_key}")
            
                post_zephyr_comment(key, zephyr_key)
                add_test_steps(zephyr_key, steps)
                fetch_test_steps(zephyr_key)


        else:
            print(f"⚠️ Skipping {key}: Missing checkbox or repro steps.")
