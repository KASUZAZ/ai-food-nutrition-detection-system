import { createHash, randomBytes, pbkdf2Sync, timingSafeEqual, randomUUID } from 'node:crypto';
import { Readable } from 'node:stream';
import { neon } from '@neondatabase/serverless';
import { put, get, del } from '@vercel/blob';
import sharp from 'sharp';

let client;
export function database() {
  const url = process.env.DATABASE_URL || process.env.POSTGRES_URL;
  if (!url) throw new Error('DATABASE_URL is missing');
  return client ??= neon(url);
}
const digest = value => createHash('sha256').update(value).digest('hex');
const equal = (a, b) => {
  const left = Buffer.from(a), right = Buffer.from(b);
  return left.length === right.length && timingSafeEqual(left, right);
};
export function text(value, label, maximum = 100) {
  if (typeof value !== 'string' || !value.trim() || value.trim().length > maximum || /[\x00-\x1f]/.test(value)) throw problem(400, `${label} tidak sah`);
  return value.trim();
}
export function number(value, label, maximum = 100000) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > maximum) throw problem(400, `${label} tidak sah`);
  return value;
}
export function malaysiaTime(value) {
  if (value instanceof Date) value = value.toISOString();
  if (typeof value !== 'string') throw problem(400, 'Waktu makan tidak sah');
  if (!/(Z|[+-]\d{2}:\d{2})$/i.test(value)) value += '+08:00';
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) throw problem(400, 'Waktu makan tidak sah');
  return new Date(date.getTime() + 8 * 3600000).toISOString().slice(0, 19) + '+08:00';
}
function problem(status, message) { return Object.assign(new Error(message), { status }); }
async function body(req) {
  if ((req.headers['content-type'] || '').split(';')[0] !== 'application/json') throw problem(415, 'Content-Type mesti application/json');
  if (Number(req.headers['content-length']) > 3 * 1024 * 1024) throw problem(413,'Permintaan terlalu besar');
  if (req.body !== undefined) {
    let parsed = req.body;
    if (typeof parsed === 'string' || Buffer.isBuffer(parsed)) {
      try { parsed = JSON.parse(parsed.toString()); } catch { throw problem(400,'JSON tidak sah'); }
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw problem(400,'Objek JSON diperlukan');
    if (Buffer.byteLength(JSON.stringify(parsed)) > 3 * 1024 * 1024) throw problem(413,'Permintaan terlalu besar');
    return parsed;
  }
  const chunks = []; let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > 3 * 1024 * 1024) throw problem(413, 'Permintaan terlalu besar');
    chunks.push(chunk);
  }
  let data;
  try { data = JSON.parse(Buffer.concat(chunks).toString()); }
  catch { throw problem(400, 'JSON tidak sah'); }
  if (!data || typeof data !== 'object' || Array.isArray(data)) throw problem(400, 'Objek JSON diperlukan');
  return data;
}
export function cookieToken(header = '') {
  return header.split(';').map(v => v.trim()).find(v => v.startsWith('nutrition_session='))?.slice('nutrition_session='.length) || '';
}
async function authenticated(req) {
  const token = cookieToken(req.headers.cookie);
  if (!token || token.length > 200) return false;
  const rows = await database()`SELECT 1 FROM nt_sessions WHERE token_hash=${digest(token)}`;
  return rows.length > 0;
}
function json(res, status, value, extra = {}) {
  res.writeHead(status, { 'Content-Type':'application/json; charset=utf-8', ...extra });
  res.end(JSON.stringify(value));
}
export async function imageBuffer(encoded) {
  if (!encoded) return null;
  if (typeof encoded !== 'string' || encoded.length > 2800000 || !/^[A-Za-z0-9+/]*={0,2}$/.test(encoded)) throw problem(400, 'Gambar tidak sah atau melebihi 2 MB');
  const input = Buffer.from(encoded, 'base64');
  if (!input.length || input.length > 2 * 1024 * 1024) throw problem(400, 'Gambar maksimum 2 MB');
  try {
    return await sharp(input, { limitInputPixels:16000000 }).rotate().resize(1600,1600,{fit:'inside',withoutEnlargement:true}).jpeg({quality:85}).toBuffer();
  } catch { throw problem(400, 'Gambar tidak sah'); }
}
async function uploadImage(buffer, folder) {
  if (!buffer) return null;
  const blob = await put(`${folder}/${randomUUID()}.jpg`, buffer, {access:'private',contentType:'image/jpeg',addRandomSuffix:false});
  return blob.url;
}
async function removeImage(url) {
  if (url) await del(url).catch(() => console.error('Blob cleanup failed'));
}
async function serveImage(res, url) {
  if (!url) throw problem(404, 'Gambar belum tersedia');
  const blob = await get(url, {access:'private',useCache:false});
  if (!blob || blob.statusCode !== 200) throw problem(404, 'Gambar tidak ditemui');
  res.writeHead(200, {'Content-Type':'image/jpeg'});
  await new Promise((resolve,reject) => {
    const stream = Readable.fromWeb(blob.stream);
    stream.on('error',reject); res.on('finish',resolve); res.on('error',reject);
    stream.pipe(res);
  });
}
async function live() {
  const sql = database();
  const [rows,commands] = await Promise.all([
    sql`SELECT payload,received_at FROM nt_live WHERE id=1`,
    sql`SELECT id,action,status,message,created_at FROM nt_commands ORDER BY created_at DESC LIMIT 10`
  ]);
  const payload = rows[0]?.payload || {model_ready:false,scale:null,result:null,detected_at:null,scale_online:false};
  const age = rows[0] ? Date.now() - new Date(rows[0].received_at).getTime() : Infinity;
  const online = age >= 0 && age < 10000;
  return {...payload,deployment:'cloud',bridge_online:online,scale_online:online && payload.scale_online === true,
    server_time:new Date().toISOString(),bridge_seen_at:rows[0]?.received_at || null,commands};
}
export function mealValues(data) {
  const food = text(data.food,'Jenis makanan');
  const weight = number(data.weight_g,'Berat');
  if (weight <= 0) throw problem(400,'Berat mesti lebih daripada 0 g');
  return {food,weight,calories:number(data.calories,'Kalori',1000000),eaten:malaysiaTime(data.eaten_at)};
}
async function saveMeal(data, id = null, device = false) {
  const sql = database(), v = mealValues(data);
  const event = device ? text(data.event_key,'ID hidangan',200) : null;
  const source = device ? data.source || 'sensor' : 'manual';
  if (!['manual','sensor'].includes(source)) throw problem(400,'Sumber tidak sah');
  if (event && (await sql`SELECT id FROM nt_meals WHERE event_key=${event}`).length) return null;
  const old = id ? await sql`SELECT image_url FROM nt_meals WHERE id=${id}` : [];
  if (id && !old.length) throw problem(404,'Rekod tidak ditemui');
  const image = await uploadImage(await imageBuffer(data.image_base64),'meals');
  try {
    let rows;
    if (id) rows = await sql`UPDATE nt_meals SET food=${v.food},weight_g=${v.weight},calories=${v.calories},
      eaten_at=${v.eaten},image_url=coalesce(${image},image_url),updated_at=now() WHERE id=${id} RETURNING id`;
    else rows = await sql`INSERT INTO nt_meals(food,weight_g,calories,eaten_at,image_url,source,event_key)
      VALUES(${v.food},${v.weight},${v.calories},${v.eaten},${image},${source},${event})
      ON CONFLICT(event_key) DO NOTHING RETURNING id`;
    if (!rows.length) await removeImage(image);
    else if (image && old[0]?.image_url) await removeImage(old[0].image_url);
    return rows[0]?.id || null;
  } catch (error) { await removeImage(image); throw error; }
}
async function syncDevice(data) {
  const sql = database(), payload = data.live;
  if (!payload || typeof payload !== 'object' || typeof payload.model_ready !== 'boolean' || typeof payload.scale_online !== 'boolean') throw problem(400,'Bacaan live tidak sah');
  const results = data.command_results || [];
  if (!Array.isArray(results) || results.length > 20) throw problem(400,'Keputusan arahan tidak sah');
  for (const result of results) {
    if (!result || !/^[0-9a-f-]{36}$/i.test(result.id) || !['succeeded','failed'].includes(result.status)) throw problem(400,'Keputusan arahan tidak sah');
    text(result.message,'Mesej',500);
  }
  const published = Object.fromEntries(['model_ready','detected_at','result','scale','scale_online'].map(k=>[k,payload[k] ?? null]));
  const old = data.image_base64 ? await sql`SELECT latest_image FROM nt_live WHERE id=1` : [];
  const image = await uploadImage(await imageBuffer(data.image_base64),'live');
  try {
    await sql`INSERT INTO nt_live(id,payload,latest_image,received_at) VALUES(1,${JSON.stringify(published)}::jsonb,${image},now())
      ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,latest_image=coalesce(excluded.latest_image,nt_live.latest_image),received_at=now()`;
  } catch (error) { await removeImage(image); throw error; }
  if (image) await removeImage(old[0]?.latest_image);
  for (const result of results) await sql`UPDATE nt_commands SET status=${result.status},message=${result.message},completed_at=now()
    WHERE id=${result.id}::uuid AND status IN ('pending','leased')`;
  await sql`UPDATE nt_commands SET status='expired',message='Laptop tidak menjawab dalam masa yang ditetapkan.',completed_at=now()
    WHERE status IN ('pending','leased') AND created_at < now() - interval '90 seconds'`;
  const commands = await sql`WITH pending AS (
    SELECT id FROM nt_commands WHERE status='pending' OR (status='leased' AND leased_at < now() - interval '20 seconds')
    ORDER BY created_at LIMIT 5 FOR UPDATE SKIP LOCKED
  ) UPDATE nt_commands AS command SET status='leased',leased_at=now() FROM pending
    WHERE command.id=pending.id RETURNING command.id,command.action,command.created_at`;
  const foods = await sql`SELECT id,food,calorie_per_gram,note FROM nt_foods ORDER BY food`;
  return {ok:true,foods,commands,acknowledged_commands:results.map(r=>r.id)};
}

export default async function handler(req,res) {
  res.setHeader('Cache-Control','no-store');
  res.setHeader('X-Content-Type-Options','nosniff');
  res.setHeader('X-Frame-Options','DENY');
  try {
    const url = new URL(req.url,'https://local.invalid');
    const path = url.searchParams.get('route') || url.pathname;
    const method = req.method, sql = database();
    if (method === 'GET') {
      if (path === '/health') { await sql`SELECT 1`; return json(res,200,{ok:true,deployment:'cloud',database:'vercel-postgres',model_ready:false}); }
      if (path === '/api/session') return json(res,200,{authenticated:await authenticated(req)});
      if (['/api/live','/api/latest'].includes(path)) return json(res,200,await live());
      if (path === '/api/foods') return json(res,200,{foods:await sql`SELECT id,food,calorie_per_gram,note FROM nt_foods ORDER BY food`});
      if (path === '/api/meals') {
        const rows = await sql`SELECT id,food,weight_g,calories,eaten_at,source,created_at,updated_at,(image_url IS NOT NULL) AS has_image FROM nt_meals ORDER BY eaten_at DESC,id DESC`;
        const meals = rows.map(({has_image,...m})=>({...m,eaten_at:malaysiaTime(m.eaten_at),image_url:has_image ? `/api/meals/${m.id}/image` : null}));
        return json(res,200,{meals});
      }
      if (path === '/latest.jpg') return await serveImage(res,(await sql`SELECT latest_image FROM nt_live WHERE id=1`)[0]?.latest_image);
      const match = path.match(/^\/api\/meals\/(\d+)\/image$/);
      if (match) return await serveImage(res,(await sql`SELECT image_url FROM nt_meals WHERE id=${Number(match[1])}`)[0]?.image_url);
      throw problem(404,'Tidak ditemui');
    }
    if (!['POST','PUT'].includes(method)) throw problem(405,'Kaedah tidak dibenarkan');
    if (path.startsWith('/api/device/')) {
      const expected = process.env.NUTRITRACK_DEVICE_TOKEN;
      if (method !== 'POST' || !expected || !equal(req.headers.authorization || '',`Bearer ${expected}`)) throw problem(401,'Peranti tidak dibenarkan');
      const data = await body(req);
      if (path === '/api/device/sync') return json(res,200,await syncDevice(data));
      if (path === '/api/device/meal') return json(res,200,{ok:true,id:await saveMeal(data,null,true)});
      throw problem(404,'Tidak ditemui');
    }
    const origin = req.headers.origin, host = req.headers.host;
    if (origin && origin !== `https://${host}` && origin !== `http://${host}`) throw problem(403,'Origin tidak dibenarkan');
    if (path === '/api/login' && method === 'POST') {
      const data = await body(req);
      if (typeof data.password !== 'string' || data.password.length > 1024) throw problem(400,'Kata laluan tidak sah');
      const attempts = await sql`INSERT INTO nt_attempts(id,attempts,started_at) VALUES('admin',1,now()) ON CONFLICT(id) DO UPDATE SET
        attempts=CASE WHEN nt_attempts.started_at < now()-interval '60 seconds' THEN 1 ELSE least(nt_attempts.attempts+1,1000000) END,
        started_at=CASE WHEN nt_attempts.started_at < now()-interval '60 seconds' THEN now() ELSE nt_attempts.started_at END RETURNING attempts`;
      if (attempts[0].attempts > 5) throw problem(429,'Terlalu banyak percubaan. Tunggu 60 saat.');
      const credentials = (await sql`SELECT salt,password_hash FROM nt_credentials WHERE id=1`)[0];
      if (!credentials) throw problem(503,'Kata laluan pentadbir belum ditetapkan');
      const candidate = pbkdf2Sync(data.password,Buffer.from(credentials.salt,'hex'),200000,32,'sha256').toString('hex');
      if (!equal(candidate,credentials.password_hash)) throw problem(401,'Kata laluan salah');
      const token = randomBytes(32).toString('base64url');
      await sql.transaction([
        sql`INSERT INTO nt_sessions(token_hash) VALUES(${digest(token)})`,
        sql`DELETE FROM nt_attempts WHERE id='admin'`
      ]);
      return json(res,200,{ok:true},{'Set-Cookie':`nutrition_session=${token}; HttpOnly; Secure; SameSite=Strict; Path=/`});
    }
    if (!await authenticated(req)) throw problem(401,'Masukkan kata laluan pentadbir dahulu');
    const data = await body(req);
    if (path === '/api/logout' && method === 'POST') {
      await sql`DELETE FROM nt_sessions WHERE token_hash=${digest(cookieToken(req.headers.cookie))}`;
      return json(res,200,{ok:true},{'Set-Cookie':'nutrition_session=; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=0'});
    }
    if (['/api/tare','/api/capture'].includes(path) && method === 'POST') {
      if (!(await live()).bridge_online) throw problem(503,'Laptop penghubung luar talian. Hidupkan server laptop dahulu.');
      const action = path.split('/').pop();
      const rows = await sql`INSERT INTO nt_commands(action) VALUES(${action}) RETURNING id`;
      return json(res,202,{ok:true,queued:true,command_id:rows[0].id,message:'Arahan dihantar ke laptop. Menunggu jawapan peranti.'});
    }
    const match = path.match(/^\/api\/(foods|meals)(?:\/(\d+))?$/);
    if (!match || (method === 'POST' && match[2]) || (method === 'PUT' && !match[2])) throw problem(404,'Tidak ditemui');
    const id = match[2] ? Number(match[2]) : null;
    if (match[1] === 'meals') return json(res,id ? 200 : 201,{ok:true,id:await saveMeal(data,id)});
    const food = text(data.food,'Jenis makanan'), rate = number(data.calories_per_100g,'Kalori/100g',10000)/100;
    const note = data.note ?? '';
    if (typeof note !== 'string' || note.length > 500) throw problem(400,'Nota maksimum 500 aksara');
    const rows = id ? await sql`UPDATE nt_foods SET food=${food},calorie_per_gram=${rate},note=${note} WHERE id=${id} RETURNING id`
      : await sql`INSERT INTO nt_foods(food,calorie_per_gram,note) VALUES(${food},${rate},${note}) RETURNING id`;
    if (!rows.length) throw problem(404,'Makanan tidak ditemui');
    return json(res,id ? 200 : 201,{ok:true});
  } catch (error) {
    if (res.headersSent) { res.destroy(); return; }
    if (error.code === '23505') return json(res,409,{error:'Nama makanan sudah digunakan'});
    if (error.status) return json(res,error.status,{error:error.message});
    console.error('Cloud request failed',error.code || error.name);
    return json(res,503,{error:'Sambungan cloud belum tersedia. Cuba semula sebentar lagi.'});
  }
}
