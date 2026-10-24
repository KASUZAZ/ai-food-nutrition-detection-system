'use strict';
const $ = id => document.getElementById(id);
const nf = new Intl.NumberFormat('ms-MY', {maximumFractionDigits: 1});
const h = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let authenticated = false, meals = [], foods = [], editingMeal = null, editingFood = null;
let currentTab = 'live', lastPhoto = '', liveBusy = false, dataBusy = false;
let pendingCommand = null, pendingCommandStatus = null;
const tabs = {
  live: ['Paparan langsung', 'Bacaan semasa dan rekod pemakanan anda.'],
  history: ['Sejarah makanan', 'Setiap hidangan, disimpan untuk rujukan anda.'],
  catalog: ['Pangkalan kalori', 'Urus jenis makanan dan rujukan tenaga bagi setiap hidangan.']
};
function malaysiaDate(value = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Kuala_Lumpur', year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', hourCycle:'h23'}).formatToParts(new Date(value));
  const p = Object.fromEntries(parts.map(x => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}
function dateTime(value, timeOnly = false) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('ms-MY', {timeZone:'Asia/Kuala_Lumpur', ...(timeOnly ? {} : {day:'2-digit',month:'short',year:'numeric'}),hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(value));
}
function notify(message, error = false) {
  $('notice').textContent = message;
  $('notice').classList.toggle('error', error);
  $('notice').hidden = !message;
}
function setAuth(value) {
  authenticated = value;
  $('auth-button').textContent = value ? 'Kunci akses pentadbir' : 'Buka akses pentadbir';
  document.querySelectorAll('[data-admin]').forEach(b => b.disabled = !value);
  renderTables();
  renderCatalog();
}
async function api(path, method = 'GET', data) {
  const response = await fetch(path, {method, cache:'no-store', headers: data === undefined ? {} : {'Content-Type':'application/json'}, body:data === undefined ? undefined : JSON.stringify(data)});
  const payload = await response.json();
  if (!response.ok) {
    if (response.status === 401 && path !== '/api/login') setAuth(false);
    throw new Error(payload.error || 'Permintaan gagal. Cuba lagi.');
  }
  return payload;
}
function selectTab(tab) {
  if (!tabs[tab]) return;
  currentTab = tab;
  Object.keys(tabs).forEach(key => $('panel-' + key).hidden = key !== tab);
  document.querySelectorAll('.nav-button').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === tab);
    if (b.dataset.tab === tab) b.setAttribute('aria-current', 'page');
    else b.removeAttribute('aria-current');
  });
  $('page-title').textContent = tabs[tab][0];
  $('breadcrumb').textContent = tabs[tab][0];
  $('page-subtitle').textContent = tabs[tab][1];
}
function tableMarkup(rows, full) {
  if (!rows.length) return `<div class="empty-table"><span aria-hidden="true">▤</span><strong>Belum ada rekod makanan${$('history-date').value && full ? ' pada tarikh ini' : ''}</strong><p>Rekod sensor muncul selepas makanan dikesan dan berat stabil.<br>Pentadbir juga boleh tambah rekod secara manual.</p></div>`;
  return `<div class="table-wrap"><table><thead><tr><th>MAKANAN</th><th>WAKTU MAKAN</th><th>BERAT</th><th>KALORI</th><th>SUMBER</th>${authenticated ? '<th>TINDAKAN</th>' : ''}</tr></thead><tbody>${rows.map(m => `<tr><td><div class="meal-name">${m.image_url ? `<a href="${h(m.image_url)}" target="_blank" rel="noopener" aria-label="Lihat gambar ${h(m.food)}"><img class="thumbnail" src="${h(m.image_url)}?v=${encodeURIComponent(m.updated_at)}" alt="${h(m.food)}" loading="lazy"></a>` : '<span class="no-photo" aria-hidden="true">▧</span>'}<span>${h(m.food)}</span></div></td><td>${h(dateTime(m.eaten_at))}</td><td>${nf.format(m.weight_g)} g</td><td>${nf.format(m.calories)} kcal</td><td><span class="source-tag ${m.source === 'manual' ? 'manual' : ''}">${m.source === 'sensor' ? 'Sensor' : 'Manual'}</span></td>${authenticated ? `<td><button class="text-button" data-edit-meal="${m.id}">Edit</button></td>` : ''}</tr>`).join('')}</tbody></table></div>`;
}
function renderTables() {
  $('recent-table').innerHTML = tableMarkup(meals.slice(0, 5), false);
  const date = $('history-date').value;
  $('history-table').innerHTML = tableMarkup(date ? meals.filter(m => m.eaten_at.slice(0,10) === date) : meals, true);
  const today = malaysiaDate().slice(0, 10);
  const daily = meals.filter(m => m.eaten_at.slice(0,10) === today);
  $('daily-calories').innerHTML = `${nf.format(daily.reduce((s, m) => s + m.calories, 0))} <small>kcal</small>`;
  $('daily-count').innerHTML = `${daily.length} <small>rekod</small>`;
}
function renderCatalog() {
  $('catalog-table').innerHTML = `<div class="table-wrap"><table><thead><tr><th>JENIS MAKANAN</th><th>KCAL / 100 G</th><th>NOTA</th>${authenticated ? '<th>TINDAKAN</th>' : ''}</tr></thead><tbody>${foods.map(f => `<tr><td><strong>${h(f.food)}</strong></td><td>${nf.format(f.calorie_per_gram * 100)}</td><td>${h(f.note)}</td>${authenticated ? `<td><button class="text-button" data-edit-food="${f.id}">Edit</button></td>` : ''}</tr>`).join('')}</tbody></table></div>`;
  $('food-options').innerHTML = foods.map(f => `<option value="${h(f.food)}"></option>`).join('');
}
async function refreshLive() {
  if (liveBusy) return;
  liveBusy = true;
  try {
    const d = await api('/api/live');
    const cloud = d.deployment === 'cloud';
    $('storage-label').textContent = cloud ? 'Disimpan di Vercel' : 'Disimpan pada laptop';
    const s = d.scale || {}, r = d.result;
    const online = d.scale_online && s.sensor_ready === true;
    const matched = online && r?.accepted && s.detection_id === r.detection_id && s.weight_g > 0;
    $('connection').textContent = online ? '● Penimbang tersambung' : cloud && !d.bridge_online ? 'Laptop luar talian' : 'Penimbang luar talian';
    $('connection').classList.toggle('online', online);
    $('live-weight').innerHTML = `${online ? nf.format(s.weight_g) : '—'} <small>g</small>`;
    $('live-calories').innerHTML = `${matched ? nf.format(s.weight_g * r.calorie_per_gram) : '—'} <small>kcal</small>`;
    $('weight-hint').textContent = online ? (s.locked ? 'Stabil · berat dikunci' : 'Membaca berat…') : 'Semak sambungan / tetapan IP penimbang';
    $('lock-status').textContent = online ? (s.locked ? 'Stabil / LOCK' : 'Sedang membaca') : 'Luar talian';
    $('updated-at').textContent = 'Disemak ' + dateTime(d.server_time, true);
    $('detected-food').textContent = r ? r.food : 'Belum dikesan';
    $('confidence').textContent = r ? nf.format(r.confidence * 100) + '%' : '—';
    $('calorie-rate').textContent = r ? nf.format(r.calorie_per_gram * 100) + ' kcal' : '—';
    $('detected-time').textContent = dateTime(d.detected_at, true);
    $('detection-note').textContent = cloud && !d.bridge_online ? 'Menunggu laptop penghubung. Sejarah dan rekod manual kekal tersedia.' : !d.model_ready ? 'Mod web sahaja. Rekod manual tersedia; model AI belum dimuatkan.' : !r ? 'Keputusan AI akan dipaparkan di sini.' : !r.accepted ? 'Keyakinan rendah · keputusan ditolak, tiada rekod automatik.' : matched ? 'Diterima · menunggu / menggunakan berat stabil.' : 'Keputusan gambar terakhir · menunggu padanan bacaan penimbang.';
    const command = (d.commands || []).find(c => c.id === pendingCommand);
    if (command && command.status !== pendingCommandStatus) {
      pendingCommandStatus = command.status;
      if (['succeeded','failed','expired'].includes(command.status)) {
        notify(command.message, command.status !== 'succeeded');
        pendingCommand = null;
      }
    }
    if (r && lastPhoto !== r.detection_id) {
      $('latest-image').src = '/latest.jpg?t=' + encodeURIComponent(r.detection_id);
      lastPhoto = r.detection_id;
      $('latest-image').hidden = false;
      $('camera-empty').hidden = true;
      $('photo-caption').hidden = false;
    }
  } catch (error) {
    $('connection').textContent = 'Website terputus · mencuba semula';
    $('connection').classList.remove('online');
    $('live-weight').innerHTML = '— <small>g</small>';
    $('live-calories').innerHTML = '— <small>kcal</small>';
    $('weight-hint').textContent = 'Server tidak dapat dihubungi';
    $('lock-status').textContent = 'Luar talian';
  } finally { liveBusy = false; }
}
async function refreshData() {
  if (dataBusy) return;
  dataBusy = true;
  try {
    const [m, f, session] = await Promise.all([api('/api/meals'), api('/api/foods'), api('/api/session')]);
    meals = m.meals; foods = f.foods;
    setAuth(session.authenticated);
  } catch (error) { notify('Rekod tidak dapat dikemas kini. ' + error.message, true); }
  finally { dataBusy = false; }
}
function openMeal(id = null) {
  if (!authenticated) return $('login-dialog').showModal();
  const form = $('meal-form');
  form.reset();
  form.querySelector('.form-error').textContent = '';
  editingMeal = id;
  const meal = meals.find(m => m.id === id);
  $('meal-title').textContent = meal ? 'Edit rekod makanan' : 'Tambah rekod makanan';
  if (meal) ['food','weight_g','calories'].forEach(key => form.elements[key].value = meal[key]);
  form.elements.eaten_at.value = malaysiaDate(meal?.eaten_at || new Date());
  $('meal-dialog').showModal();
}
function openFood(id = null) {
  if (!authenticated) return $('login-dialog').showModal();
  const form = $('food-form');
  form.reset();
  form.querySelector('.form-error').textContent = '';
  editingFood = id;
  const food = foods.find(f => f.id === id);
  $('food-title').textContent = food ? 'Edit rujukan makanan' : 'Tambah rujukan makanan';
  if (food) {
    form.elements.food.value = food.food;
    form.elements.calories_per_100g.value = (food.calorie_per_gram * 100).toFixed(2);
    form.elements.note.value = food.note;
  }
  $('food-dialog').showModal();
}
async function submitForm(event, action) {
  event.preventDefault();
  const form = event.currentTarget, submit = form.querySelector('[type=submit]');
  form.querySelector('.form-error').textContent = '';
  submit.disabled = true;
  try { await action(form); }
  catch (error) { form.querySelector('.form-error').textContent = error.message; }
  finally { submit.disabled = false; }
}
document.addEventListener('click', event => {
  const b = event.target.closest('button');
  if (!b || b.disabled) return;
  if (b.dataset.tab) selectTab(b.dataset.tab);
  if (b.hasAttribute('data-close')) b.closest('dialog').close();
  if (b.dataset.editMeal) openMeal(Number(b.dataset.editMeal));
  if (b.dataset.editFood) openFood(Number(b.dataset.editFood));
});
$('auth-button').addEventListener('click', async () => {
  if (!authenticated) {
    $('login-form').reset();
    $('login-form').querySelector('.form-error').textContent = '';
    $('login-dialog').showModal();
    return;
  }
  try { await api('/api/logout', 'POST', {}); setAuth(false); notify('Akses pentadbir telah dikunci.'); }
  catch (error) { notify(error.message, true); }
});
$('login-form').addEventListener('submit', e => submitForm(e, async form => {
  await api('/api/login', 'POST', {password:form.elements.password.value});
  form.reset(); $('login-dialog').close(); setAuth(true);
  notify('Akses pentadbir dibuka tanpa had masa. Tekan Kunci akses pentadbir apabila selesai.');
}));
$('new-meal').addEventListener('click', () => openMeal());
$('new-food').addEventListener('click', () => openFood());
$('history-date').addEventListener('change', renderTables);
$('clear-date').addEventListener('click', () => { $('history-date').value = ''; renderTables(); });
function estimateMeal() {
  const form = $('meal-form');
  const food = foods.find(f => f.food.toLowerCase() === form.elements.food.value.trim().toLowerCase());
  if (food && form.elements.weight_g.value) form.elements.calories.value = (Number(form.elements.weight_g.value) * food.calorie_per_gram).toFixed(2);
}
$('meal-form').elements.food.addEventListener('change', estimateMeal);
$('meal-form').elements.weight_g.addEventListener('input', estimateMeal);
$('meal-form').addEventListener('submit', e => submitForm(e, async form => {
  const data = {food:form.elements.food.value, weight_g:Number(form.elements.weight_g.value), calories:Number(form.elements.calories.value), eaten_at:form.elements.eaten_at.value + ':00+08:00'};
  const file = form.elements.image.files[0];
  if (file) {
    if (file.size > 2 * 1024 * 1024) throw new Error('Gambar maksimum 2 MB.');
    data.image_base64 = await new Promise((resolve,reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(',')[1]);
      reader.onerror = () => reject(new Error('Gambar tidak dapat dibaca.'));
      reader.readAsDataURL(file);
    });
  }
  await api('/api/meals' + (editingMeal === null ? '' : '/' + editingMeal), editingMeal === null ? 'POST' : 'PUT', data);
  $('meal-dialog').close(); notify('Rekod makanan telah disimpan.'); await refreshData();
}));
$('food-form').addEventListener('submit', e => submitForm(e, async form => {
  await api('/api/foods' + (editingFood === null ? '' : '/' + editingFood), editingFood === null ? 'POST' : 'PUT', {food:form.elements.food.value, calories_per_100g:Number(form.elements.calories_per_100g.value), note:form.elements.note.value});
  $('food-dialog').close(); notify('Rujukan kalori disimpan dan dikemas kini untuk pengesanan seterusnya.'); await refreshData();
}));
for (const action of ['capture', 'tare']) {
  $(action + '-button').addEventListener('click', async event => {
    const button = event.currentTarget;
    button.disabled = true;
    try { const d = await api('/api/' + action, 'POST', {}); pendingCommand = d.command_id || null; pendingCommandStatus = null; notify(d.message || 'Permintaan diterima.'); }
    catch (error) { notify(error.message, true); }
    finally { button.disabled = !authenticated; }
  });
}
$('today-label').textContent = new Intl.DateTimeFormat('ms-MY', {timeZone:'Asia/Kuala_Lumpur', day:'numeric',month:'short',year:'numeric'}).format(new Date());
selectTab(currentTab);
refreshLive(); refreshData();
setInterval(refreshLive, 1000);
setInterval(refreshData, 5000);
