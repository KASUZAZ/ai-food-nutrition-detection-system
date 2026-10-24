import { readFile } from 'node:fs/promises';
import { neon } from '@neondatabase/serverless';

const sql = neon(process.env.DATABASE_URL_UNPOOLED || process.env.DATABASE_URL);
const schema = await readFile(new URL('../database/schema.sql',import.meta.url),'utf8');
for (const statement of schema.split(';').map(s=>s.trim()).filter(Boolean)) await sql.query(statement,[]);
const credentialsPath = process.argv[2] || 'data/cloud-credentials.local.json';
const credentials = JSON.parse(await readFile(credentialsPath,'utf8'));
await sql`INSERT INTO nt_credentials(id,salt,password_hash) VALUES(1,${credentials.salt},${credentials.password_hash})
  ON CONFLICT(id) DO NOTHING`;
const csv = (await readFile(new URL('../data/food_calories.csv',import.meta.url),'utf8')).replace(/^\uFEFF/,'').trim().split(/\r?\n/).slice(1);
for (const line of csv) {
  const [food,rate,...note] = line.split(',');
  await sql`INSERT INTO nt_foods(food,calorie_per_gram,note) VALUES(${food},${Number(rate)},${note.join(',')}) ON CONFLICT DO NOTHING`;
}
console.log('Cloud database ready. Food classes:',(await sql`SELECT count(*)::int AS count FROM nt_foods`)[0].count);
