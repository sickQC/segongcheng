const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:8000';
(async () => {
 const password = fs.readFileSync('.env','utf8').split(/\r?\n/).find(x=>x.startsWith('SEED_PASSWORD=')).slice('SEED_PASSWORD='.length);
 const browser = await chromium.launch({headless:true,channel:'msedge'});
 const page = await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[]; page.on('pageerror',e=>errors.push(e.message));
 const writes=[]; page.on('request',r=>{if(r.method()==='POST' && /\/courses\//.test(r.url())) writes.push(r.url())});
 try {
  await page.goto(base);
  await page.getByPlaceholder('请输入用户名').fill('teacher');
  await page.getByPlaceholder('请输入密码').fill(password);
  await page.getByRole('button',{name:'登录 →',exact:true}).click();
  await page.waitForURL('**/#/courses');
  const response=await page.request.get(base+'/api/v1/courses');
  const cid=(await response.json()).items[0].id;
  for(const [suffix,title] of [['learn','资源学习'],['quiz','课程测验'],['report','个人学习报告'],['dashboard','教师学情看板']]) {
   const route=suffix==='dashboard'?`/teacher/courses/${cid}/dashboard`:`/courses/${cid}/${suffix}`;
   await page.goto(base+'/#'+route);
   await page.getByRole('heading',{name:title,exact:true}).waitFor();
   if(suffix==='learn') await page.getByRole('heading',{name:/^全部课程资料/}).waitFor();
   else await page.getByText('此业务尚未实现；可手动开启界面预览查看布局。',{exact:true}).waitFor();
   await page.locator('.el-switch').click();
   await page.getByText(/界面样例：所有内容仅供预览/).waitFor();
   if(suffix==='learn') {
    await page.getByRole('textbox',{name:'提问内容'}).fill('什么是功能需求？');
    await page.getByRole('button',{name:'发送问题',exact:true}).click();
    await page.getByText(/这是界面样例回复/).waitFor();
    await page.getByRole('button',{name:/需求规格说明（样例）/}).click();
    await page.getByRole('spinbutton',{name:'文档页码'}).waitFor();
   }
   if(suffix==='quiz') {
    await page.getByRole('button',{name:'开始测验',exact:true}).click();
    await page.getByText('用户可以导出报告',{exact:true}).click();
    await page.getByText('访谈',{exact:true}).click();
    await page.getByText('原型评审',{exact:true}).click();
    await page.getByText('正确',{exact:true}).click();
    await page.getByRole('textbox',{name:'填空答案'}).fill('用例');
    await page.getByRole('button',{name:'提交答卷',exact:true}).click();
    await page.getByText('预览模式仅检查表单，不执行判分或保存。真实提交接口尚未实现。',{exact:true}).waitFor();
    await page.getByRole('button',{name:'查看结果布局样例',exact:true}).click();
    await page.getByRole('heading',{name:'结果布局样例 · 75 / 100'}).waitFor();
   }
   if(suffix==='report') {
    for(const name of ['学习画像','推荐路径','学习记录','错题本','诊断与证据']) await page.getByRole('tab',{name,exact:true}).click();
    await page.getByRole('textbox',{name:'学习提问'}).fill('如何巩固？');
    await page.getByRole('button',{name:'发送问题',exact:true}).click();
    await page.getByText('此处展示提问回复。界面预览不调用模型，也不更新画像。',{exact:true}).waitFor();
   }
   if(suffix==='dashboard') {
    await page.getByRole('button',{name:'样例学生甲',exact:true}).click();
    await page.getByRole('button',{name:'手动触发诊断',exact:true}).click();
    await page.getByText('界面预览不创建诊断任务。',{exact:true}).waitFor();
    await page.keyboard.press('Escape');
   }
   await page.screenshot({path:`.local/workspace-${suffix}.png`,fullPage:true});
   await page.setViewportSize({width:390,height:844});
   await page.screenshot({path:`.local/workspace-${suffix}-mobile.png`,fullPage:true});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`${suffix} mobile overflow`);
   await page.setViewportSize({width:1440,height:1000});
   await page.locator('.el-switch').click();
   if(suffix==='learn') await page.getByRole('heading',{name:/^全部课程资料/}).waitFor();
   else await page.getByText('此业务尚未实现；可手动开启界面预览查看布局。',{exact:true}).waitFor();
  }
  assert.deepEqual(writes,[], 'preview must not POST business data');
  await page.getByRole('button',{name:'退出登录',exact:true}).click();
  await page.getByPlaceholder('请输入用户名').fill('student01');
  await page.getByPlaceholder('请输入密码').fill(password);
  await page.getByRole('button',{name:'登录 →',exact:true}).click();
  await page.waitForURL('**/#/courses');
  await page.goto(base+`/#/courses/${cid}/report`);
  await page.getByText('分章节学习历史',{exact:true}).waitFor();
  await page.getByText(/模拟学习历史，不是实际测验成绩/).waitFor();
  await page.getByText('错误率较高',{exact:true}).waitFor();
  await page.goto(base+`/#/teacher/courses/${cid}/dashboard`);
  await page.waitForURL('**/#/courses');
  await page.getByRole('button',{name:'退出登录',exact:true}).click();
  assert.deepEqual(errors,[]);
  console.log('PASS: course KB, synthetic student history, remaining 501 pages, preview interactions, mobile overflow and route guard');
 } catch(e) { await page.screenshot({path:'.local/workspace-error.png',fullPage:true}); throw e; }
 finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1});

