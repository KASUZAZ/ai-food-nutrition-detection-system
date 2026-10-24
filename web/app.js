'use strict';
const $ = id => document.getElementById(id);
const nf = new Intl.NumberFormat('en-MY', {maximumFractionDigits: 1});
const h = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let authenticated = false, meals = [], foods = [], editingMeal = null, editingFood = null;
let currentTab = 'live', lastPhoto = '', liveBusy = false, dataBusy = false;
let pendingCommand = null, pendingCommandStatus = null;
const tabs = {
  live: ['Live dashboard', 'Live readings and your meal records.'],
  history: ['Meal history', 'Every meal, saved for your reference.'],
  catalog: ['Calorie database', 'Manage food types and calorie references for each meal.']
};
function malaysiaDate(value = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Kuala_Lumpur', year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', hourCycle:'h23'}).formatToParts(new Date(value));
  const p = Object.fromEntries(parts.map(x => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}
function dateTime(value, timeOnly = false) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('en-MY', {timeZone:'Asia/Kuala_Lumpur', ...(timeOnly ? {} : {day:'2-digit',month:'short',year:'numeric'}),hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(value));
}
function notify(message, error = false) {
  $('notice').textContent = message;
  $('notice').classList.toggle('error', error);
  $('notice').hidden = !message;
}
function setAuth(value) {
  authenticated = value;
  $('auth-button').textContent = value ? 'Lock admin access' : 'Unlock admin access';
  document.querySelectorAll('[data-admin]').forEach(b => b.disabled = !value);
  renderTables();
  renderCatalog();
}
async function api(path, method = 'GET', data) {
  const response = await fetch(path, {method, cache:'no-store', headers: data === undefined ? {} : {'Content-Type':'application/json'}, body:data === undefined ? undefined : JSON.stringify(data)});
  const payload = await response.json();
  if (!response.ok) {
    if (response.status === 401 && path !== '/api/login') setAuth(false);
    throw new Error(payload.error || 'Request failed. Please try again.');
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
  if (!rows.length) return `<div class="empty-table"><span aria-hidden="true">▤</span><strong>No meal records yet${$('history-date').value && full ? ' for this date' : ''}</strong><p>Sensor records appear after food is detected and the weight is stable.<br>Admins can also add records manually.</p></div>`;
  return `<div class="table-wrap"><table><thead><tr><th>FOOD</th><th>MEAL TIME</th><th>WEIGHT</th><th>CALORIES</th><th>SOURCE</th>${authenticated ? '<th>ACTIONS</th>' : ''}</tr></thead><tbody>${rows.map(m => `<tr><td><div class="meal-name">${m.image_url ? `<a href="${h(m.image_url)}" target="_blank" rel="noopener" aria-label="View photo of ${h(m.food)}"><img class="thumbnail" src="${h(m.image_url)}?v=${encodeURIComponent(m.updated_at)}" alt="${h(m.food)}" loading="lazy"></a>` : '<span class="no-photo" aria-hidden="true">▧</span>'}<span>${h(m.food)}</span></div></td><td>${h(dateTime(m.eaten_at))}</td><td>${nf.format(m.weight_g)} g</td><td>${nf.format(m.calories)} kcal</td><td><span class="source-tag ${m.source === 'manual' ? 'manual' : ''}">${m.source === 'sensor' ? 'Sensor' : 'Manual'}</span></td>${authenticated ? `<td><button class="text-button" data-edit-meal="${m.id}">Edit</button></td>` : ''}</tr>`).join('')}</tbody></table></div>`;
}
function renderTables() {
  $('recent-table').innerHTML = tableMarkup(meals.slice(0, 5), false);
  const date = $('history-date').value;
  $('history-table').innerHTML = tableMarkup(date ? meals.filter(m => m.eaten_at.slice(0,10) === date) : meals, true);
  const today = malaysiaDate().slice(0, 10);
  const daily = meals.filter(m => m.eaten_at.slice(0,10) === today);
  $('daily-calories').innerHTML = `${nf.format(daily.reduce((s, m) => s + m.calories, 0))} <small>kcal</small>`;
  $('daily-count').innerHTML = `${daily.length} <small>records</small>`;
}
function renderCatalog() {
  $('catalog-table').innerHTML = `<div class="table-wrap"><table><thead><tr><th>FOOD TYPE</th><th>KCAL / 100 G</th><th>NOTES</th>${authenticated ? '<th>ACTIONS</th>' : ''}</tr></thead><tbody>${foods.map(f => `<tr><td><strong>${h(f.food)}</strong></td><td>${nf.format(f.calorie_per_gram * 100)}</td><td>${h(f.note)}</td>${authenticated ? `<td><button class="text-button" data-edit-food="${f.id}">Edit</button></td>` : ''}</tr>`).join('')}</tbody></table></div>`;
  $('food-options').innerHTML = foods.map(f => `<option value="${h(f.food)}"></option>`).join('');
}
async function refreshLive() {
  if (liveBusy) return;
  liveBusy = true;
  try {
    const d = await api('/api/live');
    const cloud = d.deployment === 'cloud';
    $('storage-label').textContent = cloud ? 'Saved on Vercel' : 'Saved on laptop';
    const s = d.scale || {}, r = d.result;
    const online = d.scale_online && s.sensor_ready === true;
    const matched = online && r?.accepted && s.detection_id === r.detection_id && s.weight_g > 0;
    $('connection').textContent = online ? '● Scale connected' : cloud && !d.bridge_online ? 'Laptop offline' : 'Scale offline';
    $('connection').classList.toggle('online', online);
    $('live-weight').innerHTML = `${online ? nf.format(s.weight_g) : '—'} <small>g</small>`;
    $('live-calories').innerHTML = `${matched ? nf.format(s.weight_g * r.calorie_per_gram) : '—'} <small>kcal</small>`;
    $('weight-hint').textContent = online ? (s.locked ? 'Stable · weight locked' : 'Reading weight…') : 'Check the scale connection / IP settings';
    $('lock-status').textContent = online ? (s.locked ? 'Stable / LOCK' : 'Reading weight') : 'Offline';
    $('updated-at').textContent = 'Checked ' + dateTime(d.server_time, true);
    $('detected-food').textContent = r ? r.food : 'Not detected yet';
    $('confidence').textContent = r ? nf.format(r.confidence * 100) + '%' : '—';
    $('calorie-rate').textContent = r ? nf.format(r.calorie_per_gram * 100) + ' kcal' : '—';
    $('detected-time').textContent = dateTime(d.detected_at, true);
    $('detection-note').textContent = cloud && !d.bridge_online ? 'Waiting for the laptop bridge. History and manual records remain available.' : !d.model_ready ? 'Web-only mode. Manual records are available; the AI model is not loaded.' : !r ? 'AI results will appear here.' : !r.accepted ? 'Low confidence · result rejected, no automatic record.' : matched ? 'Accepted · waiting for / using stable weight.' : 'Latest photo result · waiting for a matching scale reading.';
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
    $('connection').textContent = 'Connection lost · retrying';
    $('connection').classList.remove('online');
    $('live-weight').innerHTML = '— <small>g</small>';
    $('live-calories').innerHTML = '— <small>kcal</small>';
    $('weight-hint').textContent = 'Cannot reach the server';
    $('lock-status').textContent = 'Offline';
  } finally { liveBusy = false; }
}
async function refreshData() {
  if (dataBusy) return;
  dataBusy = true;
  try {
    const [m, f, session] = await Promise.all([api('/api/meals'), api('/api/foods'), api('/api/session')]);
    meals = m.meals; foods = f.foods;
    setAuth(session.authenticated);
  } catch (error) { notify('Could not refresh records. ' + error.message, true); }
  finally { dataBusy = false; }
}
function openMeal(id = null) {
  if (!authenticated) return $('login-dialog').showModal();
  const form = $('meal-form');
  form.reset();
  form.querySelector('.form-error').textContent = '';
  editingMeal = id;
  const meal = meals.find(m => m.id === id);
  $('meal-title').textContent = meal ? 'Edit meal record' : 'Add meal record';
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
  $('food-title').textContent = food ? 'Edit food reference' : 'Add food reference';
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
  try { await api('/api/logout', 'POST', {}); setAuth(false); notify('Admin access locked.'); }
  catch (error) { notify(error.message, true); }
});
$('login-form').addEventListener('submit', e => submitForm(e, async form => {
  await api('/api/login', 'POST', {password:form.elements.password.value});
  form.reset(); $('login-dialog').close(); setAuth(true);
  notify('Admin access unlocked for this browser session. Select Lock admin access when finished.');
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
    if (file.size > 2 * 1024 * 1024) throw new Error('Photos must not exceed 2 MB.');
    data.image_base64 = await new Promise((resolve,reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(',')[1]);
      reader.onerror = () => reject(new Error('Could not read the photo.'));
      reader.readAsDataURL(file);
    });
  }
  await api('/api/meals' + (editingMeal === null ? '' : '/' + editingMeal), editingMeal === null ? 'POST' : 'PUT', data);
  $('meal-dialog').close(); notify('Meal record saved.'); await refreshData();
}));
$('food-form').addEventListener('submit', e => submitForm(e, async form => {
  await api('/api/foods' + (editingFood === null ? '' : '/' + editingFood), editingFood === null ? 'POST' : 'PUT', {food:form.elements.food.value, calories_per_100g:Number(form.elements.calories_per_100g.value), note:form.elements.note.value});
  $('food-dialog').close(); notify('Food reference saved. The name and notes will be used for the next AI detection once the laptop is connected.'); await refreshData();
}));
for (const action of ['capture', 'tare']) {
  $(action + '-button').addEventListener('click', async event => {
    const button = event.currentTarget;
    button.disabled = true;
    try { const d = await api('/api/' + action, 'POST', {}); pendingCommand = d.command_id || null; pendingCommandStatus = null; notify(d.message || 'Request received.'); }
    catch (error) { notify(error.message, true); }
    finally { button.disabled = !authenticated; }
  });
}
$('today-label').textContent = new Intl.DateTimeFormat('en-MY', {timeZone:'Asia/Kuala_Lumpur', day:'numeric',month:'short',year:'numeric'}).format(new Date());
selectTab(currentTab);
refreshLive(); refreshData();
setInterval(refreshLive, 1000);
setInterval(refreshData, 5000);
