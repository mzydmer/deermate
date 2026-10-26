"""Render a self-contained replay from captured verifier checks, not mock events."""
# ruff: noqa: E501 -- Static HTML/CSS/JS template retains readable source lines.

import json
from pathlib import Path

TEMPLATE = """<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>DeerMate · Gateway __TRANSPORT__ 演示回放</title>
<style>
:root{color-scheme:dark;font:16px/1.65 system-ui,sans-serif;background:#101b20;color:#e9f2ee}
body{margin:0 auto;max-width:1120px;padding:40px 24px}h1{font-size:clamp(26px,4vw,40px);margin:4px 0 16px}
.muted{color:#a8bdb5}.tag{color:#a2f1c7;letter-spacing:.12em;font-size:13px}.notice{background:#27332a;border-left:3px solid #e2c181;padding:12px 18px}
.flow{display:flex;gap:8px;flex-wrap:wrap;margin:24px 0}.flow span{padding:10px 15px;border:1px solid #3d5a50;border-radius:8px;background:#172b25}
.controls{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:24px 0}button,select{background:#1c3430;color:#e9f2ee;border:1px solid #527c6c;border-radius:7px;padding:8px 14px;font:inherit;cursor:pointer}
progress{width:180px;accent-color:#9df0c2}.grid{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:24px}.panel{background:#16252a;border:1px solid #30494b;border-radius:12px;padding:20px;min-width:0}
h2{font-size:18px;margin:0 0 12px}.events{max-height:490px;overflow:auto;padding:0;margin:0;list-style:none}.event{padding:10px 0;border-bottom:1px solid #2e4146}.time{font:12px ui-monospace,monospace;color:#b8c9bf;margin-right:8px}.ok{color:#9df0c2}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#0e191e;padding:14px;border-radius:7px;font:12px/1.6 ui-monospace,monospace}.metric{font-size:28px;font-weight:700;color:#9df0c2}.small{font-size:12px}footer{margin-top:24px;color:#a8bdb5;font-size:13px}@media(max-width:780px){.grid{grid-template-columns:1fr}body{padding:24px 16px}}
</style>
<body><div class="tag">DEERMATE · CAPTURED BACKEND DEMO</div>
<h1>Gateway → MCP → __TRANSPORT__ → Worker</h1>
<p class="muted">实际进程与协议执行的事件回放。点击播放或单步查看已捕获的验收结果。</p>
<p class="notice">__SCOPE__ · 离线 Codex 协议 fixture · 未配置聊天模型。此回放不是产品工作台，也不是双机、NAT 或真实模型演示。</p>
<div class="flow"><span>DeerFlow Gateway / SQLite</span><span>→ MCP</span><span>→ __TRANSPORT__</span><span>→ 独立 Worker</span></div>
<div class="controls"><button id="play">播放</button><button id="next">下一步</button><button id="reset">重置</button><label>速度 <select id="speed"><option value="1">1×</option><option value="4" selected>4×</option><option value="10">10×</option></select></label><progress id="progress" value="0"></progress><span id="clock" class="muted small"></span></div>
<div class="grid"><section class="panel"><h2>捕获的事件</h2><ol id="events" class="events"></ol></section>
<section class="panel"><h2>执行证据</h2><div><span id="count" class="metric">0</span> / <span id="total"></span> 项通过</div>
<p id="result" class="muted">等待回放</p><pre id="detail">选择播放或下一步</pre><h2>实际 fixture diff</h2><pre id="patch"></pre><p id="validation" class="small muted"></p></section></div>
<footer id="provenance"></footer><script id="receipt" type="application/json">__RECEIPT__</script>
<script>
const receipt=JSON.parse(document.getElementById('receipt').textContent),checks=receipt.checks;
const el=id=>document.getElementById(id);let index=0,timer=null;
const labels={sql_submission_and_hidden_control_tools:'SQL 保存任务；仅提交工具对秘书可见',worker_survives_gateway_stop:'Gateway 停止后 Worker 继续执行',gateway_process_restart_preserves_identity:'新 Gateway 进程接续相同任务与会话',http_cancel_confirmed_in_sql_and_worker:'原始取消接口取得 SQL / Worker 确认',background_validation_completed:'修复完成，独立验证通过',background_validation_failed:'验证失败仍报告失败',outage_is_retryable_not_terminal:'Worker 失联表现为跟踪异常',reconnect_requires_explicit_recovery:'Worker 恢复后要求显式处理',no_replayed_sessions_or_turns:'没有重放原生会话或轮次',source_checkout_unchanged:'原始项目工作区保持不变',pinned_upstream_unchanged:'固定上游源码保持不变',ssh_instance_bound_path:'实例绑定与 SSH 转发均已确认',ssh_outage_preserves_running_worker:'仅 SSH 断线，Worker 仍在运行',ssh_reconnect_preserves_identity:'恢复 SSH 后接续原任务',ssh_revocation_does_not_claim_cancelled:'撤权后不伪造任务已取消',ssh_grant_restore_completes_requested_cancel:'恢复授权后完成先前明确请求的取消',ssh_fixture_enforced_forwarding:'SSH 仅使用获准转发，未请求 shell'};
el('total').textContent=checks.length;el('progress').max=checks.length;
el('patch').textContent=receipt.demo_artifacts?.patch_excerpt||'本次收据没有保存 diff 片段';
el('validation').textContent=receipt.demo_artifacts?.validation_excerpt||'';
el('provenance').textContent=`捕获时间 ${receipt.started_at} · 上游 ${receipt.upstream_commit.slice(0,12)} · verifier ${receipt.verifier_sha256.slice(0,12)} · transport ${receipt.transport||'local'}`;
function pause(){if(timer)clearTimeout(timer);timer=null;el('play').textContent='播放'}
function step(){if(index>=checks.length){pause();return}const c=checks[index++],item=document.createElement('li'),stamp=document.createElement('span'),text=document.createElement('span');item.className='event';stamp.className='time';stamp.textContent=`+${Number(c.elapsed_seconds||0).toFixed(1)}s`;text.className='ok';text.textContent='✓ '+(labels[c.name]||c.name);item.append(stamp,text);el('events').append(item);item.scrollIntoView({block:'nearest'});el('count').textContent=index;el('progress').value=index;el('clock').textContent=`实际时间 +${Number(c.elapsed_seconds||0).toFixed(1)}s`;el('detail').textContent=JSON.stringify(c,null,2);el('result').textContent=index===checks.length?'全部已捕获检查通过；范围限制见上方说明':'按真实事件顺序回放';if(index>=checks.length)pause()}
function tick(){step();if(index<checks.length){const before=checks[Math.max(0,index-1)].elapsed_seconds||0,after=checks[index].elapsed_seconds||before;timer=setTimeout(tick,Math.max(200,Math.min(5000,(after-before)*1000/Number(el('speed').value))));el('play').textContent='暂停'}}
el('play').onclick=()=>{if(timer)pause();else tick()};el('next').onclick=()=>{pause();step()};el('reset').onclick=()=>{pause();index=0;el('events').replaceChildren();el('count').textContent=0;el('progress').value=0;el('clock').textContent='';el('result').textContent='等待回放';el('detail').textContent='选择播放或下一步'};
</script></body></html>"""


def render_replay(receipt: dict, destination: Path):
    if not receipt.get("passed") or not receipt.get("checks"):
        raise ValueError("Only a completed, passing receipt can be replayed")
    encoded = json.dumps(receipt, ensure_ascii=False).replace("<", "\\u003c")
    destination.parent.mkdir(parents=True, exist_ok=True)
    ssh = receipt.get("transport") == "ssh"
    template = TEMPLATE.replace("__TRANSPORT__", "SSH" if ssh else "HTTP")
    template = template.replace(
        "__SCOPE__", "同机 loopback SSH · 临时密钥" if ssh else "同机 loopback HTTP"
    )
    destination.write_text(template.replace("__RECEIPT__", encoded))
