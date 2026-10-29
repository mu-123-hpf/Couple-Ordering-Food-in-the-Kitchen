"""Local couple-kitchen server. Python standard library; no third-party services."""
from __future__ import annotations
import argparse
import base64
import copy
from contextlib import contextmanager
from .auth import Accounts, AuthError, SESSION_SECONDS
import hashlib
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import tempfile
import threading
from datetime import datetime, timezone, timedelta
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / 'static'
SEED = ROOT / 'seed.json'
STATUSES = {'pending': '待接单', 'accepted': '制作中', 'completed': '已完成', 'cancelled': '已取消'}
TRANSITIONS = {'pending': {'accepted', 'cancelled'}, 'accepted': {'completed', 'cancelled'}, 'completed': set(), 'cancelled': set()}
MAX_BODY = 800_000

class ValidationError(ValueError):
    pass

def text(value, label, maximum, required=True):
    if not isinstance(value, str): raise ValidationError(f'{label}必须是文字')
    value = value.strip()
    if (required and not value) or len(value) > maximum: raise ValidationError(f'{label}需要1–{maximum}个字' if required else f'{label}不能超过{maximum}个字')
    return value

def integer(value, label, low=1, high=99):
    if type(value) is not int or not low <= value <= high: raise ValidationError(f'{label}应为{low}–{high}的整数')
    return value

def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')

def load_seed():
    return json.loads(SEED.read_text(encoding='utf-8'))

class Store:
    """A single small JSON document in SQLite; every change is an atomic transaction."""
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')
            if db.execute('SELECT 1 FROM state WHERE id=1').fetchone() is None:
                doc = load_seed()
                doc.update(orders=[], revision=1, secret=secrets.token_urlsafe(32))
                for item in doc['menu']: item.update(active=True, sales=0, custom=False)
                db.execute('INSERT INTO state VALUES(1,?)', (json.dumps(doc, ensure_ascii=False),))
    @contextmanager
    def connect(self):
        db = sqlite3.connect(str(self.path), timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()
    def read(self):
        with self.connect() as db: return json.loads(db.execute('SELECT data FROM state WHERE id=1').fetchone()[0])
    def mutate(self, fn):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            doc = json.loads(db.execute('SELECT data FROM state WHERE id=1').fetchone()[0])
            result = fn(doc)
            doc['revision'] += 1
            db.execute('UPDATE state SET data=? WHERE id=1', (json.dumps(doc, ensure_ascii=False),))
            return copy.deepcopy(result)
    def public(self):
        doc = self.read()
        doc.pop('secret', None)
        doc['menu'] = [x for x in doc['menu'] if x.get('active', True)]
        return doc
    def create_order(self, body, actor):
        raw = body.get('items')
        if not isinstance(raw, list) or not 1 <= len(raw) <= 100: raise ValidationError('请先选择1–100项菜单')
        note = text(body.get('note', ''), '备注', 200, False)
        members = Accounts(self.path).users()
        actor = next((u for u in members if u['id'] == actor['id']), None)
        if not actor or len(members) != 2: raise AuthError('请先登录双人厨房', 401)
        recipient = next(u for u in members if u['id'] != actor['id'])
        customer = actor['nickname']
        key = text(body.get('requestId', ''), '请求编号', 80)
        def change(doc):
            old = next((o for o in doc['orders'] if o['requestId'] == key and o.get('createdBy') == actor['id']), None)
            if old: return old
            menu = {m['id']: m for m in doc['menu'] if m.get('active', True)}
            totals = {}
            for row in raw:
                if not isinstance(row, dict): raise ValidationError('菜单项格式不正确')
                ident = row.get('id')
                if not isinstance(ident, str) or ident not in menu: raise ValidationError('菜单已更新，请刷新后重新选择')
                qty = integer(row.get('quantity'), '份数')
                totals[ident] = totals.get(ident, 0) + qty
                integer(totals[ident], '同一菜单的份数')
            entries = []
            for ident, qty in totals.items():
                item = menu[ident]
                entries.append({k: item.get(k) for k in ('id', 'name', 'image', 'category', 'description')})
                entries[-1]['quantity'] = qty
                item['sales'] = item.get('sales', 0) + qty
            order = {'id': 'K' + secrets.token_hex(5).upper(), 'items': entries, 'note': note, 'customer': customer, 'status': 'pending', 'createdAt': now(), 'updatedAt': now(), 'requestId': key, 'createdBy': actor['id'], 'recipientId': recipient['id'], 'recipient': recipient['nickname'], 'acceptedBy': None}
            doc['orders'].insert(0, order)
            return order
        return self.mutate(change)
    def set_status(self, ident, status, actor):
        if status not in STATUSES: raise ValidationError('未知订单状态')
        def change(doc):
            order = next((o for o in doc['orders'] if o['id'] == ident), None)
            if order is None: raise ValidationError('订单不存在')
            if not order.get('createdBy') or not order.get('recipientId'): raise AuthError('历史订单未绑定账号，只可查看', 403)
            recipient = order['recipientId'] == actor['id']
            creator = order['createdBy'] == actor['id']
            if status in ('accepted', 'completed') and not recipient: raise AuthError('只有收到这份心意的人可以接单或完成', 403)
            if status == 'cancelled' and not (recipient or (creator and order['status'] == 'pending')): raise AuthError('不能取消这份订单', 403)
            if status != order['status'] and status not in TRANSITIONS[order['status']]: raise ValidationError('不能进行此状态变更')
            if status == 'accepted': order['acceptedBy'] = actor['id']
            if status == 'completed': order['completedBy'] = actor['id']
            order.update(status=status, updatedAt=now())
            return order
        return self.mutate(change)
    def save_menu(self, body, ident=None):
        name = text(body.get('name'), '菜谱名称', 50)
        desc = text(body.get('description', ''), '说明', 150, False)
        cat = text(body.get('category'), '分类', 20)
        image = body.get('image', '/assets/item-001.jpg')
        if not isinstance(image, str) or not re.fullmatch(r'/assets/(?:item-\d{3}\.jpg|upload-[a-f0-9]{64}\.jpg)', image): raise ValidationError('请选择有效的本地配图')
        if not (STATIC / image.lstrip('/')).is_file(): raise ValidationError('配图不存在')
        def change(doc):
            if cat not in {c['id'] for c in doc['categories']}: raise ValidationError('分类不存在')
            if ident:
                item = next((m for m in doc['menu'] if m['id'] == ident and m.get('active', True)), None)
                if item is None: raise ValidationError('菜谱不存在')
            else:
                item = {'id': 'custom-' + secrets.token_hex(6), 'source': None, 'rating': None, 'sales': 0, 'active': True, 'custom': True}
                doc['menu'].append(item)
            item.update(name=name, description=desc, category=cat, image=image)
            return item
        return self.mutate(change)
    def delete_menu(self, ident):
        def change(doc):
            item = next((m for m in doc['menu'] if m['id'] == ident and m.get('active', True)), None)
            if item is None: raise ValidationError('菜谱不存在')
            item['active'] = False
            return {'deleted': ident}
        return self.mutate(change)
    def settings(self, body):
        name = text(body.get('name'), '厨房名称', 20)
        announcement = text(body.get('announcement', ''), '公告', 100, False)
        members = body.get('members')
        if not isinstance(members, list) or len(members) != 2: raise ValidationError('请设置两位成员')
        members = [text(x, '成员昵称', 20) for x in members]
        def change(doc):
            doc['settings'].update(name=name, announcement=announcement or '暂无', members=members)
            return doc['settings']
        return self.mutate(change)

class Handler(BaseHTTPRequestHandler):
    server_version='CoupleKitchen/2.0'
    def log_message(self,fmt,*args):
        message=re.sub(r'([?&]key=)[^ &]+',r'\1[REDACTED]',fmt % args)
        print(f'HTTP {self.client_address[0]} {message}',flush=True)
    @property
    def store(self):return self.server.store
    @property
    def accounts(self):return self.server.accounts
    def token(self):
        cookie=SimpleCookie()
        try:cookie.load(self.headers.get('Cookie',''))
        except Exception:return ''
        value=cookie.get('kitchen_session');return value.value if value else ''
    def session(self):return self.accounts.session(self.token())
    def cookie(self,token='',delete=False):
        value=f'kitchen_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={0 if delete else SESSION_SECONDS}'
        if self.server.secure_cookie:value+='; Secure'
        return value
    def send(self,status,data,mime='application/json; charset=utf-8',headers=None):
        raw=json.dumps(data,ensure_ascii=False).encode('utf-8') if isinstance(data,(dict,list)) else data
        self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store' if 'json' in mime or 'html' in mime else 'public, max-age=3600')
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'; object-src 'none'")
        for key,value in (headers or {}).items():self.send_header(key,value)
        self.end_headers();self.wfile.write(raw)
    def error(self,status,msg):self.send(status,{'error':msg})
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/api/health':return self.send(200,{'ok':True,'service':'couple-kitchen','version':2})
        if path in ('/','/index.html'):return self.send(200,(STATIC/'index.html').read_bytes(),'text/html; charset=utf-8')
        if path=='/api/auth/status':
            session=self.session()
            return self.send(200,{'needsSetup':not bool(self.accounts.users()),'authenticated':bool(session),'user':session['user'] if session else None})
        if path.startswith('/api/'):
            session=self.session()
            if not session:return self.error(401,'请登录你的厨房账号')
            if path in ('/api/bootstrap','/api/export'):
                doc=self.store.public();members=self.accounts.users();doc['members']=members;doc['viewer']=session['user']
                doc['settings']['members']=[u['nickname'] for u in members]
                if path=='/api/bootstrap':doc['csrf']=session['csrf']
                return self.send(200,doc)
            return self.error(404,'接口不存在')
        if path in ('/styles.css','/responsive.css','/app.js','/auth.js') or re.fullmatch(r'/assets/[A-Za-z0-9_.-]+\.(jpg|png)',path):
            # Resolve the persistent assets root, while rejecting links escaping it.
            asset_request=path.startswith('/assets/')
            allowed_root=(STATIC/'assets' if asset_request else STATIC).resolve()
            relative_name=path[len('/assets/'):] if asset_request else path.lstrip('/')
            file=(allowed_root/relative_name).resolve()
            if allowed_root not in file.parents or not file.is_file():return self.error(404,'文件不存在')
            mime='text/javascript; charset=utf-8' if path.endswith('.js') else (mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
            return self.send(200,file.read_bytes(),mime)
        return self.error(404,'页面不存在')
    def do_POST(self):self.write_request()
    def do_PATCH(self):self.write_request()
    def do_DELETE(self):self.write_request()
    def write_request(self):
        path=urlsplit(self.path).path;method=self.command
        public_auth=method=='POST' and path in ('/api/auth/setup','/api/auth/login')
        session=None if public_auth else self.session()
        if not public_auth:
            if not session:return self.error(401,'请先登录')
            if not secrets.compare_digest(self.headers.get('X-Kitchen-Token',''),session['csrf']):return self.error(403,'请求校验失败，请刷新页面')
        expected=self.server.public_origin or 'http://'+self.headers.get('Host','')
        if self.headers.get('Origin') and self.headers['Origin']!=expected:return self.error(403,'不接受跨站请求')
        if self.headers.get('Sec-Fetch-Site')=='cross-site':return self.error(403,'不接受跨站请求')
        try:
            if self.headers.get_content_type()!='application/json':return self.error(415,'请使用JSON请求')
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=MAX_BODY:return self.error(413,'请求过大或为空')
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict):raise ValidationError('请求格式不正确')
            if public_auth and path=='/api/auth/setup':return self.send(201,{'users':self.accounts.setup(body)})
            if public_auth and path=='/api/auth/login':
                result=self.accounts.login(body,self.client_address[0])
                return self.send(200,{'user':result['user'],'csrf':result['csrf']},headers={'Set-Cookie':self.cookie(result['token'])})
            if method=='POST' and path=='/api/auth/logout':
                self.accounts.logout(self.token());return self.send(200,{'ok':True},headers={'Set-Cookie':self.cookie(delete=True)})
            if method=='POST' and path=='/api/auth/password':
                self.accounts.change_password(session['user']['id'],body);return self.send(200,{'ok':True},headers={'Set-Cookie':self.cookie(delete=True)})
            if method=='POST' and path=='/api/orders':return self.send(201,self.store.create_order(body,session['user']))
            match=re.fullmatch(r'/api/orders/(K[A-F0-9]{10})',path)
            if method=='PATCH' and match:return self.send(200,self.store.set_status(match[1],body.get('status'),session['user']))
            if method=='POST' and path=='/api/menu':return self.send(201,self.store.save_menu(body))
            match=re.fullmatch(r'/api/menu/([A-Za-z0-9-]+)',path)
            if match and method=='PATCH':return self.send(200,self.store.save_menu(body,match[1]))
            if match and method=='DELETE':return self.send(200,self.store.delete_menu(match[1]))
            if method=='PATCH' and path=='/api/settings':
                body['members']=[u['nickname'] for u in self.accounts.users()]
                return self.send(200,self.store.settings(body))
            if method=='POST' and path=='/api/upload':
                data=body.get('data','')
                if not isinstance(data,str) or not data.startswith('data:image/jpeg;base64,'):raise ValidationError('仅支持JPEG图片')
                try:raw=base64.b64decode(data.split(',',1)[1],validate=True)
                except Exception:raise ValidationError('图片数据无效')
                if len(raw)>512_000 or not raw.startswith(b'\xff\xd8\xff') or not raw.endswith(b'\xff\xd9'):raise ValidationError('图片无效或超过500KB')
                name='upload-'+hashlib.sha256(raw).hexdigest()+'.jpg';(STATIC/'assets'/name).write_bytes(raw)
                return self.send(201,{'image':'/assets/'+name})
            return self.error(404,'接口不存在')
        except AuthError as exc:return self.error(exc.status,str(exc))
        except (ValidationError,json.JSONDecodeError,UnicodeDecodeError,ValueError) as exc:return self.error(400,str(exc))
        except (OSError,sqlite3.Error):return self.error(500,'保存失败，请检查服务器数据目录权限')
class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,addr,store):
        self.store=store;self.accounts=Accounts(store.path)
        self.secure_cookie=os.environ.get('KITCHEN_SECURE_COOKIE','0')=='1'
        self.public_origin=os.environ.get('KITCHEN_PUBLIC_ORIGIN','').rstrip('/')
        super().__init__(addr,Handler)

def check():
    seed=load_seed()
    for required in ('index.html','app.js','styles.css','auth.js','responsive.css'):
        if not (STATIC/required).is_file():raise FileNotFoundError(required)
    for item in seed['menu']:
        if not (STATIC/item['image'].lstrip('/')).is_file():raise FileNotFoundError(item['image'])
    with tempfile.TemporaryDirectory(prefix='kitchen-accounts-check-') as tmp:
        store=Store(Path(tmp)/'check.sqlite3');accounts=Accounts(store.path)
        users=accounts.setup({'setupToken':accounts.token_file.read_text(encoding='utf-8'),'accounts':[{'username':'check_one','nickname':'甲','password':'self-check-one-strong'},{'username':'check_two','nickname':'乙','password':'self-check-two-strong'}]})
        order=store.create_order({'items':[{'id':seed['menu'][0]['id'],'quantity':2}],'requestId':'self-check'},users[0])
        assert order['createdBy']==users[0]['id'] and order['recipientId']==users[1]['id']
        try:store.set_status(order['id'],'accepted',users[0])
        except AuthError as exc:assert exc.status==403
        else:raise AssertionError('Creator accepted own order')
        store.set_status(order['id'],'accepted',users[1]);store.set_status(order['id'],'completed',users[1])
        assert Store(store.path).read()['orders'][0]['status']=='completed'
        session=accounts.login({'username':'check_one','password':'self-check-one-strong'},'check')
        assert accounts.session(session['token'])['user']['id']==users[0]['id']
        accounts.logout(session['token']);assert accounts.session(session['token']) is None
    print('APP_CHECK=OK');print('MODE=responsive_web_two_accounts')
    print(f'CATEGORIES={len(seed["categories"])}');print(f'OBSERVED_MENU_ITEMS={len(seed["menu"])}')
    print('ACCOUNTS=2');print('FEATURES=password_login,individual_sessions,partner_orders,responsive_pc_mobile,sqlite_persistence')
    print('CHECK=assets,password_hash,login,logout,creator_recipient,deny_self_accept,partner_complete,reopen')
    return 0

def cli(argv=None):
    parser = argparse.ArgumentParser(description='情侣趣味厨房：本地可交互项目')
    parser.add_argument('--check', action='store_true', help='运行无副作用自检，不启动服务器')
    parser.add_argument('--host', default='127.0.0.1', help='默认仅本机；可信局域网可设0.0.0.0')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--data', type=Path, default=ROOT / 'data' / 'kitchen.sqlite3')
    args = parser.parse_args(argv)
    if args.check: return check()
    if not 0 <= args.port <= 65535: parser.error('端口应在0–65535之间')
    store = Store(args.data)
    try: server = Server((args.host, args.port), store)
    except OSError as exc:
        parser.exit(1, f'无法启动服务：{exc}。可用 --port 8766 更换端口。\n')
    print(f'APP=http://127.0.0.1:{server.server_port}', flush=True)
    print(f'DATA={args.data.resolve()}', flush=True)
    if not server.accounts.users():
        print(f'SETUP_TOKEN_FILE={server.accounts.token_file.resolve()}', flush=True)
        print('首次打开网页，用初始化口令创建你们的两个账号；没有默认账号或默认密码。', flush=True)
    if args.host != '127.0.0.1':
        print('服务器部署请使用HTTPS反向代理、KITCHEN_PUBLIC_ORIGIN和Secure Cookie。', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
    return 0

if __name__ == '__main__':
    raise SystemExit(cli())