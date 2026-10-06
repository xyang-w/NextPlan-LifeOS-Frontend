#!/usr/bin/env python3
import json
import hashlib
import os
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / 'state.json'
OPENAPI_FILE = ROOT / 'openapi.json'

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

def extract_learning_details(text, milestones):
    """Attach a concise topic/progress/detail summary to each top-level project."""
    blocks = []
    matches = list(re.finditer(r'(?:Current Project|当前项目)\s*[:：]\s*([^|\n]+)', text, flags=re.I))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        name = re.sub(r'\s+', ' ', match.group(1)).strip()
        blocks.append((name, text[match.end():end]))

    details = []
    for item in milestones:
        target = item['name'].lower()
        block = next((body for name, body in blocks if target in name.lower() or name.lower() in target), '')
        topic_match = re.search(r'(?:Current Topic|当前内容)\s*[:：]\s*([^|\n]+)', block, flags=re.I)
        progress_match = re.search(r'(?:Progress|进度)\s*[:：]\s*([^|\n]+)', block, flags=re.I)
        small = []

        review_match = re.search(r'(?:Review Tasks|复习任务).*?(?=\n\s*\S[^\n]{0,80}:|\Z)', block, flags=re.I | re.S)
        review_text = review_match.group(0) if review_match else block
        for line in review_text.splitlines():
            raw_line = line.strip()
            numbered = re.match(r'^\s*(?:[🔄✅⬜⏭️]\s*)?\d+[.)]\s*', raw_line)
            if not numbered and not re.match(r'^\s*Q\s*:', raw_line, flags=re.I):
                continue
            line = re.sub(r'^\s*[-•]\s*', '', raw_line).strip()
            line = re.sub(r'^\s*[🔄✅⬜⏭️]?\s*\d+[.)]\s*', '', line).strip()
            if re.search(r'current project|当前项目|current topic|当前内容|progress|进度|overall project|总体项目|^project\s*\d+\s*[—:-]', line, flags=re.I):
                continue
            if 5 <= len(line) <= 140 and line not in small:
                small.append(line)
            if len(small) >= 7:
                break
        item['details'] = small[:7]
        item['topic'] = re.sub(r'\s+', ' ', topic_match.group(1)).strip() if topic_match else ''
        item['progress'] = re.sub(r'\s+', ' ', progress_match.group(1)).strip() if progress_match else ''
        details.append(item)
    return details

def aggregate_status(items):
    statuses = [item.get('status') for item in items]
    if statuses and all(status in ('completed', 'done') for status in statuses):
        return 'completed'
    if any(status == 'active' for status in statuses):
        return 'active'
    return 'planned'

def compact_note(project_name, milestones):
    lines = [f'主线项目：{project_name}', '']
    for index, item in enumerate(milestones, 1):
        lines.append(f'{index}. {item["name"]} · {item["status"]}')
        if item.get('topic'):
            lines.append(f'   学习主题：{item["topic"]}')
        if item.get('progress'):
            lines.append(f'   学习进度：{item["progress"]}')
        for detail in item.get('details', [])[:4]:
            lines.append(f'   - {detail}')
    return '\n'.join(lines)[:5000]

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
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self): self._send(204, {})

    def do_GET(self):
        if self.path.rstrip('/') in ('/health', '/api/health'):
            return self._send(200, {'ok': True, 'service': 'NextPlan local sync', 'time': now()})
        if self.path.rstrip('/') == '/api/state':
            return self._send(200, load_state())
        if self.path.rstrip('/') in ('/openapi.json', '/api/agent/openapi.json'):
            try:
                return self._send(200, json.loads(OPENAPI_FILE.read_text()))
            except Exception as exc:
                return self._send(500, {'ok': False, 'error': f'openapi_unavailable: {exc}'})
        if self.path.rstrip('/') == '/api/agent/state':
            if not authorized(self.headers.get('Authorization', '')):
                return self._send(401, {'ok': False, 'error': 'unauthorized'})
            return self._send(200, agent_state(load_state()))
        self._send(404, {'ok': False, 'error': 'not_found'})

    def do_POST(self):
        if self.path.rstrip('/') in ('/api/agent/advance', '/api/agent/schedule-review'):
            if not authorized(self.headers.get('Authorization', '')):
                return self._send(401, {'ok': False, 'error': 'unauthorized'})
            return self.handle_agent_action(self.path.rstrip('/'))
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
            conversation_title = str(conversation.get('title') or '').strip()
            title = (conversation_title if conversation_title and not conversation_title.lower().startswith('chatgpt') else extract_title(text, 'ChatGPT conversation'))
            project_name = (conversation_title if conversation_title and not conversation_title.lower().startswith('chatgpt') else extract_project_name(text, title))
            source_url = str(conversation.get('url', '') or '')
            identity = source_url or project_name
            project_id = 'project-' + hashlib.sha1(identity.encode('utf-8')).hexdigest()[:12]
            milestones = extract_milestones(text) or [{'name': title, 'status': 'active'}]
            milestones = extract_learning_details(text, milestones)
            for item in milestones:
                item['id'] = f'{project_id}-task-{len(item.get("name", ""))}-{milestones.index(item) + 1}'
                item['desc'] = item.get('topic') or f'学习并复习 {item["name"]}'
            project = {'id': project_id, 'name': project_name, 'category': category_for(text), 'status': aggregate_status(milestones), 'priority': 2, 'next_action': project_name, 'milestones': milestones, 'source': source_url, 'updated_at': now()}
            note = {'id': f'chat-{int(datetime.now().timestamp())}', 'title': project_name,
                    'body': compact_note(project_name, milestones), 'category': '其他', 'at': now(),
                    'source': source_url, 'project_id': project_id, 'tags': ['chatgpt', 'synced', 'summary']}
            projects = state.setdefault('projects', [])
            projects[:] = [item for item in projects if item.get('source') != source_url or item.get('id') == project_id]
            existing = next((item for item in projects if item.get('id') == project_id), None)
            if existing: existing.update(project); change_type = 'update_project'
            else: projects.insert(0, project); change_type = 'create_project'
            notes = state.setdefault('notes', [])
            if source_url:
                notes[:] = [item for item in notes if item.get('source') != source_url]
            notes.insert(0, note)
            state.setdefault('events', []).insert(0, {'type': 'chat_sync', 'summary': f'Synced: {title}', 'project_id': project_id, 'at': now()})
            state.setdefault('system', {})['last_updated'] = now()
            save_state(state)
            return self._send(200, {'ok': True, 'status': 'preview', 'changes': [{'type': change_type, 'title': project_name}, {'type': 'create_tasks', 'count': len(milestones)}, {'type': 'create_note', 'title': title}], 'state': state})
        except Exception as exc:
            return self._send(400, {'ok': False, 'error': str(exc)})

    def handle_agent_action(self, path):
        try:
            length = int(self.headers.get('Content-Length', '0'))
            payload = json.loads(self.rfile.read(length) or '{}')
            state = load_state()
            project = find_agent_project(state, payload.get('project_id'))
            if not project:
                return self._send(404, {'ok': False, 'error': 'no_active_project'})

            if path == '/api/agent/advance':
                result = advance_project(state, project, payload)
            else:
                result = schedule_review(state, project, payload)
            state.setdefault('system', {})['last_updated'] = now()
            save_state(state)
            return self._send(200, {'ok': True, 'action': path.rsplit('/', 1)[-1], **result, 'state': agent_state(state)})
        except ValueError as exc:
            return self._send(400, {'ok': False, 'error': str(exc)})
        except Exception as exc:
            return self._send(500, {'ok': False, 'error': str(exc)})

    def log_message(self, fmt, *args):
        print(f'[{datetime.now().strftime("%H:%M:%S")}] {fmt % args}')

def authorized(header):
    expected = os.environ.get('NEXTPLAN_AGENT_API_KEY', '').strip()
    return bool(expected) and header == f'Bearer {expected}'

def find_agent_project(state, project_id=None):
    projects = state.get('projects', [])
    if project_id:
        return next((p for p in projects if str(p.get('id')) == str(project_id)), None)
    return next((p for p in projects if p.get('status') == 'active'), projects[0] if projects else None)

def task_status(task):
    return 'completed' if task.get('status') in ('done', 'completed') else task.get('status', 'planned')

def current_task(project):
    milestones = project.get('milestones') or []
    return next((m for m in milestones if task_status(m) == 'active'), None)

def next_task(project):
    milestones = project.get('milestones') or []
    return next((m for m in milestones if task_status(m) == 'planned'), None)

def agent_state(state):
    project = find_agent_project(state)
    if not project:
        return {'project': None, 'current_task': None, 'next_task': None, 'projects': [], 'reviews': []}
    reviews = [event for event in state.get('calendar_events', []) if event.get('kind') == 'review']
    return {
        'project': {'id': project.get('id'), 'name': project.get('name'), 'status': project.get('status'), 'next_action': project.get('next_action')},
        'current_task': current_task(project),
        'next_task': next_task(project),
        'tasks': project.get('milestones', []),
        'projects': [{'id': p.get('id'), 'name': p.get('name'), 'status': p.get('status')} for p in state.get('projects', [])],
        'reviews': reviews[-20:]
    }

def refresh_project_status(project):
    milestones = project.get('milestones') or []
    project['status'] = aggregate_status(milestones)
    active = current_task(project)
    planned = next_task(project)
    project['next_action'] = project.get('name') if not active and not planned else (active or planned).get('name')
    project['updated_at'] = now()

def advance_project(state, project, payload):
    milestones = project.get('milestones') or []
    target_id = payload.get('task_id')
    task = next((m for m in milestones if str(m.get('id')) == str(target_id)), None) if target_id else current_task(project)
    if not task:
        task = next_task(project)
    if not task:
        raise ValueError('no_current_or_next_task')
    task['status'] = 'completed'
    task['completed_at'] = now()
    for candidate in milestones:
        if task_status(candidate) == 'planned':
            candidate['status'] = 'active'
            break
    refresh_project_status(project)
    state.setdefault('events', []).insert(0, {'type': 'agent_advance', 'summary': f'Advanced {project.get("name")}: {task.get("name")}', 'project_id': project.get('id'), 'task_id': task.get('id'), 'at': now()})
    return {'completed_task': task, 'current_task': current_task(project), 'next_task': next_task(project)}

def schedule_review(state, project, payload):
    scheduled_for = str(payload.get('scheduled_for') or payload.get('when') or '').strip()
    if not scheduled_for:
        raise ValueError('scheduled_for is required; use an ISO-8601 date/time')
    task = next((m for m in project.get('milestones', []) if str(m.get('id')) == str(payload.get('task_id'))), None) or current_task(project) or next_task(project)
    event = {'id': f'review-{int(datetime.now().timestamp())}', 'title': payload.get('title') or f'Review {task.get("name") if task else project.get("name")}', 'date': scheduled_for[:10], 'time': scheduled_for[11:16] if len(scheduled_for) > 15 else '', 'kind': 'review', 'type': 'review', 'scheduled_for': scheduled_for, 'project_id': project.get('id'), 'task_id': task.get('id') if task else None, 'note': payload.get('note', ''), 'created_at': now()}
    state.setdefault('calendar_events', []).append(event)
    state.setdefault('events', []).insert(0, {'type': 'review_scheduled', 'summary': event['title'], 'project_id': project.get('id'), 'task_id': event.get('task_id'), 'at': now()})
    return {'review': event}

if __name__ == '__main__':
    port = int(os.environ.get('PORT', os.environ.get('NEXTPLAN_PORT', '8000')))
    host = os.environ.get('HOST', '0.0.0.0')
    print(f'NextPlan local sync listening on http://{host}:{port}')
    ThreadingHTTPServer((host, port), Handler).serve_forever()
