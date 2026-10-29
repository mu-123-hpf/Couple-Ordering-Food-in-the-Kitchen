"""Exactly two local accounts; salted passwords and revocable per-browser sessions."""
from contextlib import contextmanager
from pathlib import Path
import hashlib, secrets, sqlite3, time, re
ITERATIONS=600_000
SESSION_SECONDS=7*24*3600
class AuthError(ValueError):
    def __init__(self,message,status=400):super().__init__(message);self.status=status
class Accounts:
    def __init__(self,path):
        self.path=Path(path);self.token_file=self.path.parent/(self.path.stem+'.setup-token.txt')
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, nickname TEXT NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), csrf TEXT NOT NULL, expires REAL NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS auth_attempts (key TEXT PRIMARY KEY, count INTEGER NOT NULL, blocked_until REAL NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS auth_config (id INTEGER PRIMARY KEY CHECK(id=1), setup_hash TEXT NOT NULL)')
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM users').fetchone() and not db.execute('SELECT 1 FROM auth_config').fetchone():
                token=secrets.token_urlsafe(24)
                self.token_file.write_text(token,encoding='utf-8');self.token_file.chmod(0o600)
                db.execute('INSERT INTO auth_config VALUES(1,?)',(self.digest(token),))
    @contextmanager
    def connect(self):
        db=sqlite3.connect(str(self.path),timeout=15);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()
    @staticmethod
    def digest(value):return hashlib.sha256(value.encode('utf-8')).hexdigest()
    @staticmethod
    def password(value):
        if not isinstance(value,str) or not 10<=len(value)<=128:raise AuthError('密码需要10–128个字符')
        return value
    @staticmethod
    def username(value):
        if not isinstance(value,str):raise AuthError('请填写账号')
        value=value.strip().lower()
        if not re.fullmatch(r'[a-z0-9_]{3,24}',value):raise AuthError('账号需要3–24位小写字母、数字或下划线')
        return value
    @staticmethod
    def hash_password(password,salt):return hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),bytes.fromhex(salt),ITERATIONS).hex()
    @staticmethod
    def public(row):return {key:row[key] for key in ('id','username','nickname')}
    def users(self):
        with self.connect() as db:return [self.public(x) for x in db.execute('SELECT * FROM users ORDER BY rowid')]
    def setup(self,body):
        entries=body.get('accounts');token=body.get('setupToken','')
        if not isinstance(entries,list) or len(entries)!=2:raise AuthError('这个厨房需要且只需要两个账号')
        if not isinstance(token,str) or len(token)>128:raise AuthError('初始化口令无效',403)
        prepared=[]
        for entry in entries:
            if not isinstance(entry,dict):raise AuthError('账号格式不正确')
            username=self.username(entry.get('username'));password=self.password(entry.get('password'));name=entry.get('nickname')
            if not isinstance(name,str) or not 1<=len(name.strip())<=20:raise AuthError('昵称需要1–20个字')
            prepared.append((username,password,name.strip()))
        if prepared[0][0]==prepared[1][0]:raise AuthError('两个账号不能相同')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM users').fetchone():raise AuthError('厨房账号已经初始化，不能再注册第三个账号',409)
            config=db.execute('SELECT setup_hash FROM auth_config WHERE id=1').fetchone()
            if not config or not secrets.compare_digest(config[0],self.digest(token)):raise AuthError('初始化口令不正确，请查看服务器的初始化口令文件',403)
            for username,password,name in prepared:
                salt=secrets.token_hex(16)
                db.execute('INSERT INTO users VALUES(?,?,?,?,?)',('U'+secrets.token_hex(8),username,name,salt,self.hash_password(password,salt)))
            db.execute('DELETE FROM auth_config')
        try:self.token_file.unlink(missing_ok=True)
        except OSError:pass
        return self.users()
    def login(self,body,peer):
        username=self.username(body.get('username'));password=body.get('password','')
        if not isinstance(password,str) or not 1<=len(password)<=128:raise AuthError('账号或密码不正确',401)
        key=self.digest(username+'|'+peer);stamp=time.time()
        # Lock covers checking, recording failed attempts and issuing a session.
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            attempt=db.execute('SELECT * FROM auth_attempts WHERE key=?',(key,)).fetchone()
            if attempt and attempt['blocked_until']>stamp:raise AuthError('尝试次数过多，请15分钟后再试',429)
            user=db.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
            salt=user['salt'] if user else '00'*16
            actual=self.hash_password(password,salt)
            valid=user is not None and secrets.compare_digest(actual,user['password_hash'])
            if not valid:
                count=(attempt['count'] if attempt and attempt['blocked_until']==0 else 0)+1
                db.execute('INSERT OR REPLACE INTO auth_attempts VALUES(?,?,?)',(key,count,stamp+900 if count>=5 else 0))
            else:
                db.execute('DELETE FROM auth_attempts WHERE key=?',(key,));db.execute('DELETE FROM sessions WHERE expires<=?',(stamp,))
                token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
                db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(self.digest(token),user['id'],csrf,stamp+SESSION_SECONDS))
                result={'token':token,'csrf':csrf,'user':self.public(user)}
        if not valid:raise AuthError('账号或密码不正确',401)
        return result
    def session(self,token):
        if not isinstance(token,str) or not token or len(token)>128:return None
        with self.connect() as db:
            row=db.execute('SELECT users.*,sessions.csrf,sessions.expires FROM sessions JOIN users ON users.id=sessions.user_id WHERE token_hash=? AND expires>?',(self.digest(token),time.time())).fetchone()
            return {'user':self.public(row),'csrf':row['csrf']} if row else None
    def logout(self,token):
        with self.connect() as db:db.execute('DELETE FROM sessions WHERE token_hash=?',(self.digest(token),))
    def change_password(self,user_id,body):
        old=body.get('currentPassword','');new=self.password(body.get('newPassword'))
        if not isinstance(old,str) or len(old)>128:raise AuthError('当前密码不正确',401)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');user=db.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone()
            if not user or not secrets.compare_digest(self.hash_password(old,user['salt']),user['password_hash']):raise AuthError('当前密码不正确',401)
            salt=secrets.token_hex(16);db.execute('UPDATE users SET salt=?,password_hash=? WHERE id=?',(salt,self.hash_password(new,salt),user_id))
            db.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
