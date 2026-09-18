// Real browser + local production server. Weather/bus API calls are disabled.
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const assert=require('node:assert/strict');
(async()=>{
 const server=spawn('python',['app_integrated_dhs_gpt_commited.py'],{env:{...process.env,BUSFLOW_OFFLINE:'1',PORT:'5001'},stdio:['ignore','pipe','inherit']});
 let browser;
 try{
  await new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(Error('server startup timeout')),10000);server.stdout.once('data',()=>{clearTimeout(timeout);resolve()});server.once('exit',()=>reject(Error('server exited')))});
  browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1280,height:900}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:5001');
  await page.waitForFunction(()=>document.querySelector('#dataModeBadge_dhs_gpt_commited').textContent.includes('서버 연결'));
  await page.evaluate(()=>startPlan('morning'));
  const future=new Date(Date.now()+7*86400000);
  await page.locator('#planDate').fill(new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul'}).format(future));
  await page.evaluate(()=>{goStations();const r='5003A',s=catalog[r].boarding.at(-1);toggleStation(r,s.id);plan.destination='신논현역';renderDestinations();});
  await page.evaluate(()=>runRecommendation());
  assert.match(await page.locator('#resultContent').innerText(),/선택한 정류장의 기존 자료/);
  assert.match(await page.locator('#resultContent').innerText(),/배차 간격 10.2분/);
  assert.equal(await page.locator('#resultContent .result-label').innerText(),'BEST');
  assert.match(await page.locator('#resultContent').innerText(),/모델 추정 이동시간/);
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  await page.setViewportSize({width:1280,height:900});
  await page.locator('[data-candidate-id="candidate-2"]').click();
  assert.equal(await page.locator('#resultContent .result-label').innerText(),'2위');
  assert.deepEqual(await page.locator('.candidate-switch .alt-label').allTextContents(),['BEST','3위','4위']);
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  await page.evaluate(()=>startPlan('evening'));
  await page.locator('#planDate').fill(new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul'}).format(future));
  await page.evaluate(()=>{goStations();const r='5003B',s=catalog[r].boarding.at(-1);toggleStation(r,s.id);plan.destination=catalog[r].destinations.at(-1).name;renderDestinations();});
  await page.evaluate(()=>runRecommendation());
  assert.match(await page.locator('#resultContent').innerText(),/퇴근은 서울 방향 CSV를 재사용하지 않고/);
  assert.equal(await page.locator('#resultContent .result-label').innerText(),'BEST');
  assert.deepEqual(errors,[]);console.log('PASS: real XLSX + CSV modeled A/B recommendations, real rank clicks, mobile layout; no external API calls');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
