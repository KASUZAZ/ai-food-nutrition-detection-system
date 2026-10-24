import test from 'node:test';
import assert from 'node:assert/strict';
import sharp from 'sharp';
import { number,text,malaysiaTime,mealValues,cookieToken,imageBuffer } from '../api/index.mjs';

test('numeric validation rejects nonfinite, booleans and negative calories',()=>{
  for(const value of [NaN,Infinity,-1,true,'150']) assert.throws(()=>number(value,'Berat'));
  assert.equal(number(150,'Berat'),150);
  assert.throws(()=>mealValues({food:'Rice',weight_g:0,calories:0,eaten_at:'2026-10-24T12:00:00+08:00'}));
});
test('Malaysia timestamps remain correct across midnight and database Date values',()=>{
  assert.equal(malaysiaTime('2026-10-23T16:56:00Z'),'2026-10-24T00:56:00+08:00');
  assert.equal(malaysiaTime(new Date('2026-10-23T16:56:00Z')),'2026-10-24T00:56:00+08:00');
  assert.equal(malaysiaTime('2026-10-24T12:00:00'),'2026-10-24T12:00:00+08:00');
  assert.throws(()=>malaysiaTime('invalid'));
});
test('names and cookies validate without interpreting HTML',()=>{
  assert.throws(()=>text('\n','Makanan'));
  assert.equal(text(' Rice ','Makanan'),'Rice');
  assert.equal(cookieToken('other=x; nutrition_session=abc_def'),'abc_def');
  assert.equal(cookieToken('nutrition_session_fake=abc'),'');
});
test('images are validated and normalized to JPEG',async()=>{
  await assert.rejects(()=>imageBuffer('not an image'));
  const png=await sharp({create:{width:20,height:20,channels:3,background:'#669944'}}).png().toBuffer();
  const jpeg=await imageBuffer(png.toString('base64'));
  assert.equal(jpeg[0],0xff); assert.equal(jpeg[1],0xd8);
});
