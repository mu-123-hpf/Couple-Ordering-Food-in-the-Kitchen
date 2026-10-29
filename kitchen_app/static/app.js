'use strict';
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const state = {doc:null, csrf:'', activeCategory:'必看必看', edit:false, query:'', view:'kitchen', cart:[], filter:'all', role:''};
const categories = () => state.doc?.categories || [];
const menu = () => state.doc?.menu || [];
const h = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = (name, cls='icon') => `<svg class="${cls}" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
const itemById = id => menu().find(item => item.id === id);
const formatDate = value => { try { return new Intl.DateTimeFormat('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}).format(new Date(value)); } catch { return value || ''; } };
const statusText = status => ({pending:'待接单',accepted:'制作中',completed:'已完成',cancelled:'已取消'}[status] || status);
const toast = (message, ms=2500) => { const node=$('#toast'); node.textContent=message; node.hidden=false; clearTimeout(toast.timer); toast.timer=setTimeout(()=>node.hidden=true,ms); };
const api = async (path, options={}) => {
  const opts = {...options, headers:{'Content-Type':'application/json','X-Kitchen-Token':state.csrf,...(options.headers||{})}};
  const response = await fetch(path, opts);
  let payload = {};
  try { payload = await response.json(); } catch {}
  if (response.status===401) window.KitchenAuth?.showLogin('登录已失效，请重新登录。');
  if (!response.ok) throw new Error(payload.error || `请求失败（${response.status}）`);
  return payload;
};
async function refresh(){
  try {
    const doc=await api('/api/bootstrap',{headers:{}});
    state.doc=doc; state.csrf=doc.csrf; state.role=doc.viewer.nickname;
    $('#accountName').textContent=`${doc.viewer.nickname} · ${doc.viewer.username}`;
    state.activeCategory = categories().some(c=>c.id===state.activeCategory) ? state.activeCategory : categories()[0]?.id || '';
    $('#connectionBanner').hidden=true;
    renderAll();
  } catch(error) {
    $('#connectionBanner').hidden=false;
    if (!state.doc) $('#menuList').innerHTML=`<div class="initial-error">厨房还没打开。<br>${h(error.message)}<button id="retryLoad">重新打开</button></div>`;
  }
}
function renderAll(){ renderProfile(); renderCategories(); renderMenu(); renderCart(); renderOrders(); renderDiscover(); renderMe(); setView(state.view,false); }
function renderProfile(){
  const settings=state.doc.settings;
  $('#kitchenName').textContent=settings.name; $('#memberCount').textContent=`共${settings.members.length}人`; $('#announcement').textContent=settings.announcement || '暂无';
  $('#meKitchenName').textContent=settings.name; $('#meMembers').textContent=settings.members.join(' · ');
}
function renderCategories(){
  $('#categories').innerHTML=categories().map(category=>`<button class="category ${category.id===state.activeCategory?'selected':''}" data-category="${h(category.id)}">${h(category.name)}</button>`).join('');
}
function filteredItems(){
  let result=menu().filter(item=>item.category===state.activeCategory);
  if (state.query) { const q=state.query.toLowerCase(); result=result.filter(item=>`${item.name} ${item.description||''} ${item.category}`.toLowerCase().includes(q)); }
  return result;
}
function renderMenu(){
  const node=$('#menuList');
  if (!state.doc) return;
  const category=categories().find(c=>c.id===state.activeCategory);
  const items=filteredItems();
  const title=category?.name || state.activeCategory;
  const count=menu().filter(item=>item.category===state.activeCategory).length;
  let head=`<div class="menu-section"><h2>${h(title)}${count ? `(${h(count)})` : ''}</h2>`;
  if (state.query) head += `<p class="category-note">正在搜索“${h(state.query)}”，共找到 ${items.length} 项</p>`;
  if (!items.length) { node.innerHTML=head+`<div class="empty-state">${icon('heart')}<h3>这一栏还没有菜谱</h3><p>可以先加一道只属于你们的菜单。</p><button class="outline" data-action="add-recipe">添加菜谱</button></div></div>`; return; }
  node.innerHTML=head+items.map(renderItem).join('')+'</div>';
}
function renderItem(item){
  const quantity=state.cart.find(row=>row.id===item.id)?.quantity || 0;
  const stars=item.rating ? `<div class="item-stars">${'★'.repeat(item.rating)}${'☆'.repeat(5-item.rating)}<span>${item.rating.toFixed(1)}</span></div>` : '';
  const controls=state.edit ? `<button class="edit-item" data-action="edit-item" data-id="${h(item.id)}">编辑</button><button class="edit-item" data-action="delete-item" data-id="${h(item.id)}">删除</button>` : (quantity ? `<button class="minus-button" data-action="minus" data-id="${h(item.id)}">−</button><span class="quantity">${quantity}</span><button class="add-button" data-action="add" data-id="${h(item.id)}" aria-label="再加一份">${icon('plus')}</button>` : `<button class="add-button" data-action="add" data-id="${h(item.id)}" aria-label="添加${h(item.name)}">${icon('plus')}</button>`);
  return `<article class="menu-item" data-id="${h(item.id)}"><button class="item-img-button" data-action="detail" data-id="${h(item.id)}" aria-label="查看${h(item.name)}"><img class="item-img" src="${h(item.image)}" alt="${h(item.name)}" loading="lazy"></button><div class="item-body"><div class="item-name">${h(item.name)}</div>${item.description?`<div class="item-description">${h(item.description)}</div>`:''}<div class="item-sales">月销 ${h(item.sales || 0)}</div>${stars}</div><div class="item-controls">${controls}</div></article>`;
}
function renderCart(){
  $('#cartBadge').textContent=cartCount(); $('#cartBadge').hidden=!cartCount(); $('#checkout').disabled=!state.cart.length;
}
function cartCount(){ return state.cart.reduce((sum,row)=>sum+row.quantity,0); }
const cartStorageKey=()=>`couple-kitchen-cart-${state.doc?.viewer?.id||"anonymous"}`;
const requestStorageKey=()=>`couple-kitchen-request-${state.doc?.viewer?.id||"anonymous"}`;
function saveCart(){ localStorage.setItem(cartStorageKey(),JSON.stringify(state.cart)); renderCart(); }
function loadCart(){ try { const saved=JSON.parse(localStorage.getItem(cartStorageKey())||'[]'); if(Array.isArray(saved)) state.cart=saved.filter(row=>row && typeof row.id==='string' && Number.isInteger(row.quantity) && row.quantity>0); } catch { state.cart=[]; } }
function addToCart(id, delta=1){ const item=itemById(id); if(!item) return; const row=state.cart.find(x=>x.id===id); if(row) row.quantity+=delta; else state.cart.push({id,quantity:1}); state.cart=state.cart.filter(x=>x.quantity>0); saveCart(); renderMenu(); toast(delta>0?`已把“${item.name}”放进点单`:'已从点单移除一份'); }
function setView(view, scroll=true){
  state.view=view; ['kitchen','orders','discover','me'].forEach(name=>{ const node=$(`#${name==='kitchen'?'kitchenView':name+'View'}`); if(node) node.hidden=name!==view; });
  $$('.bottom-nav button').forEach(button=>{ const active=button.dataset.view===view; button.classList.toggle('active',active); if(active) button.setAttribute('aria-current','page'); else button.removeAttribute('aria-current'); });
  if(scroll && view==='kitchen') $('#menuList').scrollTop=0;
  if(view==='orders') renderOrders(); if(view==='discover') renderDiscover(); if(view==='me') renderMe();
}
function openSheet(title, body, onOpen){ $('#sheetTitle').textContent=title; $('#sheetBody').innerHTML=body; $('#modalOverlay').hidden=false; document.body.classList.add('modal-open'); if(onOpen) onOpen($('#sheetBody')); }
function closeSheet(){ $('#modalOverlay').hidden=true; $('#sheetBody').innerHTML=''; document.body.classList.remove('modal-open'); }
function showCart(){
  const rows=state.cart.map(row=>{const item=itemById(row.id);return item?`<div class="cart-row"><img src="${h(item.image)}" alt=""><strong>${h(item.name)}</strong><div class="stepper"><button class="minus-button" data-action="minus" data-id="${h(item.id)}">−</button><span>${row.quantity}</span><button class="add-button" data-action="add" data-id="${h(item.id)}">${icon('plus')}</button></div></div>`:''}).join('');
  openSheet('你的点单',state.cart.length?`${rows}<div class="cart-summary"><span>共 ${cartCount()} 份心意</span><strong>本单无需付款</strong></div><textarea id="cartNote" class="cart-note" maxlength="200" placeholder="给另一半留一句备注（可选）"></textarea><button class="primary-button" data-action="submit-order">下单给另一半</button><p class="cart-explainer">真实订单会写入本地厨房，刷新后仍然保留。</p>`:`<div class="empty-state">${icon('cart')}<h3>点单还是空的</h3><p>看到想说的话，就给它点一个加号。</p><button class="outline" data-action="close-modal">去菜单看看</button></div>`);
}
function showDetail(id){ const item=itemById(id); if(!item)return; openSheet('菜谱详情',`<img class="detail-image" src="${h(item.image)}" alt="${h(item.name)}"><div class="detail-name">${h(item.name)}</div><div class="detail-desc">${h(item.description||'今天也想和你一起。')}</div><p class="detail-meta">${h(item.category)}　·　月销 ${h(item.sales||0)}</p><button class="primary-button" data-action="add-and-close" data-id="${h(item.id)}">加入点单</button>`); }
function showInvite(){
  const members=state.doc.members;
  openSheet('你们的双人厨房',`<p class="invite-title">两个账号，一个小厨房</p><p class="invite-info">${members.map(u=>`${h(u.nickname)}（${h(u.username)}）`).join(' · ')}</p><p class="invite-info">另一位成员用自己的账号和密码登录同一网址即可。你的订单会自动发给对方，只有对方可以接单或完成。</p><div class="share-link">${h(location.origin)}</div><p class="invite-info">只分享网址，不分享密码。手机与PC访问同一个服务器，数据会同步。</p>`);
}

function recipeForm(item=null){
  const imageOptions=menu().slice(0,22).map(option=>`<button type="button" class="image-choice ${item?.image===option.image?'selected':''}" data-image="${h(option.image)}"><img src="${h(option.image)}" alt=""></button>`).join('');
  openSheet(item?'修改菜谱':'添加菜谱',`<form id="recipeForm"><input type="hidden" name="id" value="${h(item?.id||'')}"><label class="form-field">菜谱名称<input name="name" required maxlength="50" value="${h(item?.name||'')}" placeholder="例如：给你一个大大的拥抱"></label><label class="form-field">一句说明<input name="description" maxlength="150" value="${h(item?.description||'')}" placeholder="例如：今天也要开心"></label><label class="form-field">放到分类<select name="category" required>${categories().map(c=>`<option value="${h(c.id)}" ${c.id===(item?.category||state.activeCategory)?'selected':''}>${h(c.name)}</option>`).join('')}</select></label><div class="form-field">选择一张菜单图<div class="image-options" id="imageOptions">${imageOptions}</div><input type="hidden" name="image" value="${h(item?.image||menu()[0]?.image||'/assets/item-001.jpg')}"><div class="image-preview"><img id="recipePreview" src="${h(item?.image||menu()[0]?.image||'/assets/item-001.jpg')}" alt="预览"><label>上传 JPEG<input id="recipeUpload" type="file" accept="image/jpeg"></label></div></div><p class="form-error" id="recipeError"></p><button class="primary-button" type="submit">${item?'保存修改':'加入厨房'}</button>${item?`<button class="danger-button" type="button" data-action="delete-item" data-id="${h(item.id)}">从厨房移除</button>`:''}</form>`,body=>{
    $$('.image-choice',body).forEach(button=>button.addEventListener('click',()=>{ $$('.image-choice',body).forEach(x=>x.classList.remove('selected')); button.classList.add('selected'); $('input[name=image]',body).value=button.dataset.image; $('#recipePreview',body).src=button.dataset.image; }));
    $('#recipeUpload',body).addEventListener('change',async event=>{ const file=event.target.files?.[0]; if(!file)return; if(file.type!=='image/jpeg'||file.size>512000){$('#recipeError',body).textContent='请选择500KB以内的 JPEG 图片';return;} const reader=new FileReader(); reader.onload=async()=>{try{const result=await api('/api/upload',{method:'POST',body:JSON.stringify({data:reader.result})});$('input[name=image]',body).value=result.image;$('#recipePreview',body).src=result.image;toast('图片已放进厨房');}catch(error){$('#recipeError',body).textContent=error.message;}}; reader.readAsDataURL(file); });
    $('#recipeForm',body).addEventListener('submit',async event=>{event.preventDefault(); const data=Object.fromEntries(new FormData(event.currentTarget)); const error=$('#recipeError',body); error.textContent=''; try{const result=await api(data.id?`/api/menu/${encodeURIComponent(data.id)}`:'/api/menu',{method:data.id?'PATCH':'POST',body:JSON.stringify(data)}); closeSheet(); state.activeCategory=result.category; await refresh(); toast(data.id?'菜谱已更新':'已加入你们的厨房');}catch(ex){error.textContent=ex.message;} });
  });
}
function showSettings(){ const s=state.doc.settings; openSheet('厨房设置',`<form id="settingsForm"><label class="form-field">厨房名称<input name="name" maxlength="20" required value="${h(s.name)}"></label><label class="form-field">公告<input name="announcement" maxlength="100" value="${h(s.announcement==='暂无'?'':s.announcement)}" placeholder="暂无"></label><p class="form-help">成员：${s.members.map(h).join(" · ")}。身份来自登录账号，不能在这里切换。</p><p class="form-error" id="settingsError"></p><button class="primary-button" type="submit">保存厨房设置</button></form>`,body=>$('#settingsForm',body).addEventListener('submit',async event=>{event.preventDefault();const f=new FormData(event.currentTarget);const error=$('#settingsError',body);try{await api('/api/settings',{method:'PATCH',body:JSON.stringify({name:f.get('name'),announcement:f.get('announcement'),members:s.members})});closeSheet();await refresh();toast('厨房设置已保存');}catch(ex){error.textContent=ex.message;}})); }
function showAbout(){openSheet('关于这个复刻',`<p>这是根据你提供的《情侣趣味厨房 · 独家御膳房》截图和轮播素材做的可操作本地版。</p><ul class="about-list"><li>复刻了参考里可观察的白底点单页、分类栏、粉色加号、底部点单栏和四项导航。</li><li>菜单文字与配图优先使用已读清的原图条目；没有读清的条目不冒充原内容，可在“修改”里自己补齐。</li><li>“添加菜谱、搜索、随机选菜、邀请下单、订单状态、设置”是为了让这个项目真正可操作而补齐的功能。</li><li>数据存于服务器 SQLite；使用两个独立账号，不接入支付、微信或真实快递服务。</li></ul><a class="restore-link" href="/assets/item-001.jpg" target="_blank" rel="noreferrer">查看本地参考素材</a>`);}
function renderOrders(){
  const all=state.doc?.orders||[];const orders=all.filter(o=>state.filter==='all'||o.status===state.filter);const viewer=state.doc?.viewer?.id;
  $('#orderList').innerHTML=orders.length?orders.map(order=>{
    const received=order.recipientId===viewer;const mine=order.createdBy===viewer;const legacy=!order.createdBy||!order.recipientId;
    let buttons='';
    if(order.status==='pending'){
      if(received)buttons+=`<button class="accept-order" data-action="order-status" data-id="${h(order.id)}" data-status="accepted">接单</button>`;
      if(received||mine)buttons+=`<button data-action="order-status" data-id="${h(order.id)}" data-status="cancelled">取消</button>`;
    }
    if(order.status==='accepted'&&received)buttons+=`<button class="complete-order" data-action="order-status" data-id="${h(order.id)}" data-status="completed">完成这份心意</button>`;
    const recipientAccount=state.doc?.members?.find(member=>member.id===order.recipientId);
    const actionHint=received&&order.status==='pending'?'这份心意发给你：点击“接单”开始，再点击“完成这份心意”。':mine&&['pending','accepted'].includes(order.status)?`当前账号 ${h(state.doc.viewer.username)} 是下单人，请接收方账号 ${h(recipientAccount?.username||order.recipient)} 登录接单。`:'';
    return `<article class="order-card"><div class="order-heading"><span>#${h(order.id)}</span><span class="status-pill status-${h(order.status)}">${h(statusText(order.status))}</span></div><div class="order-direction">${legacy?'历史订单 · 未绑定账号':`${mine?'我送出的心意':'我收到的心意'} · ${h(order.customer)} → ${h(order.recipient)}`}</div><p class="order-meta">${h(formatDate(order.createdAt))}</p>${order.items.map(item=>`<div class="order-item"><img src="${h(item.image)}" alt=""><strong>${h(item.name)}</strong><span>×${item.quantity}</span></div>`).join('')}${order.note?`<p class="order-note">备注：${h(order.note)}</p>`:''}<div class="order-bottom"><span>本单不设金额，用心意结算</span><div class="order-buttons order-actions">${buttons}</div></div>${actionHint?`<p class="order-context" role="status">${actionHint}</p>`:''}</article>`;
  }).join(''):`<div class="empty-state"><h3>还没有这类心意</h3><p>去菜单挑一份，送给另一半吧。</p></div>`;
}

function renderDiscover(){ const featured=menu().filter(item=>['小情绪','调情','漂亮饭','水果','游戏'].includes(item.category)).slice(0,6); $('#discoverGrid').innerHTML=featured.map(item=>`<button class="discover-tile" data-action="add" data-id="${h(item.id)}"><img src="${h(item.image)}" alt=""><strong>${h(item.name)}</strong><span>${h(item.description||'点一下，送进厨房')}</span></button>`).join(''); const daily=menu().find(item=>item.name==='抱抱')||menu()[0]; if(daily){$('#dailyName').textContent=daily.name;$('#dailyAdd').dataset.id=daily.id;} }
function renderMe(){ const orders=state.doc?.orders||[]; $('#statMenu').textContent=menu().length; $('#statOrders').textContent=orders.length; $('#statDone').textContent=orders.filter(o=>o.status==='completed').length; $('#roleLabel').textContent=`${state.role}（${state.doc.viewer.username}）`; }
function updateOrderDot(){ $('#orderDot').hidden=!(state.doc?.orders||[]).some(o=>o.status==='pending'); }
async function submitOrder(){
  if(!state.cart.length)return; const note=$('#cartNote')?.value||''; const requestId=localStorage.getItem(requestStorageKey())||((crypto.randomUUID?.()||`${Date.now()}-${Math.random()}`).replace(/[^A-Za-z0-9-]/g,'')).slice(0,70); localStorage.setItem(requestStorageKey(),requestId);
  try{const order=await api('/api/orders',{method:'POST',body:JSON.stringify({items:state.cart,note,customer:state.role,requestId})}); state.cart=[];saveCart();closeSheet();await refresh();setView('orders');toast(`已下单给另一半 · ${order.id}`);localStorage.removeItem(requestStorageKey());}catch(error){toast(error.message,4000);}
}
function randomPick(){const items=menu().filter(item=>item.category!=='小狗快递'); if(!items.length)return;const item=items[Math.floor(Math.random()*items.length)];state.activeCategory=item.category;addToCart(item.id);renderCategories();renderMenu();}
async function copyText(value){try{await navigator.clipboard.writeText(value);toast('邀请链接已复制');}catch{const area=document.createElement('textarea');area.value=value;document.body.append(area);area.select();document.execCommand('copy');area.remove();toast('邀请链接已复制');}}
async function exportData(){ const data=JSON.stringify({...state.doc,csrf:undefined},null,2);const blob=new Blob([data],{type:'application/json'});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='couple-kitchen-backup.json';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);toast('厨房数据已下载'); }
async function clickAction(action,target){
  const id=target.dataset.id;
  if(action==='add') addToCart(id);
  if(action==='minus') addToCart(id,-1);
  if(action==='detail') showDetail(id);
  if(action==='add-and-close'){addToCart(id);closeSheet();}
  if(action==='add-recipe') recipeForm();
  if(action==='edit-item') recipeForm(itemById(id));
  if(action==='delete-item'){if(!confirm('从厨房移除这道菜谱？'))return;try{await api(`/api/menu/${encodeURIComponent(id)}`,{method:'DELETE'});closeSheet();await refresh();toast('菜谱已移除');}catch(error){toast(error.message,4000);}}
  if(action==='close-modal') closeSheet();
  if(action==='submit-order') submitOrder();
  if(action==='copy-invite') copyText(target.dataset.link);
  if(action==='order-status'){try{await api(`/api/orders/${encodeURIComponent(id)}`,{method:'PATCH',body:JSON.stringify({status:target.dataset.status})});await refresh();toast('订单状态已更新');}catch(error){toast(error.message,4000);}}
  if(action==='go-kitchen'){closeSheet();setView('kitchen');}
}
document.addEventListener('click',event=>{
  const action=event.target.closest('[data-action]')?.dataset.action;
  if(action){event.preventDefault();clickAction(action,event.target.closest('[data-action]'));return;}
  const buttonId=event.target.closest('button[id]')?.id;
  if(buttonId==='orderMode'||buttonId==='editMode'){
    state.edit=buttonId==='editMode';
    $('#orderMode').classList.toggle('active',!state.edit);
    $('#editMode').classList.toggle('active',state.edit);
    renderMenu();
    return;
  }
  const category=event.target.closest('[data-category]')?.dataset.category;
  if(category){state.activeCategory=category;state.query='';$('#searchInput').value='';renderCategories();renderMenu();$('#menuList').scrollTop=0;return;}
  const nav=event.target.closest('.bottom-nav button')?.dataset.view;if(nav){setView(nav);return;}
  const filter=event.target.closest('[data-filter]')?.dataset.filter;if(filter){state.filter=filter;$$('#orderFilters button').forEach(b=>b.classList.toggle('active',b.dataset.filter===filter));renderOrders();return;}
  if(buttonId==='openCart')showCart();
  if(buttonId==='inviteOrder'||buttonId==='inviteTop'||buttonId==='meInvite')showInvite();
  if(buttonId==='addRecipe')recipeForm();
  if(buttonId==='openSearch'){$('#searchBox').hidden=false;$('#searchInput').focus();}
  if(buttonId==='closeSearch'){$('#searchBox').hidden=true;state.query='';$('#searchInput').value='';renderMenu();}
  if(buttonId==='closeModal'||event.target=== $('#modalOverlay'))closeSheet();
  if(buttonId==='checkout')showCart();
  if(buttonId==='randomPick')randomPick();
  if(buttonId==='settingsButton')showSettings();
  if(buttonId==='aboutButton')showAbout();
  if(buttonId==='exportButton')exportData();
  if(buttonId==='retryLoad')refresh();
  if(buttonId==='dailyAdd')addToCart(event.target.dataset.id);
});
$('#searchInput').addEventListener('input',event=>{state.query=event.target.value.trim();renderMenu();});
window.addEventListener('storage',event=>{if(event.key===cartStorageKey()){loadCart();renderCart();renderMenu();}});

setInterval(()=>{if(state.doc&&state.view==='orders')refresh().then(updateOrderDot);},10000);