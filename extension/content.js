function visibleText(node) {
  return node && node.innerText ? node.innerText.trim() : '';
}

function collectConversation() {
  const selectors = [
    'main [data-message-author-role]',
    'main [data-testid^="conversation-turn"]',
    '[data-message-author-role]',
    'article[data-testid^="conversation-turn"]',
    'main article'
  ];
  let nodes = [];
  for (const selector of selectors) {
    nodes = [...document.querySelectorAll(selector)];
    if (nodes.length) break;
  }
  let messages = nodes.map((node, index) => {
    const role = node.getAttribute('data-message-author-role') ||
      (visibleText(node).startsWith('You') ? 'user' : 'assistant');
    return { index, role, text: visibleText(node) };
  }).filter(message => message.text)
    .filter((message, index, all) => index === 0 || message.text !== all[index - 1].text);
  // ChatGPT changes its DOM structure frequently. Keep a safe visible-text
  // fallback so the integration still works when message attributes change.
  if (!messages.length) {
    const main = document.querySelector('main');
    const text = visibleText(main).replace(/\n{3,}/g, '\n\n');
    if (text) messages = [{ index: 0, role: 'context', text: text.slice(-120000) }];
  }
  return {
    title: document.title.replace(/^ChatGPT\s*[-–—]\s*/i, '').trim(),
    url: location.href,
    captured_at: new Date().toISOString(),
    messages: messages.slice(-80)
  };
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === 'lifeos.collect') {
    sendResponse({ ok: true, conversation: collectConversation() });
  }
  return true;
});
