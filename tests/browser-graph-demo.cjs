// Run against an isolated seeded server. Example: TEST_BASE_URL + TEST_PASSWORD + PLAYWRIGHT_MODULE.
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:18876';
const password = process.env.TEST_PASSWORD;
if (!password) throw new Error('Set TEST_PASSWORD for the isolated test account');
(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
  const errors = [], writes = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => { if (/\/api\/v1\/courses\//.test(r.url()) && r.method() !== 'GET') writes.push(r.url()); });
  async function scenario(name) {
    await page.locator('.demo-controls .el-select').first().click();
    await page.getByRole('option', { name, exact: true }).click();
    await page.getByRole('button', { name: '演示推荐路径', exact: true }).click();
  }
  try {
    await page.goto(base + '/#/login');
    await page.getByPlaceholder('请输入用户名').fill('student01');
    await page.getByPlaceholder('请输入密码').fill(password);
    await page.getByRole('button', { name: '登录 →', exact: true }).click();
    await page.waitForURL('**/#/courses');
    const cid = (await (await page.request.get(base + '/api/v1/courses')).json()).items[0].id;
    await page.goto(base + `/#/courses/${cid}`);
    await page.locator('.work-nav').getByRole('link', { name: '知识图谱（演示）' }).click();
    await page.getByRole('heading', { name: '知识图谱 演示数据' }).waitFor();
    assert.equal(await page.locator('.demo-node').count(), 17);
    await page.getByRole('button', { name: '演示推荐路径', exact: true }).click();
    assert.equal(await page.locator('.demo-route li').count(), 2);
    await scenario('初学者');
    assert.equal(await page.locator('.demo-route li').count(), 4);
    await scenario('大部分已掌握');
    assert.equal(await page.locator('.demo-route li').count(), 1);
    await page.getByRole('button', { name: '重置演示', exact: true }).click();
    await page.getByRole('textbox', { name: '搜索图谱知识点' }).fill('边界值分析');
    assert.equal(await page.locator('.demo-node').count(), 1);
    await page.getByRole('textbox', { name: '搜索图谱知识点' }).fill('不存在的知识点');
    await page.getByText('没有匹配的演示知识点，请调整搜索或章节').waitFor();
    await page.getByRole('textbox', { name: '搜索图谱知识点' }).fill('');
    await page.locator('.demo-controls .el-select').nth(1).click();
    await page.getByRole('option', { name: '软件测试', exact: true }).click();
    assert.equal(await page.locator('.demo-node').count(), 6);
    await page.locator('.demo-node').filter({ hasText: '边界值分析' }).click();
    await page.getByRole('button', { name: '体验示例练习', exact: true }).click();
    await page.locator('.demo-question .el-radio').filter({ hasText: '7、8、9、19、20、21' }).click();
    await page.getByRole('button', { name: '查看解析', exact: true }).click();
    await page.getByText(/回答正确。该组覆盖/).waitFor();
    assert.match(await page.locator('.demo-detail').innerText(), /30%/);
    await page.getByRole('button', { name: '放大图谱', exact: true }).click();
    assert.equal(await page.locator('.zoom-value').innerText(), '90%');
    await page.reload();
    await page.locator('.demo-node').first().waitFor();
    assert.equal(await page.locator('.demo-node').count(), 17);
    await page.getByRole('button', { name: '演示推荐路径', exact: true }).click();
    assert.equal(await page.locator('.demo-route li').count(), 2);
    await page.screenshot({ path: '.local/graph-demo-desktop.png', fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'mobile page must not overflow');
    await page.screenshot({ path: '.local/graph-demo-mobile.png', fullPage: true });
    assert.deepEqual(writes, []);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ nodes: 17, scenarios: true, path_highlights: true, search_and_chapter: true, sample_exercise: true, refresh_resets: true, mobile: true, no_course_writes: true, no_script_errors: true }));
  } catch (error) { await page.screenshot({ path: '.local/graph-demo-failure.png', fullPage: true }); throw error; }
  finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
