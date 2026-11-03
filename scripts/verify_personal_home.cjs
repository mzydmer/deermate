/* Synthetic loopback acceptance over the real Go/Gateway/home UI. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { chromium } = require(process.env.DEERMATE_PLAYWRIGHT_MODULE ?? "playwright-core");

async function main() {
  const base = process.env.DEERMATE_URL;
  const origin = new URL(base);
  assert(["localhost", "127.0.0.1"].includes(origin.hostname));
  assert(!origin.username && !origin.password);
  const output = process.env.DEERMATE_OUTPUT;
  assert(output && process.env.DEERMATE_OWNER_FILE);
  const owner = JSON.parse(fs.readFileSync(process.env.DEERMATE_OWNER_FILE, "utf8"));
  fs.mkdirSync(output, { recursive: true, mode: 0o700 });
  const checks = [];
  const errors = [];
  const browser = await chromium.launch({headless:true, executablePath:process.env.DEERMATE_BROWSER_EXECUTABLE});
  let page;
  try {
    const context = await browser.newContext({viewport:{width:1440,height:1080},locale:"zh-CN"});
    page = await context.newPage();
    page.on("pageerror", e=>errors.push(e.message));
    if ((await (await page.request.get(base+"/api/v1/auth/setup-status")).json()).needs_setup) {
      assert.equal((await page.request.post(base+"/api/v1/auth/initialize",{data:owner})).status(),201);
    }
    await context.clearCookies();
    await context.addCookies([{name:"locale",value:"zh-CN",url:base}]);
    await page.goto(base+"/login");
    await page.locator("#email").fill(owner.email);
    await page.locator("#password").fill(owner.password);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL(u=>u.pathname==="/workspace",{timeout:45000});
    const catalog = await (await page.request.get(base+"/api/models")).json();
    assert.deepEqual(catalog.models.map(model=>model.name),["capture-fixture"]);
    const home=page.locator(".dm-personal-home");
    const user = await (await page.request.get(base+"/api/v1/auth/me")).json();
    const headers = {"X-CSRF-Token":(await context.cookies()).find(c=>c.name==="csrf_token").value,"X-Expected-User-Id":user.id};
    async function api(method,endpoint,data) {
      const response=await page.request.fetch(base+endpoint,{method,headers,data});
      assert(response.ok(), `${method} ${endpoint}: ${response.status()}`);
      return response.json();
    }
    for (const topic of (await api("GET","/api/me/attention-topics")).items) {
      assert(topic.goal === "完成有记忆的私人秘书首页" || topic.source_state === "unavailable");
      await api("PATCH",`/api/me/attention-topics/${topic.id}`,{action:"remove",expected_revision:topic.revision});
    }
    for (const fact of (await api("GET","/api/me/memories")).items) {
      assert(fact.content === "研究开源私人助手的可用性");
      const op=await api("DELETE",`/api/me/memories/${fact.id}`,{operation_id:crypto.randomUUID(),expected_revision:fact.revision});
      await page.waitForTimeout(200);
      assert.equal((await api("GET",`/api/me/memory-operations/${op.id}`)).status,"completed");
    }
    await page.reload();
    await home.getByText(/今天还没有需要展示的关注/).waitFor();
    checks.push("real_login_empty_home");
    const thread="home-ui-source-"+crypto.randomUUID();
    await api("POST","/api/threads",{thread_id:thread});
    await page.reload();
    await home.locator(".dm-attention-management > summary").click();
    await home.getByLabel("或粘贴历史对话链接").fill(`/workspace/chats/${thread}`);
    await home.getByLabel("你想跟进什么").fill("完成有记忆的私人秘书首页");
    await home.getByRole("button",{name:"关注这个对话",exact:true}).click();
    await home.locator(":scope > .dm-focus-list > li").waitFor();
    assert.equal((await api("GET","/api/me/attention-topics")).items.length,1);
    checks.push("follow_existing_chat_from_link_with_goal");
    await home.getByRole("link",{name:"打开原对话",exact:true}).click();
    await page.waitForURL(u=>u.pathname===`/workspace/chats/${thread}`);
    await page.goto(base+"/workspace");
    await home.locator(".dm-focus-followup > summary").click();
    await home.getByRole("button",{name:"一键只读跟进",exact:true}).click();
    await home.getByText("跟进已完成。",{exact:true}).waitFor({timeout:60000});
    let intents=[];
    // The button can be pressed again, but canonical admission must return the
    // original intent and actual run rather than starting another conversation.
    await home.getByRole("button",{name:"刷新关注",exact:true}).click();
    const followup = home.locator(".dm-focus-followup");
    await followup.waitFor();
    if (!(await followup.evaluate(n=>n.open))) await followup.locator(":scope > summary").click();
    const prepare=page.waitForResponse(r=>r.request().method()==="POST"&&new URL(r.url()).pathname==="/api/me/briefing/actions");
    const [prepared] = await Promise.all([prepare, home.getByRole("button",{name:"一键只读跟进",exact:true}).click()]);
    intents.push(await prepared.json());
    await home.getByText("跟进已完成。",{exact:true}).waitFor();
    const runs=await api("GET",`/api/threads/${thread}/runs`);
    assert.equal(runs.length,1);
    assert.equal(runs[0].status,"success");
    assert.equal(intents[0].run_id,runs[0].run_id);
    checks.push("read_only_followup_and_repeated_click_one_real_fake_run");
    await home.getByRole("link",{name:"查看跟进结果",exact:true}).click();
    await page.waitForURL(u=>u.pathname===`/workspace/chats/${thread}`);
    await page.getByText("Synthetic memory acceptance response.",{exact:false}).first().waitFor();
    checks.push("followup_result_visible_in_original_chat");
    await page.goto(base+"/workspace");
    await page.locator(".dm-memory > summary").click();
    await page.getByLabel("希望我怎么称呼你").fill("首页验收");
    await page.getByLabel("时区",{exact:true}).fill("Asia/Shanghai");
    await page.getByLabel("开启个人记忆",{exact:true}).check();
    await page.getByLabel("根据长期目标推荐新话题",{exact:true}).check();
    await page.getByRole("button",{name:"保存个人设置",exact:true}).click();
    await page.getByRole("heading",{level:1,name:/首页验收/}).waitFor();
    await page.locator(".dm-memory select").selectOption("goal");
    await page.locator("#dm-memory-content").fill("研究开源私人助手的可用性");
    await page.getByRole("button",{name:"保存记忆",exact:true}).click();
    await home.locator(".dm-suggestions").getByText(/研究开源私人助手的可用性/).waitFor();
    await home.getByText("因为你明确保存了这个长期目标。",{exact:true}).waitFor();
    checks.push("explicit_goal_opt_in_creates_explained_suggestion");
    await home.getByRole("button",{name:"开始这个话题",exact:true}).click();
    await home.getByText("跟进已完成。",{exact:true}).waitFor({timeout:60000});
    const href=await home.getByRole("link",{name:"查看跟进结果",exact:true}).getAttribute("href");
    assert(href.startsWith("/workspace/chats/briefing-") && href!==`/workspace/chats/${thread}`);
    const newRuns=await api("GET",`/api/threads/${href.split("/").pop()}/runs`);
    assert.equal(newRuns.length,1);
    const newState=await api("GET",`/api/threads/${href.split("/").pop()}/state`);
    assert(typeof newState.values.title === "string" && newState.values.title.length>0);
    assert(!newState.values.deermate_coding_session?.binding_id);
    assert.equal((await api("GET","/api/me/memories")).items.length,1);
    checks.push("suggestion_creates_one_separate_owned_chat_without_inferred_memory");
    await page.getByLabel("根据长期目标推荐新话题",{exact:true}).uncheck();
    await page.getByRole("button",{name:"保存个人设置",exact:true}).click();
    await home.locator(".dm-suggestions").waitFor({state:"detached"});
    checks.push("turning_suggestions_off_removes_cached_goal");
    await home.locator(".dm-attention-management > summary").click();
    await home.getByRole("button",{name:"暂停关注",exact:true}).click();
    await home.locator(":scope > .dm-focus-list > li").waitFor({state:"detached"});
    await home.getByRole("button",{name:"恢复关注",exact:true}).click();
    await home.locator(":scope > .dm-focus-list > li").waitFor();
    await home.getByRole("button",{name:"今天先不看",exact:true}).click();
    await home.locator(":scope > .dm-focus-list > li").waitFor({state:"detached"});
    await home.getByRole("button",{name:"恢复关注",exact:true}).click();
    await home.locator(":scope > .dm-focus-list > li").waitFor();
    checks.push("pause_resume_today_hide_and_saved_timezone");
    await home.getByRole("button",{name:"标记已读",exact:true}).click();
    assert.equal((await api("GET","/api/me/briefing")).items[0].has_changes,false);
    checks.push("mark_read_uses_current_evidence_revision");
    await page.locator(".dm-memory > summary").click();
    await page.locator(".dm-desk").evaluate(n=>{n.scrollTop=0;});
    await page.screenshot({path:path.join(output,"home-desktop.png"),fullPage:true});
    for(const width of [1280,390]) {
      await page.setViewportSize({width,height:844});
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      if(width===390) {
        const sizes=await home.getByRole("button").evaluateAll(nodes=>nodes.filter(n=>n.getBoundingClientRect().width).map(n=>({height:n.getBoundingClientRect().height,font:parseFloat(getComputedStyle(n).fontSize)})));
        assert(sizes.every(s=>s.height>=44 && s.font>=14),JSON.stringify(sizes));
      }
      await page.screenshot({path:path.join(output,`home-${width}.png`),fullPage:true});
    }
    await page.emulateMedia({colorScheme:"dark",reducedMotion:"reduce"});
    await page.evaluate(()=>{document.documentElement.classList.add("dark");document.documentElement.dataset.theme="dark";});
    const theme=await home.evaluate(n=>getComputedStyle(n).getPropertyValue("--dm-background").trim());
    assert.match(theme,/^#(?:0a0a0a|000|000000)$/i);
    await page.screenshot({path:path.join(output,"home-dark-mobile.png"),fullPage:true});
    checks.push("desktop_laptop_mobile_dark_reduce_motion_no_overflow");
    await page.setViewportSize({width:1440,height:1080});
    await page.route("**/api/me/briefing",route=>route.fulfill({status:503,contentType:"application/json",body:'{"error":"fixture_unavailable"}'}));
    await home.getByRole("button",{name:"刷新关注",exact:true}).click();
    await home.getByText(/关注暂不可用/).waitFor();
    assert.equal(await home.locator(":scope > .dm-focus-list > li").count(),0);
    checks.push("failed_refresh_hides_stale_focus_and_has_recovery");
    await page.unroute("**/api/me/briefing");
    await home.getByRole("button",{name:"刷新关注",exact:true}).click();
    await home.locator(":scope > .dm-focus-list > li").waitFor();
    await api("DELETE",`/api/threads/${thread}`);
    await home.getByRole("button",{name:"刷新关注",exact:true}).click();
    await home.getByText(/部分关注的来源已不可用或已归档/).waitFor();
    assert.equal(await home.locator(":scope > .dm-focus-list > li").count(),0);
    await home.getByText("来源已不可用或已归档",{exact:true}).waitFor();
    await home.getByRole("button",{name:"不再关注",exact:true}).click();
    await home.getByText("来源已不可用或已归档",{exact:true}).waitFor({state:"detached"});
    assert.equal((await api("GET","/api/me/attention-topics")).items.length,0);
    checks.push("deleted_source_hides_old_content_and_can_be_unfollowed");
    await home.getByRole("button",{name:"刷新关注",exact:true}).focus();
    await page.keyboard.press("Enter");
    assert(await home.getByRole("button",{name:"刷新关注",exact:true}).evaluate(n=>n===document.activeElement));
    checks.push("keyboard_refresh_keeps_focus");
    const other={email:`home-browser-${crypto.randomUUID()}@example.com`,password:crypto.randomBytes(24).toString("hex")};
    await api("POST","/api/v1/admin/users",{...other,system_role:"user"});
    await api("POST","/api/v1/auth/logout",{});
    await page.goto(base+"/login");
    await page.locator("#email").fill(other.email);
    await page.locator("#password").fill(other.password);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL(u=>u.pathname==="/workspace");
    await home.getByText(/今天还没有需要展示的关注/).waitFor();
    assert.equal(await home.locator(".dm-home-action, .dm-suggestions").count(),0);
    assert.equal(await page.getByRole("heading",{level:1,name:/首页验收/}).count(),0);
    assert.deepEqual((await (await page.request.get(base+"/api/me/memories")).json()).items,[]);
    checks.push("account_switch_has_no_prior_name_action_or_goal");
    assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(output,"receipt.json"),JSON.stringify({passed:true,checks,synthetic_data_only:true,configured_cloud_models:0,native_tasks:0,actual_fake_model_runs:2,source_sha256:crypto.createHash("sha256").update(fs.readFileSync(__filename)).digest("hex")},null,2)+"\n");
    console.log(JSON.stringify({passed:true,checks:checks.length,actual_fake_model_runs:2}));
    await context.close();
  } catch (error) {
    if (page) await page.screenshot({path:path.join(output,"failure.png"),fullPage:true}).catch(()=>{});
    throw error;
  } finally { await browser.close(); }
}
main().catch(error=>{console.error(error.stack);process.exitCode=1;});
