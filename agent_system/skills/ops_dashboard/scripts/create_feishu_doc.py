#!/usr/bin/env python3
"""Convert markdown report to Feishu docx document."""

import os
import re
import json
import time
import uuid
import requests

APP_ID = os.environ['FEISHU_APP_ID']
APP_SECRET = os.environ['FEISHU_APP_SECRET']
BASE = 'https://open.feishu.cn'
REPORT_PATH = '/Users/frank/.hermes/hermes-agent-official/agent_system/skills/voc_insight/output/user_persona_and_settings_crossvalidation_report.md'


def get_token():
    r = requests.post(
        BASE + '/open-apis/auth/v3/tenant_access_token/internal/',
        json={'app_id': APP_ID, 'app_secret': APP_SECRET},
        timeout=20,
    )
    data = r.json()
    if data.get('code') != 0:
        raise RuntimeError(f"Token error: {data}")
    return data['tenant_access_token']


def create_doc(token, title):
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json; charset=utf-8',
    }
    r = requests.post(
        BASE + '/open-apis/docx/v1/documents',
        headers=headers,
        json={'title': title},
        timeout=20,
    )
    data = r.json()
    if data.get('code') != 0:
        raise RuntimeError(f"Create doc error: {data}")
    doc_id = data['data']['document']['document_id']
    # Construct URL manually since response may not include it
    url = f"https://nousresearch.feishu.cn/docx/{doc_id}"
    return doc_id, url


def make_block(line):
    """Parse a single markdown line into a Feishu block."""
    line = line.rstrip('\n')
    if not line:
        return None

    # Heading 1
    if line.startswith('# ') and not line.startswith('## '):
        text = line[2:].strip()
        return {
            'block_type': 3,
            'heading1': {
                'elements': [{'text_run': {'content': text, 'text_element_style': {}}}],
                'style': {}
            }
        }

    # Heading 2
    if line.startswith('## ') and not line.startswith('### '):
        text = line[3:].strip()
        return {
            'block_type': 4,
            'heading2': {
                'elements': [{'text_run': {'content': text, 'text_element_style': {}}}],
                'style': {}
            }
        }

    # Heading 3 and 4 (use heading3 block type)
    if line.startswith('### ') or line.startswith('#### '):
        text = line.lstrip('#').strip()
        return {
            'block_type': 5,
            'heading3': {
                'elements': [{'text_run': {'content': text, 'text_element_style': {}}}],
                'style': {}
            }
        }

    # Skip horizontal rules
    if line.strip() == '---':
        return None

    # Blockquote
    if line.startswith('> '):
        text = '💡 ' + line[2:].strip()
        return {
            'block_type': 2,
            'text': {
                'elements': [{'text_run': {'content': text, 'text_element_style': {}}}],
                'style': {}
            }
        }

    # Bullet list item
    if line.strip().startswith('- ') or line.strip().startswith('* '):
        text = '• ' + line.strip()[2:].strip()
        return {
            'block_type': 2,
            'text': {
                'elements': [{'text_run': {'content': text, 'text_element_style': {}}}],
                'style': {}
            }
        }

    # Numbered list item
    m = re.match(r'^(\s*)(\d+)\.\s+(.*)$', line)
    if m:
        text = f"{m.group(2)}. {m.group(3)}"
        return {
            'block_type': 2,
            'text': {
                'elements': [{'text_run': {'content': text, 'text_element_style': {}}}],
                'style': {}
            }
        }

    # Table row - preserve as text
    if '|' in line:
        return {
            'block_type': 2,
            'text': {
                'elements': [{'text_run': {'content': line, 'text_element_style': {}}}],
                'style': {}
            }
        }

    # Regular paragraph
    return {
        'block_type': 2,
        'text': {
            'elements': [{'text_run': {'content': line, 'text_element_style': {}}}],
            'style': {}
        }
    }


def parse_markdown(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    blocks = []
    in_code_block = False
    code_buffer = []

    for line in lines:
        stripped = line.strip()

        # Code block handling
        if stripped.startswith('```'):
            if in_code_block and code_buffer:
                # Flush code buffer
                code_text = '\n'.join(code_buffer)
                blocks.append({
                    'block_type': 2,
                    'text': {
                        'elements': [{'text_run': {'content': code_text, 'text_element_style': {}}}],
                        'style': {}
                    }
                })
                code_buffer = []
            in_code_block = not in_code_block
            continue

        if in_code_block:
            code_buffer.append(line.rstrip('\n'))
            continue

        block = make_block(line)
        if block:
            blocks.append(block)

    return blocks


def write_batches(token, doc_id, blocks, batch_size=45):
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json; charset=utf-8',
    }

    total = len(blocks)
    success_count = 0
    fail_count = 0

    for i in range(0, total, batch_size):
        batch = blocks[i:i+batch_size]
        body = {
            'index': -1,
            'children': batch,
        }

        r = requests.post(
            BASE + f'/open-apis/docx/v1/documents/{doc_id}/blocks/{doc_id}/children',
            headers=headers,
            params={'document_revision_id': -1, 'client_token': str(uuid.uuid4())},
            json=body,
            timeout=30,
        )
        data = r.json()

        if data.get('code') == 0:
            success_count += len(batch)
            print(f"Batch {i//batch_size + 1}/{(total-1)//batch_size + 1}: OK ({len(batch)} blocks)")
        else:
            fail_count += len(batch)
            print(f"Batch {i//batch_size + 1}: FAILED - {data}")

        if i + batch_size < total:
            time.sleep(0.5)

    return success_count, fail_count


def set_permissions(token, doc_id):
    """Set tenant-wide edit permissions."""
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json; charset=utf-8',
    }
    r = requests.patch(
        BASE + f'/open-apis/drive/v1/permissions/{doc_id}/public',
        headers=headers,
        params={'type': 'docx'},
        json={
            'external_access': False,
            'security_entity': 'anyone_can_edit',
            'comment_entity': 'anyone_can_view',
            'share_entity': 'same_tenant',
            'link_share_entity': 'tenant_editable',
        },
        timeout=20,
    )
    data = r.json()
    print(f"Permission set response: {json.dumps(data, indent=2, ensure_ascii=False)}")
    return data.get('code') == 0


def add_collaborator(token, doc_id, open_id):
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json; charset=utf-8',
    }
    r = requests.post(
        BASE + f'/open-apis/drive/v1/permissions/{doc_id}/members',
        headers=headers,
        params={'type': 'docx', 'need_notification': 'false'},
        json={
            'member_type': 'openid',
            'member_id': open_id,
            'perm': 'full_access',
        },
        timeout=20,
    )
    data = r.json()
    print(f"Add collaborator response: {json.dumps(data, indent=2, ensure_ascii=False)}")
    return data.get('code') == 0


def find_user_open_id(token, name):
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json; charset=utf-8',
    }
    r = requests.get(
        BASE + '/open-apis/contact/v3/users',
        headers=headers,
        params={'user_id_type': 'open_id', 'page_size': 100},
        timeout=20,
    )
    data = r.json()
    if data.get('code') != 0:
        print(f"List users error: {data}")
        return None

    for user in data.get('data', {}).get('items', []):
        if user.get('name') == name:
            return user.get('open_id')
    return None


def main():
    print("Step 1: Getting access token...")
    token = get_token()
    print("Token acquired.")

    print("\nStep 2: Creating document...")
    title = "用户画像与设置项交叉验证详细报告"
    doc_id, url = create_doc(token, title)
    print(f"Document created: {doc_id}")
    print(f"URL: {url}")

    print("\nStep 3: Parsing markdown...")
    blocks = parse_markdown(REPORT_PATH)
    print(f"Parsed {len(blocks)} blocks from markdown.")

    print("\nStep 4: Writing blocks to document...")
    success, fail = write_batches(token, doc_id, blocks)
    print(f"\nWrite complete: {success} succeeded, {fail} failed.")

    print("\nStep 5: Setting permissions...")
    perm_ok = set_permissions(token, doc_id)
    print(f"Permission set: {'OK' if perm_ok else 'FAILED'}")

    print("\nStep 6: Finding and adding collaborator 杨子枫...")
    open_id = find_user_open_id(token, '杨子枫')
    if open_id:
        print(f"Found 杨子枫: {open_id}")
        add_ok = add_collaborator(token, doc_id, open_id)
        print(f"Add collaborator: {'OK' if add_ok else 'FAILED'}")
    else:
        print("杨子枫 not found in tenant user list.")

    # Also try 王玥琳 if available
    open_id2 = find_user_open_id(token, '王玥琳')
    if open_id2:
        print(f"Found 王玥琳: {open_id2}")
        add_ok = add_collaborator(token, doc_id, open_id2)
        print(f"Add collaborator: {'OK' if add_ok else 'FAILED'}")

    print(f"\n=== FINAL RESULT ===")
    print(f"Document ID: {doc_id}")
    print(f"Document URL: {url}")
    print(f"Blocks written: {success}/{len(blocks)}")

    return doc_id, url


if __name__ == '__main__':
    main()
