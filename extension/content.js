function visibleText(node) {
  return node && node.innerText ? node.innerText.trim() : '';
}

function collectFromDom() {
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
  return messages;
}

async function collectConversation() {
  const scrollables = [...document.querySelectorAll('main, main *')]
    .filter(node => node.scrollHeight > node.clientHeight + 200)
    .slice(0, 3);
  const positions = scrollables.map(node => node.scrollTop);
  const messages = [];
  const append = items => items.forEach(item => {
    if (item.text && !messages.some(existing => existing.role === item.role && existing.text === item.text)) {
      messages.push({...item, index: messages.length});
    }
  });
  append(collectFromDom());
  if (scrollables.length) {
    scrollables.forEach(node => { node.scrollTop = 0; });
    await new Promise(resolve => setTimeout(resolve, 900));
    append(collectFromDom());
    scrollables.forEach(node => { node.scrollTop = node.scrollHeight; });
    await new Promise(resolve => setTimeout(resolve, 900));
    append(collectFromDom());
    scrollables.forEach((node, index) => { node.scrollTop = positions[index]; });
  }
  return {
    title: document.title.replace(/^ChatGPT\s*[-–—]\s*/i, '').trim(),
    url: location.href,
    captured_at: new Date().toISOString(),
    messages: messages.slice(-200)
  };
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === 'lifeos.collect') {
    collectConversation().then(conversation => sendResponse({ ok: true, conversation }));
  }
  return true;
});
