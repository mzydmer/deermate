function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

export default {
  apiVersion: 1,
  module: "deermate-tooling",
  icon: "file-text",
  conversationActions(_t, locale) {
    const zh = locale === "zh-CN";
    return {
      label: zh ? "会话关联" : "Session binding",
      icon: "file-text",
      actions: [{
        id: "session-binding",
        label: zh ? "查看执行器会话" : "View executor session",
        icon: "file-text",
        available: settings => settings.enabled === true,
        async execute(context, services) {
          const result = await services.callBackend("session_binding", {thread_id: context.thread.thread_id});
          services.showMessage(result.bound
            ? `${result.title ?? ""} · ${result.executor} · ${zh ? "第" : "Round "}${result.round}${zh ? "轮" : ""}\n${result.native_session ?? (zh ? "等待原生会话确认" : "Native session not yet confirmed")} · ${result.status}`
            : (zh ? "此对话尚未绑定执行器会话。首次派单后建立关联。" : "No executor session is bound. The first coding request creates the association."));
        }
      }]
    };
  },
  surfaces: [{
    id: "tools",
    slot: "page",
    title: "Tools & connections",
    navigation: { label: "Tools & connections", labelZh: "工具与连接", icon: "file-text" },
    mount(root, context) {
      let disposed = false;
      const zh = context.locale === "zh-CN";
      const text = (cn, en) => zh ? cn : en;
      const page = element("div", undefined, "dm-tools-page");
      const style = element("style");
      style.textContent = `
        .dm-tools-page{font-family:var(--dm-font-sans);color:var(--dm-foreground);font-size:14px;line-height:1.6}
        .dm-tools-page h2{font-size:16px;font-weight:600;margin:28px 0 12px}
        .dm-tools-page p{margin:6px 0 16px;color:var(--dm-muted)}
        .dm-tools-page button,.dm-tools-page a{border:1px solid var(--dm-border);background:var(--dm-background);color:var(--dm-foreground);border-radius:var(--dm-radius-sm);padding:7px 12px;font-size:14px;cursor:pointer;text-decoration:none;display:inline-block}
        .dm-tools-page button:disabled{opacity:.5;cursor:wait}
        .dm-tools-page :focus-visible{outline:2px solid var(--dm-focus);outline-offset:3px}
        .dm-tools-page .row{border-top:1px solid var(--dm-border);padding:16px 0;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}
        .dm-tools-page .meta{font-size:12px;color:var(--dm-muted);overflow-wrap:anywhere}
        .dm-tools-page .result{flex-basis:100%;white-space:pre-wrap;overflow-wrap:anywhere;font-family:var(--dm-font-mono);font-size:12px}
        .dm-tools-page .note{padding:16px;border:1px solid var(--dm-border);background:var(--dm-surface);border-radius:var(--dm-radius-md);margin-top:24px}
      `;
      page.append(style, element("p", text(
        "查看实际加载的工具，检查已保存的数据连接。仅管理员可使用此检查页。",
        "Inspect loaded tools and saved data connections. Administrator access is required."
      )));
      const refresh = element("button", text("刷新状态", "Refresh status"));
      refresh.type = "button";
      const content = element("div");
      const status = element("p");
      status.setAttribute("role", "status");
      status.setAttribute("aria-live", "polite");
      page.append(refresh, status, content);
      const note = element("div", undefined, "note");
      note.append(element("strong", text("如何使用", "How to use")), element("p", text(
        "在聊天中直接说：搜索 DeerFlow 的公开资料，读取官网并给出来源。搜索词会发给搜索服务，网页地址会发给 Jina Reader；请勿放入私人资料或密钥。",
        "In chat, ask: Search for public information about DeerFlow, read its website and cite sources. Search queries go to search providers and page URLs to Jina Reader. Do not include private data or keys."
      )), element("p", text(
        "GitHub、Notion、SQL 数据库需要先在能力中心添加对应 MCP 服务和授权。这里仅执行连接初始化和工具发现，不读取业务数据、不调用工具。测试成功也不代表拥有所有数据权限；新增工具请在下一次聊天消息中使用。",
        "GitHub, Notion and SQL need an MCP service and authorization in Capability center. Tests only initialize the connection and discover tools; they do not read business data or invoke tools. Discovery does not prove data permissions. Use newly added tools in your next chat message."
      )));
      const link = element("a", text("打开能力中心，配置数据连接", "Configure connections in Capability center"));
      link.href = "/workspace/capabilities";
      note.append(link);
      page.append(note);
      root.append(page);
      const alive = () => !disposed && !context.signal.aborted;
      async function load() {
        refresh.disabled = true;
        status.textContent = text("正在读取运行时状态…", "Reading runtime status…");
        try {
          const data = await context.callBackend("inventory", {});
          if (!alive()) return;
          content.replaceChildren(element("h2", text("当前原生工具", "Configured native tools")));
          for (const tool of data.native) {
            const row = element("div", undefined, "row");
            row.append(element("strong", tool.name), element("span", tool.status === "loaded" ? text("已加载", "Loaded") : text("加载失败", "Unavailable"), "meta"));
            content.append(row);
          }
          if (!data.native.length) content.append(element("p", text("尚未配置原生工具。", "No native tools configured.")));
          content.append(element("h2", text("MCP 数据连接", "MCP connections")), element("p", text("已配置与可连接是两个独立状态。", "Saved configuration and successful discovery are separate states.")));
          if (!data.connections.length) content.append(element("p", text("尚未配置数据连接，可在能力中心添加。", "No connections saved. Add one in Capability center.")));
          for (const connection of data.connections) {
            const row = element("div", undefined, "row");
            const label = element("div");
            label.append(element("strong", connection.name), element("div", `${connection.scope === "personal" ? text("个人", "Personal") : text("平台", "Platform")} · ${connection.enabled ? text("已配置，尚未测试", "Configured, not tested") : text("已停用", "Disabled")}`, "meta"));
            const button = element("button", text("测试连接", "Test connection"));
            button.type = "button";
            button.disabled = !connection.enabled;
            button.setAttribute("aria-label", `${text("测试连接", "Test connection")} ${connection.name}`);
            const result = element("div", undefined, "result");
            result.setAttribute("role", "status");
            button.onclick = async () => {
              button.disabled = true;
              result.textContent = text("正在发现工具，最多等待 20 秒…", "Discovering tools; up to 20 seconds…");
              try {
                const response = await context.callBackend("discover", {scope: connection.scope, name: connection.name});
                if (!alive() || !row.isConnected) return;
                label.querySelector(".meta").textContent = `${connection.scope === "personal" ? text("个人", "Personal") : text("平台", "Platform")} · ${response.status === "discovered" ? text("本次已发现工具", "Tools discovered this check") : text("本次检查未通过", "Check not confirmed")}`;
                const messages = {
                  discovered: text(`连接成功 · ${response.total} 个工具`, `Connected · ${response.total} tools`),
                  disabled: text("连接已停用，请刷新。", "Connection disabled. Refresh status."),
                  not_configured: text("连接已移除，请刷新。", "Connection removed. Refresh status."),
                  timeout: text("连接超时，请检查服务是否运行。", "Timed out. Check the service."),
                  busy: text("已有连接检查正在进行，请稍后再试。", "Another connection check is in progress. Try again shortly."),
                  unavailable: text("连接失败，请检查服务、授权和配置。", "Unavailable. Check service, authorization and configuration.")
                };
                result.textContent = (messages[response.status] ?? text("无法确认连接状态。", "Connection could not be confirmed.")) + (response.tools?.length ? `\n${response.tools.join(" · ")}` : "");
              } catch {
                if (alive()) result.textContent = text("无法完成检查，请确认管理员登录和服务状态。", "Check failed. Verify administrator login and runtime status.");
              } finally { if (alive()) button.disabled = false; }
            };
            row.append(label, button, result);
            content.append(row);
          }
          status.textContent = text("已读取配置；工具是否执行成功以聊天中的实际结果为准。", "Configuration loaded. Actual execution is verified by chat tool results.");
        } catch {
          if (alive()) status.textContent = text("无法读取状态，请确认管理员登录、扩展和服务状态。", "Status unavailable. Check administrator login, extension and runtime.");
        } finally { if (alive()) refresh.disabled = false; }
      }
      refresh.onclick = load;
      void load();
      return { dispose() { disposed = true; page.remove(); } };
    }
  }]
};
