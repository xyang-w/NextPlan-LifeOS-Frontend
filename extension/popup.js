const $ = id => document.getElementById(id);
const DEFAULT_ENDPOINT = 'https://backend-production-7612.up.railway.app/api/chat/sync';

async function currentConversation() {
  const tabs = await chrome.tabs.query({});
  const [tab] = tabs
    .filter(candidate => /^https:\/\/(chatgpt\.com|chat\.openai\.com)\//.test(candidate.url || ''))
    .sort((a, b) => Number(b.active) - Number(a.active) || Number(b.lastAccessed || 0) - Number(a.lastAccessed || 0));
  if (!tab?.id || !/^https:\/\/(chatgpt\.com|chat\.openai\.com)\//.test(tab.url || '')) {
    throw new Error('请先打开 chatgpt.com 的对话页面。');
  }
  try { return await chrome.tabs.sendMessage(tab.id, { type: 'lifeos.collect' }); }
  catch (_error) {
    try {
      const [result] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: () => ({
        title: document.title.replace(/^ChatGPT\s*[-–—]\s*/i, '').trim(), url: location.href,
        captured_at: new Date().toISOString(),
        messages: [{ index: 0, role: 'context', text: (document.querySelector('main')?.innerText || document.body.innerText || '').trim().slice(-120000) }]
      }) });
      return { ok: true, conversation: result.result };
    } catch (_fallbackError) {
      throw new Error('插件无法读取当前 ChatGPT 页面，请确认页面已完全加载并刷新后重试。');
    }
  }
}

async function loadConfig() {
  const config = await chrome.storage.local.get({ endpoint: DEFAULT_ENDPOINT });
  $('endpoint').value = config.endpoint;
}

function showPreview(conversation) {
  const text = conversation.messages.map(m => `${m.role}: ${m.text}`).join('\n\n');
  $('previewBox').textContent = text || '没有读取到当前页面中的对话内容。';
  $('previewBox').hidden = false;
  return text;
}

$('preview').onclick = async () => {
  $('status').textContent = '正在读取…';
  try {
    const conversation = (await currentConversation()).conversation;
    if (!conversation.messages[0]?.text) throw new Error('当前页面没有可读取的可见对话内容。');
    showPreview(conversation); $('status').textContent = '请确认预览内容后再同步。';
  }
  catch (e) { $('status').textContent = e.message; }
};

$('sync').onclick = async () => {
  $('status').textContent = '正在同步…';
  try {
    const endpoint = $('endpoint').value.trim() || DEFAULT_ENDPOINT;
    await chrome.storage.local.set({ endpoint });
    const result = await currentConversation();
    const conversation = result.conversation;
    if (!conversation.messages.length) throw new Error('没有读取到可同步的对话内容。');
    showPreview(conversation);
    const response = await fetch(endpoint, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: 'chatgpt-extension', conversation })
    });
    if (!response.ok) throw new Error(`LifeOS API 返回 ${response.status}`);
    $('status').textContent = '同步成功。请在 LifeOS 中确认待写入的计划变更。';
  } catch (e) { $('status').textContent = `同步失败：${e.message}`; }
};
loadConfig();
