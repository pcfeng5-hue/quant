const fs=require('fs');
const {chromium}=require('/Users/puchun/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const path=require('path');
const dir=__dirname;
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--disable-background-networking','--disable-component-update','--no-first-run']});
 const page=await browser.newPage({viewport:{width:768,height:1700},colorScheme:'light'});
 const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.route('https://**/*',r=>r.abort());
 await page.route('http://**/*',r=>r.abort());
 await page.setContent(fs.readFileSync(path.join(dir,'preview.html'),'utf8'),{waitUntil:'domcontentloaded'});
 const frame=page.frameLocator('iframe');
 await frame.locator('#aq-detail h3').waitFor();
 const checks={};
 checks.initial_step=await frame.locator('#aq-detail h3').innerText()==='07 质量与历史可得性';
 checks.step_count=await frame.locator('#aq-flow button').count()===17;
 checks.each_step_updates_purpose_and_effect=true;
 for(let i=0;i<17;i++){
   await frame.locator('#aq-flow button').nth(i).click();
   const heading=await frame.locator('#aq-detail h3').innerText();
   const dd=await frame.locator('#aq-detail dd').allTextContents();
   if(!heading.startsWith(String(i+1).padStart(2,'0'))||dd.length!==8||dd.some(s=>!s.trim()))checks.each_step_updates_purpose_and_effect=false;
 }
 await frame.locator('#aq-flow button').nth(6).click();
 const layout=[];
 for(const width of [768,392,352]){
   await page.setViewportSize({width,height:1900});
   for(const tab of ['aq-flow-tab','aq-data-tab','aq-plan-tab']){
     await frame.locator('#'+tab).click();
     const dims=await frame.locator('#ashare-roadmap-oct15').evaluate(el=>({client:el.clientWidth,scroll:el.scrollWidth,body:el.ownerDocument.body.clientWidth,whole:el.ownerDocument.documentElement.scrollWidth}));
     layout.push({outer_width:width,tab,...dims,root_fits:dims.scroll<=dims.client+1,document_fits:dims.whole<=dims.body+1});
   }
 }
 checks.no_root_horizontal_overflow=layout.every(r=>r.root_fits&&r.document_fits);
 checks.data_rows=await frame.locator('#aq-data-rows tr').count()===17;
 checks.week_rows=await frame.locator('#aq-week-rows tr').count()===6;
 checks.timeline_rows=await frame.locator('#aq-timeline .time-row').count()===7;
 checks.tab_interaction=await frame.locator('#aq-plan-panel').isVisible()&&!await frame.locator('#aq-flow-panel').isVisible();
 await page.setViewportSize({width:768,height:1900});
 await frame.locator('#aq-flow-tab').click();
 await frame.locator('#ashare-roadmap-oct15').screenshot({path:path.join(dir,'roadmap-desktop.png')});
 await frame.locator('#aq-plan-tab').click();
 await frame.locator('#ashare-roadmap-oct15').screenshot({path:path.join(dir,'plan-desktop.png')});
 await page.setViewportSize({width:392,height:2500});
 await frame.locator('#aq-flow-tab').click();
 await frame.locator('#ashare-roadmap-oct15').screenshot({path:path.join(dir,'roadmap-mobile.png')});
 checks.no_javascript_exceptions=errors.length===0;
 const result={checked_at:new Date().toISOString(),checks,layout,errors,scope:'New project roadmap visualization only; database browser not opened or previewed.',source_sha256:require('crypto').createHash('sha256').update(fs.readFileSync('/Users/puchun/.codex/visualizations/2026/10/07/01a117ad-aa9c-7e12-a194-47edf9f62817/a-share-project-roadmap.html')).digest('hex')};
 fs.writeFileSync(path.join(dir,'validation.json'),JSON.stringify(result,null,2));
 console.log(JSON.stringify(result,null,2));await browser.close();
 if(Object.values(checks).some(x=>!x))process.exitCode=1;
})().catch(e=>{console.error(e);process.exitCode=1;});
