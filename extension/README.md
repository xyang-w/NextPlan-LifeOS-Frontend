# NextPlan Sync

这是 NextPlan 的 Chrome Manifest V3 原型插件，用于把 ChatGPT 对话同步为可确认的计划变更。

## 安装

1. 打开 `chrome://extensions`。
2. 开启「开发者模式」。
3. 选择「加载已解压的扩展程序」。
4. 选择本目录 `extension/`。
5. 打开 ChatGPT 对话，点击插件图标。

插件只会在用户点击按钮后读取当前会话最近 80 条消息，并发送到配置的 LifeOS API。它不会读取 Cookie、密码或后台聊天列表。若 ChatGPT 页面 DOM 发生变化，插件会使用当前 `main` 区域的可见文本作为回退上下文。

## 后端接口约定

```http
POST /api/chat/sync
Content-Type: application/json
```

请求体为：

```json
{
  "source": "chatgpt-extension",
  "conversation": {
    "title": "当前对话标题",
    "url": "https://chatgpt.com/c/...",
    "captured_at": "2026-10-06T00:00:00.000Z",
    "messages": [{"index": 0, "role": "user", "text": "..."}]
  }
}
```

后端应该先解析为待确认变更，再由用户确认后写入项目和任务；不要直接覆盖用户计划。
