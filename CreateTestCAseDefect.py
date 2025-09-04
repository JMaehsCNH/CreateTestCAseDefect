import os, re, json, base64, requests

# ======== CONFIG ========
JIRA_BASE_URL   = "https://cnhpd.atlassian.net"
ZEPHYR_BASE_URL = "https://api.zephyrscale.smartbear.com/v2"

JIRA_EMAIL      = "john.maehs@cnh.com"
JIRA_API_TOKEN  = os.getenv("JIRA_API_TOKEN")           # required
ZEPHYR_TOKEN    = os.getenv("ZEPHYR_TOKEN")             # required
ZEPHYR_PROJECT_KEY = "PREC"

# Jira custom field IDs (adjust to your site)
REPRO_STEPS_FIELD = "customfield_13101"     # repro steps (ADF or text)
CHECKBOX_FIELD    = "customfield_14242"     # "Create Test Case" checkbox
CHECKBOX_FIELD_NAME = "Create Test Case"    # label in the UI (for JQL)

# ======== AUTH HEADERS ========
if not (JIRA_EMAIL and JIRA_API_TOKEN):
    raise SystemExit("❌ Missing JIRA_EMAIL or JIRA_API_TOKEN.")

jira_b64 = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
JIRA_HEADERS_JSON = {
    "Authorization": f"Basic {jira_b64}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

ZEPHYR_HEADERS_JSON = {
    "Authorization": f"Bearer {ZEPHYR_TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

print("🔐 Testing Jira authentication...")
me = requests.get(f"{JIRA_BASE_URL}/rest/api/3/myself", headers=JIRA_HEADERS_JSON)
print(f"Auth status: {me.status_code}")
if me.status_code != 200:
    print("❌ Jira authentication failed.")
    print(me.text)
    raise SystemExit(1)
print("✅ Jira authentication successful.")

# ======== HELPERS ========
def jira_search_jql(jql: str, fields=None, max_results=50):
    """
    Use the new POST /rest/api/3/search/jql with nextPageToken pagination.
    """
    url = f"{JIRA_BASE_URL}/rest/api/3/search/jql"
    body = {
        "jql": jql,
        "maxResults": max_results,
        "fields": fields or []
    }

    all_issues = []
    next_page = None
    page = 0

    while True:
        page += 1
        payload = dict(body)
        if next_page:
            payload["nextPageToken"] = next_page

        r = requests.post(url, headers=JIRA_HEADERS_JSON, json=payload)
        if r.status_code != 200:
            print("❌ Jira Search Error:")
            print(f"Status Code: {r.status_code}")
            print(f"URL: {url}")
            print(f"JQL: {jql}")
            print(f"Body sent: {json.dumps(payload, indent=2)}")
            print(f"Response: {r.text}")
            r.raise_for_status()

        data = r.json()
        issues = data.get("issues", [])
        print(f"📄 Search page {page} → {len(issues)} issues")
        all_issues.extend(issues)

        if data.get("isLast", True):
            break
        next_page = data.get("nextPageToken")
        if not next_page:
            break

    print(f"📊 Total issues fetched: {len(all_issues)}")
    return all_issues

def zephyr_key_already_commented(issue_key, keyword="PREC-T"):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment"
    r = requests.get(url, headers=JIRA_HEADERS_JSON)
    if r.status_code != 200:
        print(f"⚠️ Could not fetch comments for {issue_key}: {r.status_code}")
        return False

    comments = r.json().get("comments", [])
    for c in comments:
        body = c.get("body")
        if isinstance(body, dict):  # ADF
            if keyword in json.dumps(body):
                return True
        elif isinstance(body, str):
            if keyword in body:
                return True
    return False

def extract_repro_steps(adf_or_text):
    # Fallback: plain text with "1. Step" lines
    if isinstance(adf_or_text, str):
        lines = adf_or_text.splitlines()
        steps, step = [], ""
        for line in lines:
            m = re.match(r"^\s*\d+\.\s*(.*)", line)
            if m:
                if step:
                    steps.append({"action": step.strip()})
                step = m.group(1)
            else:
                step += ("\n" + line)
        if step:
            steps.append({"action": step.strip()})
        return steps

    # ADF ordered list → extract text per list item
    steps = []
    try:
        for block in adf_or_text.get("content", []):
            if block.get("type") == "orderedList":
                for item in block.get("content", []):
                    step_text = ""
                    for paragraph in item.get("content", []):
                        for part in (paragraph.get("content", []) or []):
                            if part.get("type") == "text":
                                step_text += part.get("text", "")
                    if step_text.strip():
                        steps.append({"action": step_text.strip()})
    except Exception as e:
        print(f"⚠️ Error parsing ADF: {e}")
    return steps

def create_test_case(project_key, name):
    url = f"{ZEPHYR_BASE_URL}/testcases"
    payload = {
        "projectKey": project_key,
        "name": name,
        "scriptType": "STEP_BY_STEP",
        "automated": False
    }
    print("📤 Creating test case in Zephyr…")
    print(json.dumps(payload, indent=2))
    r = requests.post(url, headers=ZEPHYR_HEADERS_JSON, json=payload)
    if r.status_code not in (200, 201):
        print("❌ Zephyr create failed:")
        print(r.text)
        r.raise_for_status()
    return r.json()

def post_zephyr_comment(issue_key, zephyr_key):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment"
    body = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [{
                "type": "paragraph",
                "content": [{"type": "text", "text": f"🧪 Linked Zephyr Test Case: {zephyr_key}"}]
            }]
        }
    }
    r = requests.post(url, headers=JIRA_HEADERS_JSON, json=body)
    if r.status_code == 201:
        print(f"✅ Comment added to {issue_key}")
    else:
        print(f"❌ Failed to comment on {issue_key}: {r.status_code}")
        print(r.text)

def add_test_steps(test_case_key, steps):
    url = f"{ZEPHYR_BASE_URL}/testcases/{test_case_key}/teststeps"
    payload = {"mode": "OVERWRITE", "items": []}

    for idx, step in enumerate(steps, 1):
        step_text = (step.get("action") or "").strip()
        expected   = (step.get("expectedResult") or "No Expected Result").strip()
        data       = (step.get("testData") or "").strip()
        if not step_text:
            print(f"⚠️ Skipping Step {idx} – empty step text")
            continue
        print(f"🧪 Step {idx}: step='{step_text}' expected='{expected}' data='{data}'")
        payload["items"].append({
            "inline": {
                "description": step_text,
                "expectedResult": expected,
                "testData": data
            }
        })

    print("📤 Pushing steps to Zephyr…")
    print(json.dumps(payload, indent=2))
    r = requests.post(url, headers=ZEPHYR_HEADERS_JSON, json=payload)
    print(f"📥 Zephyr response: {r.status_code}")
    if r.status_code != 201:
        print(r.text)
        r.raise_for_status()
    else:
        print("✅ Steps added successfully.")

def fetch_test_steps(test_case_key):
    url = f"{ZEPHYR_BASE_URL}/testcases/{test_case_key}/teststeps"
    r = requests.get(url, headers=ZEPHYR_HEADERS_JSON)
    print(f"🔍 Fetch steps: {r.status_code}")
    if r.status_code == 200:
        vals = r.json().get("values", [])
        for i, s in enumerate(vals, 1):
            inline = s.get("inline", {})
            print(f"  {i}. {inline.get('description')}  | exp={inline.get('expectedResult')} | data={inline.get('testData')}")
    else:
        print(r.text)

# ======== MAIN ========
# Only pick Bugs with the checkbox checked
jql = f'project = {ZEPHYR_PROJECT_KEY} AND issuetype = Bug AND "{CHECKBOX_FIELD_NAME}" = "{CHECKBOX_FIELD_NAME}"'
print(f"🔎 JQL: {jql}")

issues = jira_search_jql(
    jql,
    fields=[REPRO_STEPS_FIELD, CHECKBOX_FIELD, "summary", "project", "issuetype"],
    max_results=100
)

if not issues:
    print("ℹ️ No matching Bugs found with Test Case checkbox checked.")
    raise SystemExit(0)

for issue in issues:
    key         = issue["key"]
    fields      = issue.get("fields", {}) or {}
    summary     = fields.get("summary", "")
    checkbox    = fields.get(CHECKBOX_FIELD, False)
    description = fields.get(REPRO_STEPS_FIELD, "")

    print(f"\n🐞 {key} — {summary}")
    print(f"☑️ Checkbox Set: {checkbox}")
    print(f"📋 Repro Steps Type: {type(description)}")

    if not (checkbox and description):
        print(f"⚠️ Skipping {key}: missing checkbox or repro steps.")
        continue

    # Don’t double-create
    if zephyr_key_already_commented(key, "PREC-T"):
        print(f"ℹ️ Zephyr test case already linked in {key}. Skipping…")
        continue

    steps = extract_repro_steps(description)
    if not steps:
        print("⚠️ No steps extracted (unsupported format?).")
        continue

    # Create Zephyr test case
    tc = create_test_case(ZEPHYR_PROJECT_KEY, summary)
    zephyr_key = tc["key"]
    print(f"✅ Created Zephyr Test Case: {zephyr_key}")

    # Comment back to Jira, then push steps
    post_zephyr_comment(key, zephyr_key)
    add_test_steps(zephyr_key, steps)
    fetch_test_steps(zephyr_key)
