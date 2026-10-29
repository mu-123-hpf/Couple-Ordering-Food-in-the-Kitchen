from pathlib import Path
import sys,tempfile,threading,json,urllib.request,urllib.error,http.cookiejar,sqlite3
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from kitchen_app.server import Store,Server
checks=[]
def check(label,condition):
    assert condition,label
    checks.append(label);print('PASS='+label)
with tempfile.TemporaryDirectory(prefix='kitchen-two-users-') as tmp:
    store=Store(Path(tmp)/'test.sqlite3');server=Server(('127.0.0.1',0),store)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
    def client():return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    a,b,anon=client(),client(),client()
    def req(client,path,method='GET',body=None,csrf=None,origin=None,cookie=None):
        headers={'Content-Type':'application/json'}
        if csrf is not None:headers['X-Kitchen-Token']=csrf
        if origin is not None:headers['Origin']=origin
        if cookie is not None:headers['Cookie']=cookie
        data=None if body is None else json.dumps(body,ensure_ascii=False).encode('utf-8')
        try:response=client.open(urllib.request.Request(base+path,data=data,headers=headers,method=method),timeout=15)
        except urllib.error.HTTPError as exc:response=exc
        raw=response.read();status=response.status;headers=dict(response.headers)
        try:payload=json.loads(raw)
        except (ValueError,UnicodeDecodeError):payload=raw
        return status,payload,headers
    accounts=[{'username':'alice_test','nickname':'甲','password':'alice-integration-strong'},{'username':'bob_test','nickname':'乙','password':'bob-integration-strong'}]
    try:
        check('initial_setup_needed',req(anon,'/api/auth/status')[1]['needsSetup'])
        check('anonymous_data_denied_even_loopback',req(anon,'/api/bootstrap')[0]==401)
        check('old_shared_secret_cookie_denied',req(anon,'/api/bootstrap',cookie='kitchen_session='+store.read()['secret'])[0]==401)
        check('anonymous_order_denied',req(anon,'/api/orders','POST',{})[0]==401)
        token=server.accounts.token_file.read_text(encoding='utf-8')
        setup={'setupToken':token,'accounts':accounts}
        check('wrong_setup_token_denied',req(anon,'/api/auth/setup','POST',{**setup,'setupToken':'wrong'})[0]==403)
        check('three_accounts_rejected',req(anon,'/api/auth/setup','POST',{**setup,'accounts':accounts+[accounts[0]]})[0]==400)
        check('duplicate_username_rejected',req(anon,'/api/auth/setup','POST',{**setup,'accounts':[accounts[0],accounts[0]]})[0]==400)
        status,created,_=req(anon,'/api/auth/setup','POST',setup)
        check('exactly_two_accounts_created',status==201 and len(created['users'])==2)
        check('setup_token_file_removed',not server.accounts.token_file.exists())
        check('cannot_register_after_setup',req(anon,'/api/auth/setup','POST',setup)[0]==409)
        with server.accounts.connect() as db:
            rows=db.execute('SELECT * FROM users').fetchall()
            check('passwords_salted_not_plaintext',all(len(row['salt'])==32 and len(row['password_hash'])==64 and row['password_hash']!=accounts[n]['password'] for n,row in enumerate(rows)))
        check('foreign_origin_login_denied',req(a,'/api/auth/login','POST',accounts[0],origin='https://untrusted.example')[0]==403)
        check('wrong_password_denied',req(anon,'/api/auth/login','POST',{**accounts[0],'password':'wrong-password'})[0]==401)
        status,login_a,headers_a=req(a,'/api/auth/login','POST',accounts[0]);status_b,login_b,headers_b=req(b,'/api/auth/login','POST',accounts[1])
        check('two_independent_logins',status==status_b==200 and login_a['user']['id']!=login_b['user']['id'])
        check('session_cookie_httponly_samesite','HttpOnly' in headers_a['Set-Cookie'] and 'SameSite=Strict' in headers_a['Set-Cookie'])
        check('session_tokens_unique',headers_a['Set-Cookie']!=headers_b['Set-Cookie'])
        csrf_a,csrf_b=login_a['csrf'],login_b['csrf'];user_a,user_b=login_a['user'],login_b['user']
        _,doc,_=req(a,'/api/bootstrap');_,doc_b,_=req(b,'/api/bootstrap')
        check('bootstrap_own_identity',doc['viewer']['id']==user_a['id'] and doc_b['viewer']['id']==user_b['id'])
        check('bootstrap_does_not_expose_password_hashes','password_hash' not in json.dumps(doc) and 'salt' not in json.dumps(doc))
        check('csrf_distinct_per_session',csrf_a!=csrf_b)
        payload={'items':[{'id':doc['menu'][0]['id'],'quantity':1}],'requestId':'same-client-key','customer':'伪造乙','createdBy':user_b['id'],'recipientId':user_a['id'],'note':'双账号测试'}
        check('missing_csrf_denied',req(a,'/api/orders','POST',payload)[0]==403)
        check('other_user_csrf_denied',req(a,'/api/orders','POST',payload,csrf_b)[0]==403)
        status,order_a,_=req(a,'/api/orders','POST',payload,csrf_a)
        check('creator_recipient_assigned_server_side',status==201 and order_a['createdBy']==user_a['id'] and order_a['recipientId']==user_b['id'] and order_a['customer']=='甲')
        _,duplicate,_=req(a,'/api/orders','POST',payload,csrf_a)
        check('same_user_order_idempotent',duplicate['id']==order_a['id'] and len(store.read()['orders'])==1)
        _,order_b,_=req(b,'/api/orders','POST',payload,csrf_b)
        check('idempotency_keys_scoped_to_user',order_b['id']!=order_a['id'] and order_b['createdBy']==user_b['id'] and order_b['recipientId']==user_a['id'])
        path='/api/orders/'+order_a['id']
        check('creator_cannot_accept_own_order',req(a,path,'PATCH',{'status':'accepted'},csrf_a)[0]==403)
        check('creator_cannot_complete_own_order',req(a,path,'PATCH',{'status':'completed'},csrf_a)[0]==403)
        check('recipient_cannot_skip_accept',req(b,path,'PATCH',{'status':'completed'},csrf_b)[0]==400)
        check('recipient_can_accept',req(b,path,'PATCH',{'status':'accepted'},csrf_b)[1]['acceptedBy']==user_b['id'])
        check('recipient_can_complete',req(b,path,'PATCH',{'status':'completed'},csrf_b)[1]['completedBy']==user_b['id'])
        reverse='/api/orders/'+order_b['id']
        req(a,reverse,'PATCH',{'status':'accepted'},csrf_a)
        check('reciprocal_partner_completion',req(a,reverse,'PATCH',{'status':'completed'},csrf_a)[1]['completedBy']==user_a['id'])
        check('recipient_completion_visible_to_creator',req(a,'/api/bootstrap')[1]['orders'][1]['status']=='completed')
        bad={**payload,'requestId':'invalid','items':[{'id':doc['menu'][0]['id'],'quantity':-1}]}
        check('invalid_quantity_rejected',req(a,'/api/orders','POST',bad,csrf_a)[0]==400)
        recipe={'name':'账号测试菜谱','description':'仅测试','category':doc['menu'][0]['category'],'image':doc['menu'][0]['image']}
        status,new,_=req(a,'/api/menu','POST',recipe,csrf_a)
        check('shared_menu_create',status==201)
        check('partner_can_edit_shared_menu',req(b,'/api/menu/'+new['id'],'PATCH',{**recipe,'name':'乙修改'},csrf_b)[1]['name']=='乙修改')
        check('shared_menu_delete',req(a,'/api/menu/'+new['id'],'DELETE',{},csrf_a)[0]==200)
        export=req(a,'/api/export')[1]
        check('export_no_csrf_passwords_sessions','csrf' not in export and 'secret' not in export and 'password_hash' not in json.dumps(export))
        legacy={'id':'K0000000000','status':'pending','requestId':'legacy','items':[],'createdAt':'2026-10-28','note':'历史数据'}
        store.mutate(lambda data:data['orders'].append(legacy))
        check('legacy_order_preserved_read_only',req(a,'/api/orders/K0000000000','PATCH',{'status':'accepted'},csrf_a)[0]==403)
        old_cookie=headers_a['Set-Cookie'].split(';')[0]
        check('logout_success',req(a,'/api/auth/logout','POST',{},csrf_a)[0]==200)
        check('revoked_session_denied',req(anon,'/api/bootstrap',cookie=old_cookie)[0]==401)
        check('other_account_remains_logged_in',req(b,'/api/bootstrap')[0]==200)
        _,new_login,_=req(a,'/api/auth/login','POST',accounts[0]);csrf_a=new_login['csrf']
        check('password_change_reauth_required',req(a,'/api/auth/password','POST',{'currentPassword':accounts[0]['password'],'newPassword':'alice-new-password-strong'},csrf_a)[0]==200 and req(a,'/api/bootstrap')[0]==401)
        check('old_password_no_longer_works',req(anon,'/api/auth/login','POST',accounts[0])[0]==401)
        _,new_login,_=req(a,'/api/auth/login','POST',{**accounts[0],'password':'alice-new-password-strong'})
        check('new_password_works',new_login.get('user',{}).get('id')==user_a['id'])
        with server.accounts.connect() as db:db.execute('UPDATE sessions SET expires=0 WHERE user_id=?',(user_a['id'],))
        check('expired_session_denied',req(a,'/api/bootstrap')[0]==401)
        # Distinct account name isolates lockout from the browser demo fixture.
        for n in range(5):req(anon,'/api/auth/login','POST',{'username':'nobody_rate','password':'wrong-password'})
        check('login_rate_limit_429',req(anon,'/api/auth/login','POST',{'username':'nobody_rate','password':'wrong-password'})[0]==429)
        server.secure_cookie=True
        _,_,secure_headers=req(anon,'/api/auth/login','POST',accounts[1])
        check('production_secure_cookie_flag','Secure' in secure_headers['Set-Cookie'])
        check('two_accounts_and_orders_survive_reopen',len(Store(store.path).read()['orders'])==3 and len(server.accounts.users())==2)
    finally:server.shutdown();server.server_close();thread.join(timeout=5)
    restarted=Server(('127.0.0.1',0),Store(store.path));thread=threading.Thread(target=restarted.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{restarted.server_port}'
    try:check('session_and_orders_survive_server_restart',req(b,'/api/bootstrap')[0]==200 and len(req(b,'/api/bootstrap')[1]['orders'])==3)
    finally:restarted.shutdown();restarted.server_close();thread.join(timeout=5)
check('all_database_connections_closed',not Path(tmp).exists())
print('TWO_ACCOUNT_INTEGRATION=OK');print('CHECKS='+str(len(checks)))
(Path(__file__).resolve().parents[1]/'kitchen_app'/'records'/'accounts_test_results.json').write_text(json.dumps({'checks':checks,'exit':0},indent=2),encoding='utf-8')
