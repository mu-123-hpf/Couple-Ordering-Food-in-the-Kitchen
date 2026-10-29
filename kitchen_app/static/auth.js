/* Login and first-run account setup; no default personal credentials. */
window.KitchenAuth={
  showLogin(error=''){
    document.querySelector('#app').hidden=true;
    const stage=document.querySelector('#authStage');stage.hidden=false;
    stage.innerHTML=`<div class="auth-card"><div class="brand-mark">♡</div><p class="eyebrow">JUST THE TWO OF US</p><h1>登录你们的小厨房</h1><p class="auth-subtitle">用各自的账号登录。一人下单，另一人认真完成。</p><form id="loginForm"><label>你的账号<input name="username" autocomplete="username" required minlength="3" maxlength="24" placeholder="输入你的账号"></label><label>密码<input name="password" type="password" autocomplete="current-password" required maxlength="128" placeholder="输入密码"></label><p class="auth-error" id="authError" role="alert"></p><button class="auth-submit" type="submit">进入厨房 →</button></form><p class="auth-footnote">手机与电脑共用同一厨房，账号身份由服务器确认。</p></div>`;
    document.querySelector('#authError').textContent=error;
    document.querySelector('#loginForm').addEventListener('submit',async event=>{
      event.preventDefault();const form=new FormData(event.currentTarget);const button=event.currentTarget.querySelector('button');button.disabled=true;
      try{await KitchenAuth.request('/api/auth/login',{username:form.get('username'),password:form.get('password')});await KitchenAuth.enter();}
      catch(error){document.querySelector('#authError').textContent=error.message;button.disabled=false;}
    });
  },
  showSetup(){
    document.querySelector('#app').hidden=true;const stage=document.querySelector('#authStage');stage.hidden=false;
    stage.innerHTML=`<div class="auth-card setup-card"><div class="brand-mark">♡</div><p class="eyebrow">CREATE YOUR SHARED KITCHEN</p><h1>先创建你们的两个账号</h1><p class="auth-subtitle">每个人拥有自己的密码。两个账号共享菜单，但不能替对方完成自己下的订单。</p><form id="setupForm"><label>初始化口令<input name="setupToken" type="password" required autocomplete="off" placeholder="从服务器初始化口令文件复制"></label><p class="setup-hint">本机口令文件：kitchen_app/data/kitchen.setup-token.txt。部署服务器后由管理员读取口令；初始化成功后口令失效。</p><div class="setup-accounts">${[0,1].map((n)=>`<fieldset><legend>第 ${n+1} 位成员</legend><label>账号<input name="username${n}" required minlength="3" maxlength="24" pattern="[a-z0-9_]{3,24}" placeholder="小写字母、数字或下划线" autocomplete="off"></label><label>昵称<input name="nickname${n}" required maxlength="20" placeholder="希望对方怎么称呼你"></label><label>密码<input name="password${n}" type="password" required minlength="10" maxlength="128" autocomplete="new-password" placeholder="至少10个字符"></label><label>确认密码<input name="confirm${n}" type="password" required minlength="10" maxlength="128" autocomplete="new-password"></label></fieldset>`).join('')}</div><p class="auth-error" id="authError" role="alert"></p><button class="auth-submit" type="submit">创建双人厨房</button></form><p class="auth-footnote">不会创建默认密码，也不会开放第三个账号注册。</p></div>`;
    document.querySelector('#setupForm').addEventListener('submit',async event=>{
      event.preventDefault();const form=new FormData(event.currentTarget);const button=event.currentTarget.querySelector('button');button.disabled=true;
      try{const accounts=[0,1].map(n=>{if(form.get(`password${n}`)!==form.get(`confirm${n}`))throw new Error(`第${n+1}位成员的两次密码不一致`);return {username:form.get(`username${n}`),nickname:form.get(`nickname${n}`),password:form.get(`password${n}`)};});await KitchenAuth.request('/api/auth/setup',{setupToken:form.get('setupToken'),accounts});KitchenAuth.showLogin('账号已创建，请使用你自己的账号登录。');}
      catch(error){document.querySelector('#authError').textContent=error.message;button.disabled=false;}
    });
  },
  async request(path,body){const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const payload=await response.json();if(!response.ok)throw new Error(payload.error||'请求失败');return payload;},
  async enter(){
    state.doc=null;state.cart=[];state.csrf='';state.edit=false;
    await refresh();if(!state.doc)return;
    document.querySelector('#authStage').hidden=true;document.querySelector('#app').hidden=false;
    loadCart();renderAll();setView('kitchen');
  },
  async logout(){
    try{await api('/api/auth/logout',{method:'POST',body:'{}'});}catch{}
    state.doc=null;state.csrf='';state.cart=[];closeSheet();KitchenAuth.showLogin();
  },
  password(){
    openSheet('修改我的密码',`<form id="passwordForm"><label class="form-field">当前密码<input name="currentPassword" type="password" required autocomplete="current-password" maxlength="128"></label><label class="form-field">新密码<input name="newPassword" type="password" required minlength="10" maxlength="128" autocomplete="new-password"></label><label class="form-field">确认新密码<input name="confirm" type="password" required minlength="10" maxlength="128" autocomplete="new-password"></label><p id="passwordError" class="form-error"></p><button class="primary-button" type="submit">保存并重新登录</button></form>`,body=>document.querySelector('#passwordForm').addEventListener('submit',async event=>{event.preventDefault();const form=new FormData(event.currentTarget);try{if(form.get('newPassword')!==form.get('confirm'))throw new Error('两次新密码不一致');await api('/api/auth/password',{method:'POST',body:JSON.stringify({currentPassword:form.get('currentPassword'),newPassword:form.get('newPassword')})});closeSheet();state.doc=null;KitchenAuth.showLogin('密码已更新，原有登录已失效，请重新登录。');}catch(error){document.querySelector('#passwordError').textContent=error.message;}}));
  }
};
window.addEventListener('DOMContentLoaded',async()=>{
  document.querySelector('#logoutButton').addEventListener('click',()=>KitchenAuth.logout());
  document.querySelector('#passwordButton').addEventListener('click',()=>KitchenAuth.password());
  try{const response=await fetch('/api/auth/status');const status=await response.json();if(status.needsSetup)KitchenAuth.showSetup();else if(status.authenticated)await KitchenAuth.enter();else KitchenAuth.showLogin();}
  catch{KitchenAuth.showLogin('无法连接厨房服务，请检查服务器是否启动。');}
});
