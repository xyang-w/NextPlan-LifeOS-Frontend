#!/usr/bin/env python3
import json
import os
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / 'state.json'

def now():
    return datetime.now(timezone.utc).isoformat()

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {'schema_version': 2, 'system': {'name': 'NextPlan', 'last_updated': None},
            'projects': [], 'events': [], 'notes': [], 'resources': [],
            'deadlines': [], 'calendar_events': []}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')

def extract_title(text, fallback):
    for line in text.splitlines():
        line = re.sub(r'^[#\-\s✅🔄⏭️⬜]+', '', line).strip()
        if 3 <= len(line) <= 100 and ('project' in line.lower() or '项目' in line):
            return re.sub(r'^.*?Project\s*\d+\s*[—:-]\s*', '', line, flags=re.I) or line
    return fallback

def extract_project_name(text, fallback):
    patterns = [r'(?:Current Project|当前项目)\s*[:：]\s*([^|\n]+)', r'(?:Project|项目)\s*[:：]\s*([^|\n]+)']
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            name = match.group(1).strip(' \t:：')
            if 2 <= len(name) <= 120: return name
    return fallback

def extract_milestones(text):
    items = []
    pattern = re.compile(r'([✅⏭️🔄⬜]?)\s*Project\s*\d+\s*[—:-]\s*([^\n（(]+)', re.I)
    for match in pattern.finditer(text):
        name = re.sub(r'\s+', ' ', match.group(2)).strip(' \t-–—|')
        if not name or name in [item['name'] for item in items]: continue
        emoji = match.group(1)
        status = 'completed' if emoji == '✅' else ('active' if emoji == '🔄' else 'planned')
        items.append({'name': name[:160], 'status': status})
    return items[:5]

def category_for(text):
    lowered = text.lower()
    if any(word in lowered for word in ('phd', 'research', '科研', '论文')): return '科研'
    if any(word in lowered for word in ('course', '学习', '课程', 'interview', '面试')): return '课程'
    if any(word in lowered for word in ('job', '求职', 'career', '招聘')): return '行政'
    return '其他'

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self): self._send(204, {})

    def do_GET(self):
        if self.path.rstrip('/') in ('/health', '/api/health'):
            return self._send(200, {'ok': True, 'service': 'NextPlan local sync', 'time': now()})
        if self.path.rstrip('/') == '/api/state':
            return self._send(200, load_state())
        self._send(404, {'ok': False, 'error': 'not_found'})

    def do_POST(self):
        if self.path.rstrip('/') != '/api/chat/sync':
            return self._send(404, {'ok': False, 'error': 'not_found'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            body = json.loads(self.rfile.read(length))
            conversation = body.get('conversation') or {}
            messages = conversation.get('messages') or []
            text = '\n\n'.join(str(m.get('text', '')) for m in messages).strip()
            if not text:
                return self._send(400, {'ok': False, 'error': 'empty_conversation'})
            state = load_state()
            title = extract_title(text, conversation.get('title') or 'ChatGPT conversation')
            conversation_title = str(conversation.get('title') or '').strip()
            project_name = (conversation_title if conversation_title and not conversation_title.lower().startswith('chatgpt') else extract_project_name(text, title))
            project_id = 'project-' + re.sub(r'[^a-z0-9]+', '-', project_name.lower()).strip('-')[:60]
            milestones = extract_milestones(text) or [{'name': title, 'status': 'active'}]
            project = {'id': project_id, 'name': project_name, 'category': category_for(text), 'status': 'active', 'priority': 2, 'next_action': project_name, 'milestones': [{'id': f'{project_id}-task-{i + 1}', 'name': item['name'], 'status': item['status'], 'desc': f'Review {item["name"]}'} for i, item in enumerate(milestones)], 'source': conversation.get('url', ''), 'updated_at': now()}
            note = {'id': f'chat-{int(datetime.now().timestamp())}', 'title': title,
                    'body': text[:120000], 'category': '其他', 'at': now(),
                    'source': conversation.get('url', ''), 'project_id': project_id, 'tags': ['chatgpt', 'synced']}
            projects = state.setdefault('projects', [])
            source_url = conversation.get('url', '')
            projects[:] = [item for item in projects if item.get('source') != source_url or item.get('id') == project_id]
            existing = next((item for item in projects if item.get('id') == project_id), None)
            if existing: existing.update(project); change_type = 'update_project'
            else: projects.insert(0, project); change_type = 'create_project'
            state.setdefault('notes', []).insert(0, note)
            state.setdefault('events', []).insert(0, {'type': 'chat_sync', 'summary': f'Synced: {title}', 'project_id': project_id, 'at': now()})
            state.setdefault('system', {})['last_updated'] = now()
            save_state(state)
            return self._send(200, {'ok': True, 'status': 'preview', 'changes': [{'type': change_type, 'title': project_name}, {'type': 'create_tasks', 'count': len(milestones)}, {'type': 'create_note', 'title': title}], 'state': state})
        except Exception as exc:
            return self._send(400, {'ok': False, 'error': str(exc)})

    def log_message(self, fmt, *args):
        print(f'[{datetime.now().strftime("%H:%M:%S")}] {fmt % args}')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', os.environ.get('NEXTPLAN_PORT', '8000')))
    host = os.environ.get('HOST', '0.0.0.0')
    print(f'NextPlan local sync listening on http://{host}:{port}')
    ThreadingHTTPServer((host, port), Handler).serve_forever()
