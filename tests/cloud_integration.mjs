// Explicit opt-in test against the configured real cloud resources. Own fixtures only.
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {randomUUID} from 'node:crypto';
import assert from 'node:assert/strict';
import sharp from 'sharp';
import handler,{database} from '../api/index.mjs';

const password=process.env.NUTRITRACK_TEST_ADMIN_PASSWORD;
if(!password) throw new Error('Set NUTRITRACK_TEST_ADMIN_PASSWORD for this opt-in test.');
const bridge=JSON.parse(await readFile('data/cloud-bridge.local.json','utf8'));
process.env.NUTRITRACK_DEVICE_TOKEN=bridge.token;
const server=createServer(handler);
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const base=process.env.NUTRITRACK_TEST_URL || `http://127.0.0.1:${server.address().port}`;
const sql=database(),suffix=randomUUID(),foodName='Ujian '+suffix.slice(0,8);
let cookie='',mealId,foodId,commandId;
const originalLive=await sql`SELECT * FROM nt_live WHERE id=1`;
async function request(path,method='GET',data,device=false){
  const response=await fetch(base+path,{method,headers:{...(data===undefined?{}:{'Content-Type':'application/json'}),Cookie:cookie,...(device?{Authorization:`Bearer ${bridge.token}`}:{})},body:data===undefined?undefined:JSON.stringify(data)});
  return {status:response.status,data:response.headers.get('content-type')?.includes('application/json')?await response.json():Buffer.from(await response.arrayBuffer()),headers:response.headers};
}
try{
  assert.equal((await request('/health')).status,200);
  assert.equal((await request('/api/meals','POST',{})).status,401);
  assert.equal((await request('/api/device/sync','POST',{})).status,401);
  assert.equal((await request('/api/login','POST',{password:'incorrect-test-password'})).status,401);
  const login=await request('/api/login','POST',{password});
  assert.equal(login.status,200);
  assert.ok(login.headers.get('set-cookie').includes('Secure'));
  assert.ok(!login.headers.get('set-cookie').includes('Max-Age'));
  cookie=login.headers.get('set-cookie').split(';')[0];
  assert.equal((await request('/api/session')).data.authenticated,true);
  const food=await request('/api/foods','POST',{food:foodName,calories_per_100g:130,note:'Temporary integration fixture'});
  assert.equal(food.status,201);
  foodId=(await sql`SELECT id FROM nt_foods WHERE food=${foodName}`)[0].id;
  const jpeg=await sharp({create:{width:30,height:30,channels:3,background:'#447755'}}).jpeg().toBuffer();
  const meal={food:foodName,weight_g:150,calories:195,eaten_at:'2026-10-23T16:56:00Z',image_base64:jpeg.toString('base64')};
  const created=await request('/api/meals','POST',meal);
  assert.equal(created.status,201); mealId=created.data.id;
  const photo=await request(`/api/meals/${mealId}/image`);
  assert.equal(photo.status,200); assert.equal(photo.data[0],0xff);
  assert.equal((await request(`/api/meals/${mealId}`,'PUT',{...meal,image_base64:undefined,calories:200})).status,200);
  const stored=(await request('/api/meals')).data.meals.find(m=>m.id===mealId);
  assert.equal(stored.calories,200); assert.equal(stored.eaten_at,'2026-10-24T00:56:00+08:00');
  const payload={live:{model_ready:false,detected_at:null,result:null,scale:null,scale_online:false},command_results:[]};
  const sync=await request('/api/device/sync','POST',payload,true);
  assert.equal(sync.status,200); assert.ok(sync.data.foods.some(f=>f.id===foodId));
  assert.equal((await request('/api/live')).data.bridge_online,true);
  const queued=await request('/api/capture','POST',{}); assert.equal(queued.status,202); commandId=queued.data.command_id;
  const claimed=await request('/api/device/sync','POST',payload,true);
  assert.ok(claimed.data.commands.some(c=>c.id===commandId));
  const completed=await request('/api/device/sync','POST',{...payload,command_results:[{id:commandId,status:'succeeded',message:'Temporary integration fixture acknowledged'}]},true);
  assert.ok(completed.data.acknowledged_commands.includes(commandId));
  const sensor={...meal,event_key:'integration:'+suffix,source:'sensor'};
  assert.equal((await request('/api/device/meal','POST',sensor,true)).status,200);
  assert.equal((await request('/api/device/meal','POST',sensor,true)).status,200);
  assert.equal((await sql`SELECT count(*)::int AS count FROM nt_meals WHERE event_key=${sensor.event_key}`)[0].count,1);
  assert.equal((await request('/api/logout','POST',{})).status,200);
  assert.equal((await request('/api/session')).data.authenticated,false);
  console.log('PASS: cloud login, session, meals, private Blob images, catalog, bridge, commands and deduplication.');
}finally{
  const photos=await sql`SELECT image_url FROM nt_meals WHERE id=${mealId||-1} OR event_key=${'integration:'+suffix}`;
  const {del}=await import('@vercel/blob');
  for(const row of photos) if(row.image_url) await del(row.image_url);
  await sql`DELETE FROM nt_meals WHERE id=${mealId||-1} OR event_key=${'integration:'+suffix}`;
  if(foodId) await sql`DELETE FROM nt_foods WHERE id=${foodId}`;
  if(commandId) await sql`DELETE FROM nt_commands WHERE id=${commandId}::uuid`;
  if(originalLive[0]) await sql`UPDATE nt_live SET payload=${JSON.stringify(originalLive[0].payload)}::jsonb,received_at=${originalLive[0].received_at} WHERE id=1`;
  else await sql`DELETE FROM nt_live WHERE id=1`;
  await new Promise(resolve=>server.close(resolve));
}
