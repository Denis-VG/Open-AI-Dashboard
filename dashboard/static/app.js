/* ==========================================================================
   Portable AI Dashboard — Application Logic
   Zero-dependency vanilla JS, organized by domain
   ========================================================================== */

// ─── State ──────────────────────────────────────────────────────────────────
const API = '';
let cfg = {};
let currentChatId = null;
let chatMessages = [];
let isStreaming = false;
let streamError = false;
let allModels = [];
let setupState = { provider: '', key: '', model: '', tier: 'free', baseUrl: '' };
let streamController = null;
let userScrolled = false;
let currentMode = 'normal';
let agentMode = false;
let workDir = '';
let sessionUsage = {};
let pendingAttachments = [];
let mentionMenu = null;
let mentionItems = [];
let mentionActive = -1;
const MAX_ATTACH_SIZE = 200 * 1024; // 200 KB per text attachment

const defaults = {
    gemini: 'gemini-2.0-pro-exp-02-05',
    anthropic: 'claude-3-7-sonnet-20250219',
    ollama: 'llama3.2:3b',
    openai: 'gpt-4o',
    nvidia: 'meta/llama-3.1-70b-instruct',
    deepseek: 'deepseek-v4-flash',
    lmstudio: '',
    'custom-openai': '',
    'custom-anthropic': 'claude-sonnet-4-20250514'
};

const providerNames = {
    openrouter: 'OpenRouter',
    gemini: 'Gemini',
    anthropic: 'Claude',
    ollama: 'Ollama',
    openai: 'OpenAI',
    nvidia: 'NVIDIA NIM',
    deepseek: 'DeepSeek',
    lmstudio: 'LM Studio',
    'custom-openai': 'Custom OpenAI-Compatible',
    'custom-anthropic': 'Custom Anthropic API'
};

// ─── Provider Config Table (data-driven, replaces if-else chain) ────────────
const PROVIDER_CONFIGS = {
    openrouter: {
        AI_PROVIDER: 'openai',
        CLAUDE_CODE_USE_OPENAI: '1',
        OPENAI_BASE_URL: 'https://openrouter.ai/api/v1',
    },
    nvidia: {
        AI_PROVIDER: 'openai',
        CLAUDE_CODE_USE_OPENAI: '1',
        OPENAI_BASE_URL: 'https://integrate.api.nvidia.com/v1',
    },
    deepseek: {
        AI_PROVIDER: 'openai',
        CLAUDE_CODE_USE_OPENAI: '1',
        OPENAI_BASE_URL: 'https://api.deepseek.com',
    },
    lmstudio: {
        AI_PROVIDER: 'openai',
        CLAUDE_CODE_USE_OPENAI: '1',
        OPENAI_API_KEY: 'lm-studio',
    },
    'custom-openai': {
        AI_PROVIDER: 'openai',
        CLAUDE_CODE_USE_OPENAI: '1',
    },
    'custom-anthropic': {
        AI_PROVIDER: 'anthropic',
        CLAUDE_CODE_USE_ANTHROPIC: '1',
    },
    openai: {
        AI_PROVIDER: 'openai',
        CLAUDE_CODE_USE_OPENAI: '1',
        OPENAI_BASE_URL: 'https://api.openai.com/v1',
    },
    gemini: {
        AI_PROVIDER: 'gemini',
    },
    anthropic: {
        AI_PROVIDER: 'anthropic',
    },
    ollama: {
        AI_PROVIDER: 'ollama',
        CLAUDE_CODE_USE_OPENAI: '1',
        OPENAI_API_KEY: 'ollama',
        OPENAI_BASE_URL: 'http://localhost:11434/v1',
    },
};

// ─── Deduplicated Provider Info ─────────────────────────────────────────────
function getProviderInfo(cfg) {
    let pName = cfg.AI_PROVIDER === 'openai' && cfg.OPENAI_BASE_URL && cfg.OPENAI_BASE_URL.indexOf('openrouter') !== -1
        ? 'OpenRouter'
        : cfg.AI_PROVIDER === 'openai' && cfg.OPENAI_BASE_URL && cfg.OPENAI_BASE_URL.indexOf('integrate.api.nvidia.com') !== -1
            ? 'NVIDIA NIM'
            : cfg.AI_PROVIDER === 'openai' && cfg.OPENAI_BASE_URL && cfg.OPENAI_BASE_URL.indexOf('api.deepseek.com') !== -1
                ? 'DeepSeek'
                : cfg.AI_PROVIDER === 'openai' && cfg.OPENAI_BASE_URL && cfg.OPENAI_BASE_URL.indexOf('localhost:1234') !== -1
                    ? 'LM Studio'
                    : cfg.AI_PROVIDER === 'openai' && cfg.OPENAI_BASE_URL && cfg.OPENAI_BASE_URL.indexOf('api.openai.com') === -1
                        ? 'Custom OpenAI-Compatible'
                        : cfg.AI_PROVIDER === 'ollama'
                            ? 'Local AI'
                            : providerNames[cfg.AI_PROVIDER] || cfg.AI_PROVIDER || '\u2014';

    const model = cfg.AI_DISPLAY_MODEL || cfg.OPENAI_MODEL || '\u2014';

    let providerURL = '\u2014';
    if (cfg.OPENAI_BASE_URL) {
        providerURL = cfg.OPENAI_BASE_URL;
    } else if (cfg.AI_PROVIDER === 'gemini') {
        providerURL = 'https://generativelanguage.googleapis.com';
    } else if (cfg.AI_PROVIDER === 'anthropic') {
        providerURL = 'https://api.anthropic.com';
    } else if (cfg.AI_PROVIDER === 'ollama') {
        providerURL = 'http://localhost:11434/v1';
    }

    return { pName: pName, model: model, providerURL: providerURL };
}

// ─── Utility Functions ──────────────────────────────────────────────────────
function escHtml(t) {
    return t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function relativeTime(iso) {
    var d = new Date(iso), now = new Date();
    var diff = (now - d) / 1000;
    if (diff < 60) return 'just now';
    if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    return d.toLocaleDateString();
}

function renderMarkdown(text) {
    if (!text) return '';
    var html = escHtml(text);

    html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, function (_, lang, code) {
        return '<pre><code>' + code.trim() + '</code></pre>';
    });
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
    html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    html = html.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');
    html = html.replace(/^---$/gm, '<hr>');
    html = html.replace(/^[\*\-] (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>\n?)+/g, function (m) { return '<ul>' + m + '</ul>'; });
    html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    html = html.split(/\n\n+/).map(function (block) {
        if (block.match(/^<(h[1-6]|ul|ol|blockquote|pre|hr)/)) return block;
        return '<p>' + block.replace(/\n/g, '<br>') + '</p>';
    }).join('\n');

    return html;
}

// ─── Toast ──────────────────────────────────────────────────────────────────
function showToast(msg, type) {
    type = type || '';
    var t = document.getElementById('toast');
    t.className = 'toast ' + type;
    t.innerHTML = (type === 'success' ? '\u2713 ' : type === 'error' ? '\u2717 ' : '') + msg;
    t.classList.add('show');
    setTimeout(function () { t.classList.remove('show'); }, 3000);
}

// ─── Theme ──────────────────────────────────────────────────────────────────
function toggleTheme() {
    var html = document.documentElement;
    var next = html.dataset.theme === 'dark' ? 'light' : 'dark';
    html.dataset.theme = next;
    localStorage.setItem('theme', next);
}

// ─── Sidebar ────────────────────────────────────────────────────────────────
function toggleSidebar() {
    var sb = document.getElementById('sidebar');
    if (window.innerWidth <= 500) {
        sb.classList.toggle('mobile-open');
        sb.classList.remove('collapsed');
    } else {
        sb.classList.toggle('collapsed');
    }
}

// ─── Page Navigation ────────────────────────────────────────────────────────
var pages = { chat: 'chatPage', setup: 'setupPage', system: 'systemPage', actions: 'actionsPage', updates: 'updatesPage' };
var tabs = { chat: 'tabChat', setup: 'tabSetup', system: 'tabSystem', actions: 'tabActions', updates: 'tabUpdates' };

function switchPage(name) {
    document.getElementById('chatPage').classList.remove('visible');
    Object.values(pages).forEach(function (id) {
        var p = document.getElementById(id);
        if (p) p.classList.remove('visible');
    });
    Object.values(tabs).forEach(function (id) {
        var t = document.getElementById(id);
        if (t) t.classList.remove('active');
    });

    if (name === 'chat') {
        document.getElementById('chatPage').classList.add('visible');
    } else {
        document.getElementById(pages[name]).classList.add('visible');
    }
    var tabEl = document.getElementById(tabs[name]);
    if (tabEl) tabEl.classList.add('active');

    if (name === 'setup') { loadProfiles(); loadSystemPrompt(); loadProjectPrompt(); }
    if (name === 'system') loadSystemInfo();
    if (name === 'updates') checkUpdates();
}

// ─── loadConfig ─────────────────────────────────────────────────────────────
async function loadConfig() {
    try {
        var res = await fetch(API + '/api/config');
        cfg = await res.json();
        var isConfigured = !!cfg.AI_PROVIDER;
        document.getElementById('noConfigBanner').style.display = isConfigured ? 'none' : 'flex';

        var info = getProviderInfo(cfg);
        document.getElementById('sbProvider').textContent = info.pName;
        document.getElementById('sbProviderURL').textContent = info.providerURL;
        document.getElementById('sbModel').textContent = info.model;
        document.getElementById('topbarTitle').textContent = isConfigured ? info.model : 'Portable AI';
    } catch (e) {
        console.error('loadConfig failed:', e);
    }
    loadSidebarInfo();
    loadProjectUsage();
}

async function loadSidebarInfo() {
    try {
        var res = await fetch(API + '/api/system');
        var d = await res.json();
        document.getElementById('sbGit').innerHTML = d.hasGit
            ? '<span class="info-badge badge-ok">\u2713</span>'
            : '<span class="info-badge badge-err">\u2717</span>';
        document.getElementById('sbPython').innerHTML = d.hasPython
            ? '<span class="info-badge badge-ok">\u2713</span>'
            : '<span class="info-badge badge-err">\u2717</span>';
    } catch (e) {
        console.error('loadSidebarInfo failed:', e);
    }
}

// ─── Token Usage ─────────────────────────────────────────────────────────────
function formatTokens(n) {
    if (!n || n < 1000) return String(n || '—');
    if (n < 1000000) return (n / 1000).toFixed(1) + 'k';
    return (n / 1000000).toFixed(1) + 'M';
}

function extractCacheTokens(usage) {
    return usage.cached_tokens
        || usage.cache_read_input_tokens
        || usage.prompt_cache_hit_tokens
        || (usage.prompt_tokens_details && usage.prompt_tokens_details.cached_tokens)
        || (usage.promptTokensDetails && usage.promptTokensDetails.cachedTokens)
        || 0;
}

function extractPromptTokens(usage) {
    return usage.prompt_tokens || usage.promptTokenCount || 0;
}

function extractCompletionTokens(usage) {
    return usage.completion_tokens || usage.candidatesTokenCount || 0;
}

function extractTotalTokens(usage) {
    return usage.total_tokens || usage.totalTokenCount
        || (extractPromptTokens(usage) + extractCompletionTokens(usage));
}

// Per-chat token bar (bottom of chat area)
function updateTokenBar() {
    var total = extractTotalTokens(sessionUsage);
    var prompt = extractPromptTokens(sessionUsage);
    var completion = extractCompletionTokens(sessionUsage);
    var cached = extractCacheTokens(sessionUsage);
    var cachePct = prompt > 0 ? Math.round(cached / prompt * 100) : 0;

    var parts = ['Tokens: ' + formatTokens(total) + ' (' + formatTokens(prompt) + ' in / ' + formatTokens(completion) + ' out)'];
    if (cachePct > 0) parts.push('Cache: ' + cachePct + '%');

    var bar = document.getElementById('tokenBar');
    bar.style.display = total > 0 ? 'flex' : 'none';
    document.getElementById('tokenBarText').innerHTML = parts.join(' <span style="color:var(--border)">·</span> ');
}

// Sidebar: global usage across all chats
async function loadProjectUsage() {
    try {
        var res = await fetch(API + '/api/project-usage');
        var d = await res.json();
        document.getElementById('sbTokens').textContent = formatTokens(d.total_tokens || 0);
    } catch (e) {
        console.error('loadProjectUsage failed:', e);
    }
}

// Called after each SSE done event
function updateTokenDisplay(usage) {
    // Accumulate into session
    for (var key in usage) {
        if (typeof usage[key] === 'number') {
            sessionUsage[key] = (sessionUsage[key] || 0) + usage[key];
        }
    }
    updateTokenBar();
    // Also save to global usage
    saveProjectUsage(usage);
}

async function saveProjectUsage(usage) {
    try {
        await fetch(API + '/api/project-usage', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(usage)
        });
        loadProjectUsage();
    } catch (e) { /* silent */ }
}

function resetSessionUsage() {
    sessionUsage = {};
    updateTokenBar();
}

// ─── Chat History List ──────────────────────────────────────────────────────
async function loadChatList() {
    try {
        var res = await fetch(API + '/api/chats');
        var data = await res.json();
        var chats = data.chats;
        var el = document.getElementById('chatList');
        if (!chats.length) {
            el.innerHTML = '<div style="padding:12px 16px;font-size:0.75rem;color:var(--text3)">No conversations yet</div>';
            return;
        }
        el.innerHTML = chats.map(function (c) {
            var activeClass = currentChatId === c.id ? ' active' : '';
            var isAgent = c.chat_mode === 'agent';
            var title = escHtml(c.title);
            var modeBadge = isAgent
                ? ' <span class="chat-mode-badge agent-badge" title="Agent mode">\uD83E\uDD16</span>'
                : ' <span class="chat-mode-badge simple-badge" title="Simple chat">\uD83D\uDCAC</span>';
            var meta = c.messageCount + ' msgs \u00b7 ' + relativeTime(c.updated);
            return '<div class="chat-item' + activeClass + '" data-action="openChat" data-id="' + c.id + '">'
                + '<div style="min-width:0">'
                + '<div class="chat-item-title">' + title + modeBadge + '</div>'
                + '<div class="chat-item-meta">' + meta + '</div>'
                + '</div>'
                + '<button class="chat-item-del" data-action="deleteChat" data-id="' + c.id + '" data-title="' + escHtml(c.title).replace(/"/g, '&quot;') + '">\u2715</button>'
                + '</div>';
        }).join('');
    } catch (e) {
        console.error('loadChatList failed:', e);
    }
}

async function openChatById(id) {
    try {
        var res = await fetch(API + '/api/chats/' + id);
        var chat = await res.json();
        if (chat.error) { localStorage.removeItem('activeChatId'); return; }
        currentChatId = id;
        localStorage.setItem('activeChatId', id);
        chatMessages = chat.messages || [];
        renderMessages(chatMessages);
        document.getElementById('topbarTitle').textContent = chat.title;

        // Restore agent mode from chat metadata
        var isAgentChat = chat.chat_mode === 'agent';
        agentMode = isAgentChat;
        localStorage.setItem('agentMode', isAgentChat);
        document.getElementById('agentToggle').checked = isAgentChat;
        document.getElementById('workdirBar').style.display = isAgentChat ? 'flex' : 'none';
        document.getElementById('chatInput').placeholder = isAgentChat
            ? 'Ask agent to create files, run commands...'
            : 'Message AI...';
        updateInputToolbar();
        updateModeToggle();
        if (isAgentChat) loadWorkDir();

        // Restore token usage from chat
        resetSessionUsage();
        if (chat.total_usage) updateTokenDisplay(chat.total_usage);
        else document.getElementById('sbTokens').textContent = '—';

        loadChatList();
        switchPage('chat');
    } catch (e) {
        console.error('openChatById failed:', e);
    }
}

var _pendingDeleteId = null;

function confirmDeleteChat(id, title) {
    _pendingDeleteId = id;
    document.getElementById('modalBody').textContent = '\u201c' + title + '\u201d will be permanently deleted and cannot be recovered.';
    document.getElementById('confirmModal').style.display = 'flex';
}

async function executeDelete() {
    var id = _pendingDeleteId;
    closeModal();
    if (!id) return;
    try {
        var res = await fetch(API + '/api/chats/' + id, { method: 'DELETE' });
        var data = await res.json();
        if (data.success) {
            if (currentChatId === id) {
                currentChatId = null;
                localStorage.removeItem('activeChatId');
                chatMessages = [];
                document.getElementById('messages').innerHTML = '';
                document.getElementById('messages').style.display = 'none';
                document.getElementById('welcomeScreen').style.display = 'flex';
                document.getElementById('topbarTitle').textContent = 'Portable AI';
            }
            showToast('Conversation deleted');
            loadChatList();
        } else {
            showToast('Failed to delete', 'error');
        }
    } catch (e) {
        console.error('executeDelete failed:', e);
        showToast('Failed to delete', 'error');
    }
}

function closeModal() {
    document.getElementById('confirmModal').style.display = 'none';
    _pendingDeleteId = null;
}

async function startNewChat() {
    try {
        var chatMode = agentMode ? 'agent' : 'simple';
        var res = await fetch(API + '/api/chats', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: 'New Conversation', chat_mode: chatMode })
        });
        var data = await res.json();
        currentChatId = data.id;
        localStorage.setItem('activeChatId', data.id);
        chatMessages = [];
        document.getElementById('messages').innerHTML = '';
        document.getElementById('messages').style.display = 'none';
        document.getElementById('welcomeScreen').style.display = 'flex';
        document.getElementById('topbarTitle').textContent = 'New Conversation';
        resetMode();
        resetSessionUsage();
        loadChatList();
        switchPage('chat');
        document.getElementById('chatInput').focus();
    } catch (e) {
        console.error('startNewChat failed:', e);
        showToast('Failed to create conversation', 'error');
    }
}

// ─── Mode Toggle ────────────────────────────────────────────────────────────
function setMode(mode) {
    currentMode = mode;
    document.getElementById('modeNormal').className = 'mode-pill' + (mode === 'normal' ? ' active-normal' : '');
    document.getElementById('modeLimitless').className = 'mode-pill' + (mode === 'limitless' ? ' active-limitless' : '');
}

function resetMode() {
    currentMode = 'normal';
    setMode('normal');
}

async function toggleAgent(enabled) {
    agentMode = enabled;
    localStorage.setItem('agentMode', enabled);
    document.getElementById('workdirBar').style.display = enabled ? 'flex' : 'none';
    document.getElementById('chatInput').placeholder = enabled
        ? 'Ask agent to create files, run commands...'
        : 'Message AI...';
    updateInputToolbar();
    updateModeToggle();
    if (enabled) loadWorkDir();

    // Persist mode change to current chat and refresh sidebar badges
    if (currentChatId) {
        try {
            var chat = await fetch(API + '/api/chats/' + currentChatId).then(function (r) { return r.json(); });
            if (chat && !chat.error) {
                chat.chat_mode = enabled ? 'agent' : 'simple';
                await fetch(API + '/api/chats/' + currentChatId, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(chat)
                });
            }
        } catch (e) {
            console.error('toggleAgent save failed:', e);
        }
        loadChatList();
    }
}

async function loadWorkDir() {
    try {
        var r = await fetch(API + '/api/workdir');
        var d = await r.json();
        workDir = d.workDir;
        document.getElementById('workdirPath').textContent = workDir;
    } catch (e) {
        console.error('loadWorkDir failed:', e);
    }
}

async function changeWorkDir() {
    var newDir = prompt('Enter new working directory:', workDir);
    if (!newDir) return;
    try {
        var r = await fetch(API + '/api/workdir', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: newDir })
        });
        var d = await r.json();
        if (d.success) {
            workDir = d.workDir;
            document.getElementById('workdirPath').textContent = workDir;
            showToast('Working directory updated', 'success');
        } else {
            showToast(d.error || 'Invalid directory', 'error');
        }
    } catch (e) {
        console.error('changeWorkDir failed:', e);
        showToast('Failed to update directory', 'error');
    }
}

// ─── Chat Sending ───────────────────────────────────────────────────────────
function handleKey(e) {
    if (mentionMenu) {
        if (e.key === 'ArrowDown') { e.preventDefault(); moveMention(1); return; }
        if (e.key === 'ArrowUp') { e.preventDefault(); moveMention(-1); return; }
        if (e.key === 'Enter' || e.key === 'Tab') {
            if (mentionItems.length) { e.preventDefault(); chooseMention(mentionActive); return; }
        }
        if (e.key === 'Escape') { e.preventDefault(); closeMentionMenu(); return; }
    }
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
}

function autoResize(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 180) + 'px';
}

function sendSuggestion(text) {
    document.getElementById('chatInput').value = text;
    sendMessage();
}

async function sendMessage() {
    if (isStreaming) return;
    streamError = false;
    var input = document.getElementById('chatInput');
    var text = input.value.trim();
    if (!text && !pendingAttachments.length) return;
    if (!cfg.AI_PROVIDER) {
        showToast('Please configure a provider first', 'error');
        switchPage('setup');
        return;
    }

    if (!currentChatId) await startNewChat();

    var userMsg = { role: 'user', content: text };
    if (pendingAttachments.length) {
        userMsg.attachments = pendingAttachments.map(function (a) {
            return { name: a.name, content: a.content, size: a.size };
        });
    }
    pendingAttachments = [];
    renderAttachList();

    setAgentStatus('thinking');
    input.value = '';
    input.style.height = 'auto';

    document.getElementById('welcomeScreen').style.display = 'none';
    document.getElementById('messages').style.display = 'flex';

    chatMessages.push(userMsg);
    appendMessage(userMsg, chatMessages.length - 1);
    scrollToBottom();

    var typingEl = document.createElement('div');
    typingEl.className = 'message';
    typingEl.innerHTML = '<div class="msg-avatar ai">AI</div><div class="msg-body"><div class="msg-bubble"><div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div></div></div>';
    document.getElementById('messages').appendChild(typingEl);
    scrollToBottom();

    isStreaming = true;
    userScrolled = false;
    document.getElementById('sendBtn').style.display = 'none';
    document.getElementById('stopBtn').style.display = 'flex';

    if (agentMode) {
        await sendAgentMessage(composeAgentContent(text), typingEl);
    } else {
        await sendChatMessage(composeUserContent(text, userMsg.attachments || []), typingEl);
    }

    isStreaming = false;
    setAgentStatus(streamError ? 'error' : 'ready');
    streamController = null;
    document.getElementById('sendBtn').style.display = 'flex';
    document.getElementById('stopBtn').style.display = 'none';
    document.getElementById('chatInput').focus();
}

// ─── Chat SSE Streaming (FIXED: buffer for partial lines) ──────────────────
async function sendChatMessage(text, typingEl) {
    var aiMsgEl = null;
    var fullText = '';
    var reasoningText = '';
    try {
        streamController = new AbortController();
        var res = await fetch(API + '/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                chatId: currentChatId,
                messages: chatMessages.slice(0, -1),
                userMessage: text,
                mode: currentMode
            }),
            signal: streamController.signal,
        });
        var reader = res.body.getReader();
        var decoder = new TextDecoder();
        typingEl.remove();

        var buffer = '';
        while (true) {
            var result = await reader.read();
            if (result.done) break;
            buffer += decoder.decode(result.value, { stream: true });
            var lines = buffer.split('\n');
            buffer = lines.pop();
            for (var i = 0; i < lines.length; i++) {
                var line = lines[i];
                if (line.indexOf('data: ') !== 0) continue;
                try {
                    var data = JSON.parse(line.slice(6));
                    if (data.type === 'reasoning') {
                        if (!aiMsgEl) aiMsgEl = appendMessage({ role: 'assistant', content: '' }, undefined, true);
                        reasoningText += data.content;
                        updateChatBubble(aiMsgEl, reasoningText, fullText, true);
                        scrollToBottom();
                    } else if (data.type === 'delta') {
                        if (!aiMsgEl) aiMsgEl = appendMessage({ role: 'assistant', content: '' }, undefined, true);
                        fullText += data.content;
                        updateChatBubble(aiMsgEl, reasoningText, fullText, true);
                        scrollToBottom();
                    } else if (data.type === 'done') {
                        if (aiMsgEl) updateChatBubble(aiMsgEl, reasoningText, data.fullText || fullText, false);
                        fullText = data.fullText || fullText;
                        pushAssistantMessage(fullText, aiMsgEl);
                        if (data.usage) updateTokenDisplay(data.usage);
                        loadChatList();
                    } else if (data.type === 'error') {
                        streamError = true;
                        setAgentStatus('error');
                        typingEl.remove();
                        if (aiMsgEl) updateChatBubble(aiMsgEl, reasoningText, fullText, false);
                        var errMsg = '\u26a0\ufe0f Error: ' + (data.content || 'Unknown error');
                        var errEl = appendMessage({ role: 'assistant', content: errMsg });
                        pushAssistantMessage(errMsg, errEl);
                        loadChatList();
                    }
                } catch (e) {
                    console.error('SSE parse error (chat):', e);
                }
            }
        }
    } catch (err) {
        if (err.name === 'AbortError') {
            if (aiMsgEl) updateChatBubble(aiMsgEl, reasoningText, fullText || '*(stopped)*', false);
            if (fullText) pushAssistantMessage(fullText, aiMsgEl);
        } else {
            typingEl.remove();
            appendMessage({ role: 'assistant', content: '\u26a0\ufe0f Error: ' + err.message });
        }
    }
}

// ─── Agent SSE Streaming ────────────────────────────────────────────────────
async function sendAgentMessage(text, typingEl) {
    var aiMsgEl = null;
    var fullText = '';
    var toolCards = new Map();
    var lastReasoningEl = null;
    try {
        streamController = new AbortController();
        var res = await fetch(API + '/api/agent', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                chatId: currentChatId,
                messages: chatMessages.slice(0, -1),
                userMessage: text,
                mode: currentMode
            }),
            signal: streamController.signal,
        });
        var reader = res.body.getReader();
        var decoder = new TextDecoder();
        typingEl.remove();
        var buffer = '';
        while (true) {
            var result = await reader.read();
            if (result.done) break;
            buffer += decoder.decode(result.value, { stream: true });
            var lines = buffer.split('\n');
            buffer = lines.pop();
            for (var i = 0; i < lines.length; i++) {
                var line = lines[i];
                if (line.indexOf('data: ') !== 0) continue;
                try {
                    var data = JSON.parse(line.slice(6));
                    if (data.type === 'agent_thinking') {
                        // Finalize previous reasoning card if any
                        if (lastReasoningEl) finalizeReasoningCard(lastReasoningEl);
                        lastReasoningEl = null;
                    } else if (data.type === 'agent_reasoning') {
                        setAgentStatus('reasoning');
                        // Finalize previous, create new inline reasoning card
                        if (lastReasoningEl) finalizeReasoningCard(lastReasoningEl);
                        lastReasoningEl = createReasoningCard(data.iteration, data.content);
                        document.getElementById('messages').appendChild(lastReasoningEl);
                        scrollToBottom();
                    } else if (data.type === 'tool_call') {
                        setAgentStatus('exec');
                        // Finalize reasoning card so tool appears right after it
                        if (lastReasoningEl) { finalizeReasoningCard(lastReasoningEl); lastReasoningEl = null; }
                        var card = createToolCard(data);
                        toolCards.set(data.id, card);
                        document.getElementById('messages').appendChild(card);
                        scrollToBottom();
                    } else if (data.type === 'approval_needed') {
                        var card2 = toolCards.get(data.id);
                        if (card2) addApprovalButtons(card2, data.id);
                        scrollToBottom();
                    } else if (data.type === 'tool_result') {
                        var card3 = toolCards.get(data.id);
                        if (card3) updateToolCardResult(card3, data);
                        scrollToBottom();
                    } else if (data.type === 'tool_rejected') {
                        var card4 = toolCards.get(data.id);
                        if (card4) {
                            card4.querySelector('.tool-status').className = 'tool-status rejected';
                            card4.querySelector('.tool-status').textContent = 'Rejected';
                            var ab = card4.querySelector('.approval-bar');
                            if (ab) ab.remove();
                        }
                    } else if (data.type === 'agent_text') {
                        if (lastReasoningEl) { finalizeReasoningCard(lastReasoningEl); lastReasoningEl = null; }
                        fullText = data.content;
                        if (!aiMsgEl) aiMsgEl = appendMessage({ role: 'assistant', content: '' }, undefined, false);
                        finalizeMessage(aiMsgEl, fullText);
                        scrollToBottom();
                    } else if (data.type === 'agent_error') {
                        streamError = true;
                        setAgentStatus('error');
                        if (lastReasoningEl) { lastReasoningEl.remove(); lastReasoningEl = null; }
                        var errMsg2 = '\u26a0\ufe0f Agent Error: ' + (data.error || 'Unknown error');
                        var errEl2 = appendMessage({ role: 'assistant', content: errMsg2 });
                        pushAssistantMessage(errMsg2, errEl2);
                        loadChatList();
                    } else if (data.type === 'done') {
                        if (lastReasoningEl) { finalizeReasoningCard(lastReasoningEl); lastReasoningEl = null; }
                        if (data.fullText) {
                            fullText = data.fullText;
                            pushAssistantMessage(fullText, aiMsgEl);
                        }
                        if (data.usage) updateTokenDisplay(data.usage);
                        loadChatList();
                    }
                } catch (e) {
                    console.error('SSE parse error (agent):', e);
                }
            }
        }
    } catch (err) {
        if (err.name !== 'AbortError') {
            typingEl.remove();
            appendMessage({ role: 'assistant', content: '\u26a0\ufe0f Error: ' + err.message });
        }
    }
}

// ─── Inline Reasoning Cards ──────────────────────────────────────────────────
function createReasoningCard(iteration, content) {
    var el = document.createElement('div');
    el.className = 'message';
    el.innerHTML = '<div class="msg-avatar ai">AI</div><div class="msg-body"><div class="reasoning-card open">'
        + '<div class="reasoning-header" onclick="var b=this.nextElementSibling;b.classList.toggle(\'open\');this.querySelector(\'.reasoning-arrow\').classList.toggle(\'open\')">'
        + '<span class="reasoning-pulse"></span>'
        + '<span class="reasoning-label">Reasoning \u2014 Step ' + iteration + '</span>'
        + '<span class="reasoning-arrow open">\u25bc</span>'
        + '</div>'
        + '<div class="reasoning-body open">' + escHtml(content) + '</div>'
        + '</div></div>';
    return el;
}

function finalizeReasoningCard(el) {
    var pulse = el.querySelector('.reasoning-pulse');
    if (pulse) pulse.classList.add('done');
    var body = el.querySelector('.reasoning-body');
    var arrow = el.querySelector('.reasoning-arrow');
    if (body) body.classList.remove('open');
    if (arrow) arrow.classList.remove('open');
}

// ─── Tool Cards ─────────────────────────────────────────────────────────────
function createToolCard(data) {
    var icons = { write_file: '\ud83d\udcc4', read_file: '\ud83d\udcd6', list_directory: '\ud83d\udcc1', execute_command: '\u26a1', search_files: '\ud83d\udd0d' };
    var el = document.createElement('div');
    el.className = 'message';
    var argsPreview = data.name === 'write_file' ? data.args.path
        : data.name === 'execute_command' ? data.args.command
        : data.name === 'read_file' ? data.args.path
        : data.name === 'list_directory' ? (data.args.path || '.')
        : data.args.pattern;
    el.innerHTML = '<div class="msg-avatar ai">AI</div><div class="msg-body"><div class="tool-card" id="tc_' + data.id + '">'
        + '<div class="tool-header" onclick="this.nextElementSibling.classList.toggle(\'open\')">'
        + '<span class="tool-icon">' + (icons[data.name] || '\ud83d\udd27') + '</span>'
        + '<span class="tool-name">' + data.name + '(' + escHtml(String(argsPreview || '').slice(0, 60)) + ')</span>'
        + '<span class="tool-status running">' + (data.needs_approval ? 'Pending' : 'Running') + '</span>'
        + '</div>'
        + '<div class="tool-body">' + (data.name === 'write_file' ? escHtml(data.args.content || '').slice(0, 2000) : JSON.stringify(data.args, null, 2)) + '</div>'
        + '</div></div>';
    return el;
}

function addApprovalButtons(card, callId) {
    var tc = card.querySelector('.tool-card');
    tc.querySelector('.tool-status').className = 'tool-status pending';
    tc.querySelector('.tool-status').textContent = 'Needs Approval';
    var bar = document.createElement('div');
    bar.className = 'approval-bar';
    bar.innerHTML = '<span class="approval-label">This action modifies your system. Allow?</span>'
        + '<button class="approve-btn yes" data-action="approve" data-id="' + callId + '" data-approved="true">\u2713 Approve</button>'
        + '<button class="approve-btn no" data-action="approve" data-id="' + callId + '" data-approved="false">\u2717 Reject</button>';
    tc.appendChild(bar);
}

async function approveToolCall(callId, approved, btn) {
    var bar = btn.closest('.approval-bar');
    bar.innerHTML = '<span class="approval-label">' + (approved ? 'Approved \u2014 executing...' : 'Rejected') + '</span>';
    try {
        await fetch(API + '/api/agent/approve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ callId: callId, approved: approved })
        });
    } catch (e) {
        console.error('approveToolCall failed:', e);
    }
}

function updateToolCardResult(card, data) {
    var tc = card.querySelector('.tool-card');
    var status = tc.querySelector('.tool-status');
    var body = tc.querySelector('.tool-body');
    var ab = tc.querySelector('.approval-bar');
    if (ab) ab.remove();
    if (data.result && data.result.success) {
        status.className = 'tool-status success';
        status.textContent = 'Done';
    } else {
        status.className = 'tool-status rejected';
        status.textContent = 'Failed';
    }
    var resultText = '';
    if (data.name === 'write_file') {
        resultText = (data.result && data.result.message) || 'File written';
    } else if (data.name === 'read_file') {
        resultText = (data.result && data.result.content ? data.result.content.slice(0, 3000) : '') || (data.result && data.result.error) || '';
    } else if (data.name === 'list_directory') {
        resultText = ((data.result && data.result.entries) || []).map(function (e) {
            return (e.type === 'directory' ? '\ud83d\udcc1' : '\ud83d\udcc4') + ' ' + e.name + (e.size ? ' (' + e.size + 'b)' : '');
        }).join('\n');
    } else if (data.name === 'execute_command') {
        resultText = ((data.result && data.result.output) || '') + (data.result && data.result.error ? '\n[STDERR] ' + data.result.error : '');
    } else if (data.name === 'search_files') {
        resultText = (data.result && data.result.matches) || (data.result && data.result.message) || '';
    } else {
        resultText = JSON.stringify(data.result, null, 2);
    }
    body.textContent = resultText || '(no output)';
    body.classList.add('open');
}

function abortStream() {
    if (streamController) {
        streamController.abort();
    }
    setAgentStatus('ready');
}

// ─── Agent Status Indicator ──────────────────────────────────────────────────
var _statusTimer = null;
var _statusStart = 0;

function setAgentStatus(state) {
    var el = document.getElementById('agentStatus');
    var timeEl = document.getElementById('agentElapsed');
    if (!el) return;

    // Clear any running timer
    if (_statusTimer) { clearInterval(_statusTimer); _statusTimer = null; }
    if (state !== 'thinking' && state !== 'reasoning' && state !== 'exec') _statusStart = 0;

    var labels = { ready: 'Ready', thinking: 'Thinking', reasoning: 'Reasoning', exec: 'Exec', error: 'Error' };
    var label = labels[state] || state;

    if (state === 'ready') {
        el.className = 'agent-status ready';
        el.title = 'Ready';
        if (timeEl) { timeEl.textContent = label; timeEl.style.display = ''; }
    } else if (state === 'error') {
        el.className = 'agent-status error';
        el.title = label;
        if (timeEl) {
            timeEl.textContent = label;
            timeEl.style.display = '';
        }
    } else {
        // thinking / reasoning / exec — yellow pulsing, continuous timer
        el.className = 'agent-status busy';
        el.title = label;
        if (!_statusStart) _statusStart = Date.now();
        if (timeEl) timeEl.style.display = '';
        if (!_statusTimer) {
            _statusTimer = setInterval(function () {
                var sec = ((Date.now() - _statusStart) / 1000).toFixed(1);
                if (timeEl) timeEl.textContent = label + ' · ' + sec + 's';
            }, 200);
        }
    }
}

// ─── Message Rendering ──────────────────────────────────────────────────────
function appendMessage(msg, idx, streaming) {
    streaming = streaming || false;
    var el = document.createElement('div');
    el.className = 'message ' + msg.role;
    if (idx !== undefined) el.setAttribute('data-index', idx);
    var isUser = msg.role === 'user';
    var contentHtml = isUser
        ? escHtml(msg.content).replace(/\n/g, '<br>')
        : renderMarkdown(msg.content) + (streaming ? '<span class="cursor"></span>' : '');
    var attachmentsHtml = '';
    if (isUser && msg.attachments && msg.attachments.length) {
        attachmentsHtml = '<div class="msg-attachments">' + msg.attachments.map(function (a) {
            return '<span class="msg-attach-chip">\uD83D\uDCCE ' + escHtml(a.name) + '</span>';
        }).join('') + '</div>';
    }
    var actionsHtml = isUser ? (
        '<div class="msg-actions">'
        + '<button class="msg-act-btn" title="Copy" onclick="copyUserMessage(' + idx + ')">\uD83D\uDCCB</button>'
        + '<button class="msg-act-btn" title="Edit" onclick="editUserMessage(' + idx + ')">\u270F\uFE0F</button>'
        + '<button class="msg-act-btn msg-act-del" title="Delete" onclick="deleteUserMessage(' + idx + ')">\uD83D\uDDD1\uFE0F</button>'
        + '</div>'
    ) : (
        '<div class="msg-actions">'
        + '<button class="msg-act-btn" title="Copy" data-action="copyAssistant">\uD83D\uDCCB</button>'
        + '<button class="msg-act-btn" title="Save as file" data-action="saveAssistant">\uD83D\uDCBE</button>'
        + '</div>'
    );
    el.innerHTML = '<div class="msg-avatar ' + (isUser ? 'user' : 'ai') + '">' + (isUser ? '\ud83d\udc64' : 'AI') + '</div>'
        + '<div class="msg-body">'
        + '<div class="msg-name">' + (isUser ? 'You' : 'Assistant') + '</div>'
        + '<div class="msg-bubble">' + contentHtml + '</div>'
        + attachmentsHtml
        + actionsHtml
        + '</div>';
    document.getElementById('messages').appendChild(el);
    return el;
}

function updateStreamingMessage(el, text) {
    var bubble = el.querySelector('.msg-bubble');
    if (bubble) bubble.innerHTML = renderMarkdown(text) + '<span class="cursor"></span>';
}

function updateChatBubble(el, reasoning, answer, streaming) {
    var bubble = el.querySelector('.msg-bubble');
    if (!bubble) return;
    var html = '';
    if (reasoning) {
        var collapsed = !!answer && el.dataset.reasoningOpen !== '1';
        html += '<div class="chat-reasoning' + (collapsed ? ' collapsed' : '') + '">'
            + '<div class="chat-reasoning-head" onclick="toggleChatReasoning(this)">'
            + '\uD83D\uDCAD Reasoning <span class="chat-reasoning-caret">' + (collapsed ? '\u25B8' : '\u25BE') + '</span>'
            + '</div>'
            + '<div class="chat-reasoning-body">' + escHtml(reasoning).replace(/\n/g, '<br>') + '</div>'
            + '</div>';
    }
    if (answer) html += renderMarkdown(answer);
    bubble.innerHTML = html + (streaming ? '<span class="cursor"></span>' : '');
    var box = bubble.querySelector('.chat-reasoning');
    if (box) {
        var body = box.querySelector('.chat-reasoning-body');
        if (body && !box.classList.contains('collapsed')) body.scrollTop = body.scrollHeight;
    }
}

function toggleChatReasoning(head) {
    var box = head.closest('.chat-reasoning');
    if (!box) return;
    var collapsed = box.classList.toggle('collapsed');
    var caret = box.querySelector('.chat-reasoning-caret');
    if (caret) caret.textContent = collapsed ? '\u25B8' : '\u25BE';
    var msgEl = box.closest('.message');
    if (msgEl) msgEl.dataset.reasoningOpen = collapsed ? '0' : '1';
}

function finalizeMessage(el, text) {
    var bubble = el.querySelector('.msg-bubble');
    if (bubble) bubble.innerHTML = renderMarkdown(text);
}

function renderMessages(msgs) {
    var el = document.getElementById('messages');
    if (!msgs.length) {
        el.style.display = 'none';
        document.getElementById('welcomeScreen').style.display = 'flex';
        return;
    }
    el.style.display = 'flex';
    document.getElementById('welcomeScreen').style.display = 'none';
    el.innerHTML = '';
    msgs.forEach(function (m, i) { appendMessage(m, i); });
    scrollToBottom();
}

// ─── Message Actions (copy / edit / delete) ──────────────────────────────────

function copyUserMessage(idx) {
    var msg = chatMessages[idx];
    if (!msg) return;
    navigator.clipboard.writeText(msg.content).then(function () {
        showToast('Copied to clipboard', 'success');
    }).catch(function () {
        showToast('Failed to copy', 'error');
    });
}

function editUserMessage(idx) {
    var el = document.querySelector('.message.user[data-index="' + idx + '"]');
    if (!el) return;
    var bubble = el.querySelector('.msg-bubble');
    var actions = el.querySelector('.msg-actions');
    var origText = chatMessages[idx].content;

    // Replace bubble with textarea
    bubble.style.display = 'none';
    if (actions) actions.style.display = 'none';

    var ta = document.createElement('textarea');
    ta.className = 'msg-edit-textarea';
    ta.value = origText;
    ta.setAttribute('data-orig', origText);
    ta.setAttribute('data-idx', idx);
    ta.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') cancelEditUserMessage(idx);
    });

    var editBar = document.createElement('div');
    editBar.className = 'msg-edit-bar';
    editBar.innerHTML = '<button class="btn btn-sm btn-primary" onclick="saveEditUserMessage(' + idx + ')">Save & Resend</button>'
        + '<button class="btn btn-sm btn-outline" onclick="cancelEditUserMessage(' + idx + ')">Cancel</button>';

    bubble.parentNode.insertBefore(ta, bubble);
    bubble.parentNode.insertBefore(editBar, bubble);
    ta.focus();
    autoResize(ta);
    ta.addEventListener('input', function () { autoResize(ta); });
}

function cancelEditUserMessage(idx) {
    var el = document.querySelector('.message.user[data-index="' + idx + '"]');
    if (!el) return;
    var bubble = el.querySelector('.msg-bubble');
    var actions = el.querySelector('.msg-actions');
    var ta = el.querySelector('.msg-edit-textarea');
    var bar = el.querySelector('.msg-edit-bar');

    bubble.style.display = '';
    if (actions) actions.style.display = '';
    if (ta) ta.remove();
    if (bar) bar.remove();
}

async function saveEditUserMessage(idx) {
    var el = document.querySelector('.message.user[data-index="' + idx + '"]');
    if (!el) return;
    var ta = el.querySelector('.msg-edit-textarea');
    if (!ta) return;
    var newText = ta.value.trim();
    var origText = ta.getAttribute('data-orig');

    if (!newText || newText === origText) {
        cancelEditUserMessage(idx);
        return;
    }

    // Preserve any attachments that were on the original message
    var origAttachments = (chatMessages[idx] && chatMessages[idx].attachments) ? chatMessages[idx].attachments : [];

    // Truncate chatMessages: keep everything up to (idx - 1), then new text as user msg
    chatMessages = chatMessages.slice(0, idx);
    var newMsg = { role: 'user', content: newText };
    if (origAttachments.length) newMsg.attachments = origAttachments;
    chatMessages.push(newMsg);

    // Re-render and resend (backend saves user + assistant reply atomically)
    renderMessages(chatMessages);
    loadChatList();
    resendLastUserMessage();
}

async function deleteUserMessage(idx) {
    if (!confirm('Delete this message and all subsequent replies?')) return;

    // Truncate: keep messages up to but NOT including idx
    chatMessages = chatMessages.slice(0, idx);

    // Save to disk
    if (currentChatId) {
        try {
            var existing = await fetch(API + '/api/chats/' + currentChatId).then(function (r) { return r.json(); });
            if (existing && !existing.error) {
                existing.messages = chatMessages.slice();
                existing.updated = new Date().toISOString();
                await fetch(API + '/api/chats/' + currentChatId, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(existing)
                });
            }
        } catch (e) {
            console.error('deleteUserMessage save failed:', e);
        }
    }

    if (!chatMessages.length) {
        // All messages deleted — reset to welcome screen
        currentChatId = null;
        localStorage.removeItem('activeChatId');
        document.getElementById('messages').innerHTML = '';
        document.getElementById('messages').style.display = 'none';
        document.getElementById('welcomeScreen').style.display = 'flex';
        document.getElementById('topbarTitle').textContent = 'Portable AI';
        resetMode();
        loadChatList();
    } else {
        renderMessages(chatMessages);
        loadChatList();
    }
    showToast('Messages deleted', 'success');
}

async function resendLastUserMessage() {
    // The last message in chatMessages is the user text to send
    // Remove the visual user msg we just rendered (it's already in chatMessages)
    streamError = false;
    var input = document.getElementById('chatInput');
    var lastMsg = chatMessages[chatMessages.length - 1];
    var lastText = agentMode
        ? composeAgentContent(lastMsg.content)
        : composeUserContent(lastMsg.content, lastMsg.attachments || []);

    // show welcome off, messages on
    document.getElementById('welcomeScreen').style.display = 'none';
    document.getElementById('messages').style.display = 'flex';

    // Add typing indicator
    var typingEl = document.createElement('div');
    typingEl.className = 'message';
    typingEl.innerHTML = '<div class="msg-avatar ai">AI</div><div class="msg-body"><div class="msg-bubble"><div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div></div></div>';
    document.getElementById('messages').appendChild(typingEl);
    scrollToBottom();

    isStreaming = true;
    userScrolled = false;
    document.getElementById('sendBtn').style.display = 'none';
    document.getElementById('stopBtn').style.display = 'flex';

    if (agentMode) {
        await sendAgentMessage(lastText, typingEl);
    } else {
        await sendChatMessage(lastText, typingEl);
    }

    isStreaming = false;
    setAgentStatus(streamError ? 'error' : 'ready');
    streamController = null;
    document.getElementById('sendBtn').style.display = 'flex';
    document.getElementById('stopBtn').style.display = 'none';
    document.getElementById('chatInput').focus();
}

// ─── Attachments (paperclip, chat-only) ──────────────────────────────────────
function updateInputToolbar() {
    var btn = document.getElementById('attachBtn');
    if (btn) btn.style.display = agentMode ? 'none' : 'flex';
}

function updateModeToggle() {
    var pills = document.getElementById('modePills');
    var label = document.getElementById('modeLabel');
    if (pills) pills.style.display = agentMode ? 'flex' : 'none';
    if (label) label.style.display = agentMode ? 'inline' : 'none';
}

function handleAttachFiles(fileList) {
    var files = Array.prototype.slice.call(fileList || []);
    files.forEach(function (f) {
        if (f.size > MAX_ATTACH_SIZE) {
            showToast('File too large (max 200 KB): ' + f.name, 'error');
            return;
        }
        var reader = new FileReader();
        reader.onload = function () {
            pendingAttachments.push({ name: f.name, content: String(reader.result), size: f.size });
            renderAttachList();
        };
        reader.onerror = function () { showToast('Failed to read: ' + f.name, 'error'); };
        reader.readAsText(f);
    });
    var inp = document.getElementById('attachInput');
    if (inp) inp.value = '';
}

function renderAttachList() {
    var list = document.getElementById('attachList');
    if (!list) return;
    list.innerHTML = pendingAttachments.map(function (a, i) {
        return '<span class="attach-chip">\uD83D\uDCCE ' + escHtml(a.name)
            + ' <button class="attach-remove" title="Remove" onclick="removeAttachment(' + i + ')">\u2715</button></span>';
    }).join('');
    list.style.display = pendingAttachments.length ? 'flex' : 'none';
}

function removeAttachment(i) {
    pendingAttachments.splice(i, 1);
    renderAttachList();
}

// ─── Message composition (send-time) ─────────────────────────────────────────
function composeUserContent(text, attachments) {
    if (!attachments || !attachments.length) return text;
    var parts = [text];
    attachments.forEach(function (a) {
        parts.push('Attached file: ' + a.name + '\n```\n' + a.content + '\n```');
    });
    return parts.filter(function (s) { return s && s.trim(); }).join('\n\n');
}

function composeAgentContent(text) {
    var refs = [];
    var re = /(?:^|\s)@([A-Za-z0-9_.\-\/\\]+)/g;
    var m;
    while ((m = re.exec(text)) !== null) {
        var p = m[1];
        if (p && !/[\/\\]$/.test(p)) refs.push(p);
    }
    if (!refs.length) return text;
    var note = '\n\nFiles referenced by the user \u2014 read them with read_file before answering:\n'
        + refs.map(function (p) { return '- ' + p; }).join('\n');
    return text + note;
}

// ─── Assistant copy / save ───────────────────────────────────────────────────
function pushAssistantMessage(content, el) {
    chatMessages.push({ role: 'assistant', content: content });
    if (el) el.setAttribute('data-index', chatMessages.length - 1);
}

function messageIndex(el) {
    var msgEl = el.closest('.message');
    if (!msgEl) return -1;
    var idx = msgEl.getAttribute('data-index');
    return idx == null ? -1 : parseInt(idx, 10);
}

function copyAssistantMessage(idx) {
    var msg = chatMessages[idx];
    if (!msg) return;
    navigator.clipboard.writeText(msg.content).then(function () {
        showToast('Copied to clipboard', 'success');
    }).catch(function () {
        showToast('Failed to copy', 'error');
    });
}

const LANG_EXT = {
    python: 'py', py: 'py', c: 'c', 'c++': 'cpp', cpp: 'cpp', 'c#': 'cs', csharp: 'cs',
    javascript: 'js', js: 'js', typescript: 'ts', ts: 'ts', tsx: 'tsx', jsx: 'jsx',
    bash: 'sh', sh: 'sh', shell: 'sh', zsh: 'sh', powershell: 'ps1', ps1: 'ps1',
    markdown: 'md', md: 'md', json: 'json', html: 'html', htm: 'html', css: 'css',
    scss: 'scss', sql: 'sql', yaml: 'yml', yml: 'yml', toml: 'toml', ini: 'ini',
    go: 'go', rust: 'rs', java: 'java', kotlin: 'kt', swift: 'swift', php: 'php',
    ruby: 'rb', r: 'r', lua: 'lua', perl: 'pl', dart: 'dart', scala: 'scala',
    text: 'txt', txt: 'txt', diff: 'diff'
};

function extForLang(lang) {
    var l = (lang || '').trim().toLowerCase();
    return LANG_EXT[l] || l || 'txt';
}

function parseCodeBlocks(text) {
    var blocks = [];
    var re = /```(\w*)[ \t]*\n?([\s\S]*?)```/g;
    var m;
    while ((m = re.exec(text)) !== null) {
        blocks.push({ lang: m[1].trim(), code: m[2].replace(/\n$/, '') });
    }
    return blocks;
}

function downloadTextFile(filename, content) {
    var blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
}

function saveAssistantMessage(idx, btn) {
    var msg = chatMessages[idx];
    if (!msg) return;
    var text = msg.content || '';
    var blocks = parseCodeBlocks(text);
    if (!blocks.length) {
        downloadTextFile('answer.md', text);
        showToast('Saved answer.md', 'success');
        return;
    }
    if (blocks.length === 1) {
        var ext = extForLang(blocks[0].lang);
        downloadTextFile('file.' + ext, blocks[0].code);
        showToast('Saved file.' + ext, 'success');
        return;
    }
    showSaveMenu(btn, blocks);
}

function showSaveMenu(btn, blocks) {
    closeSaveMenu();
    var menu = document.createElement('div');
    menu.className = 'save-menu';
    menu.id = 'saveMenu';
    blocks.forEach(function (b, i) {
        var ext = extForLang(b.lang);
        var item = document.createElement('div');
        item.className = 'save-menu-item';
        item.textContent = 'file' + (i + 1) + '.' + ext + '  (' + (b.lang || 'text') + ')';
        item.addEventListener('click', function () {
            downloadTextFile('file' + (i + 1) + '.' + ext, b.code);
            closeSaveMenu();
            showToast('Saved file' + (i + 1) + '.' + ext, 'success');
        });
        menu.appendChild(item);
    });
    document.body.appendChild(menu);
    var rect = btn.getBoundingClientRect();
    menu.style.left = Math.min(rect.left, window.innerWidth - 280) + 'px';
    menu.style.top = (rect.bottom + 6) + 'px';
    setTimeout(function () { document.addEventListener('click', closeSaveMenuOnOutside); }, 0);
}

function closeSaveMenuOnOutside(e) {
    if (e.target.closest('.save-menu')) return;
    closeSaveMenu();
}

function closeSaveMenu() {
    var m = document.getElementById('saveMenu');
    if (m) m.remove();
    document.removeEventListener('click', closeSaveMenuOnOutside);
}

// ─── @-mention autocomplete (agent-only) ─────────────────────────────────────
function handleMentionInput() {
    var ta = document.getElementById('chatInput');
    if (!agentMode) { closeMentionMenu(); return; }
    var ctx = getMentionContext(ta);
    if (!ctx) { closeMentionMenu(); return; }
    var q = ctx.query;
    fetchFileSuggestions(q).then(function (items) {
        var ctx2 = getMentionContext(ta);
        if (!ctx2 || ctx2.query !== q) return;
        mentionItems = items;
        mentionActive = 0;
        renderMentionMenu(ta);
    });
}

function getMentionContext(ta) {
    var pos = ta.selectionStart == null ? ta.value.length : ta.selectionStart;
    var before = ta.value.slice(0, pos);
    var at = before.lastIndexOf('@');
    if (at === -1) return null;
    if (at > 0 && !/\s/.test(before.charAt(at - 1))) return null;
    var query = before.slice(at + 1);
    if (/\s/.test(query)) return null;
    return { at: at, query: query };
}

async function fetchFileSuggestions(query) {
    var dir = '.';
    var prefix = query;
    var slash = query.lastIndexOf('/');
    if (slash !== -1) {
        dir = query.slice(0, slash) || '.';
        prefix = query.slice(slash + 1);
    }
    try {
        var res = await fetch(API + '/api/files?path=' + encodeURIComponent(dir));
        var d = await res.json();
        if (!d.success) return [];
        var p = prefix.toLowerCase();
        return (d.entries || []).filter(function (e) {
            if (e.type !== 'file' && e.type !== 'dir') return false;
            return !p || e.name.toLowerCase().indexOf(p) === 0;
        }).slice(0, 40);
    } catch (e) {
        return [];
    }
}

function renderMentionMenu(ta) {
    if (mentionMenu) { mentionMenu.remove(); mentionMenu = null; }
    if (!mentionItems.length) return;
    var menu = document.createElement('div');
    menu.className = 'mention-menu';
    mentionItems.forEach(function (item, i) {
        var el = document.createElement('div');
        el.className = 'mention-item' + (i === mentionActive ? ' active' : '');
        el.textContent = (item.type === 'dir' ? '\uD83D\uDCC1 ' : '\uD83D\uDCC4 ') + item.path;
        el.addEventListener('mousedown', function (e) { e.preventDefault(); chooseMention(i); });
        menu.appendChild(el);
    });
    document.body.appendChild(menu);
    mentionMenu = menu;
    var bar = document.getElementById('input-bar');
    var rect = bar.getBoundingClientRect();
    menu.style.left = rect.left + 'px';
    menu.style.width = Math.max(rect.width, 320) + 'px';
    menu.style.bottom = (window.innerHeight - rect.top + 8) + 'px';
}

function moveMention(delta) {
    if (!mentionItems.length) return;
    mentionActive = (mentionActive + delta + mentionItems.length) % mentionItems.length;
    var items = mentionMenu ? mentionMenu.querySelectorAll('.mention-item') : [];
    items.forEach(function (el, i) {
        el.classList.toggle('active', i === mentionActive);
    });
}

function chooseMention(i) {
    var item = mentionItems[i];
    if (!item) { closeMentionMenu(); return; }
    var ta = document.getElementById('chatInput');
    var ctx = getMentionContext(ta);
    if (!ctx) { closeMentionMenu(); return; }
    var insert = '@' + item.path;
    if (item.type === 'dir') insert += '/';
    var pos = ta.selectionStart;
    ta.value = ta.value.slice(0, ctx.at) + insert + ta.value.slice(pos);
    var caret = ctx.at + insert.length;
    ta.selectionStart = ta.selectionEnd = caret;
    closeMentionMenu();
    ta.focus();
    autoResize(ta);
    if (item.type === 'dir') handleMentionInput();
}

function closeMentionMenu() {
    if (mentionMenu) { mentionMenu.remove(); mentionMenu = null; }
    mentionItems = [];
    mentionActive = -1;
}

function scrollToBottom(force) {
    var el = document.getElementById('messages');
    if (force || !userScrolled) {
        el.scrollTop = el.scrollHeight;
    }
}

function initScrollTracking() {
    var el = document.getElementById('messages');
    el.addEventListener('scroll', function () {
        var distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
        userScrolled = distFromBottom > 80;
    });
}

// ─── Setup Wizard ───────────────────────────────────────────────────────────
function selectProvider(el) {
    document.querySelectorAll('.provider-option').forEach(function (o) { o.classList.remove('active'); });
    el.classList.add('active');
    setupState.provider = el.dataset.provider;
    setupState.key = '';
    setupState.model = '';
    setupState.baseUrl = setupState.provider === 'lmstudio' ? 'http://localhost:1234/v1' : '';
    document.getElementById('btnNext1').disabled = false;
}

function prepareKeyStep() {
    var p = setupState.provider;
    var isLM = p === 'lmstudio';
    var isCustom = p === 'custom-openai';
    var isCustomAnth = p === 'custom-anthropic';
    var title = document.getElementById('keyStepTitle');
    var sub = document.getElementById('keyStepSubtitle');
    var guide = document.getElementById('providerGuide');
    var baseWrap = document.getElementById('baseUrlWrap');
    var apiKey = document.getElementById('apiKey');
    var baseUrl = document.getElementById('baseUrl');
    document.getElementById('keyStatus').innerHTML = '';
    baseWrap.style.display = (isLM || isCustom || isCustomAnth) ? '' : 'none';
    guide.style.display = (isLM || isCustom || isCustomAnth) ? '' : 'none';
    apiKey.parentElement.style.display = isLM ? 'none' : '';
    apiKey.placeholder = isLM ? '' : 'sk-...';
    baseUrl.value = isLM ? 'http://localhost:1234/v1' : (setupState.baseUrl || '');
    title.textContent = isLM ? 'Connect LM Studio' : isCustomAnth ? 'Connect Anthropic API' : isCustom ? 'Connect Custom API' : 'Enter API Key';
    sub.textContent = isLM
        ? 'LM Studio must be running before verification'
        : isCustomAnth
            ? 'Enter your Anthropic-compatible API endpoint'
            : isCustom
                ? 'Enter your OpenAI-compatible endpoint details'
                : 'Paste your provider API key below';
    guide.innerHTML = isLM
        ? 'In LM Studio, load a model, open <strong>Developer &gt; Local Server</strong>, then start the server. The default OpenAI-compatible base URL is <strong>http://localhost:1234/v1</strong>.'
        : isCustomAnth
            ? 'Enter the Anthropic-compatible base URL (without trailing slash). The dashboard will use it for /v1/messages.'
            : 'Use the provider base URL that already includes <strong>/v1</strong>. This setup checks <strong>/models</strong> and then uses the same URL for chat requests.';
}

function goStep(n) {
    for (var i = 1; i <= 4; i++) {
        document.getElementById('sec' + i).classList.toggle('visible', i === n);
        var s = document.getElementById('step' + i);
        s.classList.remove('active', 'done');
        if (i < n) s.classList.add('done');
        if (i === n) s.classList.add('active');
    }
    if (n === 2 && setupState.provider === 'ollama') goStep(3);
    if (n === 2) prepareKeyStep();
    if (n === 3) initModelStep();
    if (n === 4) initConfirmStep();
}

async function verifyKey() {
    var isLM = setupState.provider === 'lmstudio';
    var isCustom = setupState.provider === 'custom-openai';
    var isCustomAnth = setupState.provider === 'custom-anthropic';
    var key = isLM ? 'lm-studio' : (document.getElementById('apiKey').value.trim() || (isCustom ? 'not-needed' : ''));
    var baseUrlInput = document.getElementById('baseUrl');
    var baseUrl = (baseUrlInput ? baseUrlInput.value : '').trim().replace(/\/+$/, '');
    if ((isLM || isCustom || isCustomAnth) && !baseUrl) { showKeyStatus('Base URL cannot be empty', 'error'); return; }
    if (!key) { showKeyStatus('API key cannot be empty', 'error'); return; }
    setupState.key = key;
    setupState.baseUrl = baseUrl;
    showKeyStatus('<div class="spinner"></div> Verifying...', 'loading');
    document.getElementById('btnVerify').disabled = true;
    try {
        var res = await fetch(API + '/api/verify-key', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider: setupState.provider, key: key, baseUrl: baseUrl })
        });
        var d = await res.json();
        if (d.valid) {
            showKeyStatus('\u2713 Verified', 'success');
            setTimeout(function () { goStep(3); }, 600);
        } else if (isCustom) {
            showKeyStatus('Could not verify /models. You can still enter the model manually.', 'error');
            setTimeout(function () { goStep(3); }, 900);
        } else {
            showKeyStatus('\u2717 Invalid or expired API key', 'error');
        }
    } catch (e) {
        console.error('verifyKey failed:', e);
        if (isCustom) {
            showKeyStatus('Verification failed. You can still enter the model manually.', 'error');
            setTimeout(function () { goStep(3); }, 900);
        } else {
            showKeyStatus('\u2717 Verification failed', 'error');
        }
    }
    document.getElementById('btnVerify').disabled = false;
}

function showKeyStatus(html, type) {
    var el = document.getElementById('keyStatus');
    var colors = { success: 'var(--success)', error: 'var(--error)', loading: 'var(--text2)' };
    el.style.color = colors[type] || 'var(--text2)';
    el.innerHTML = html;
}

// ─── Model Discovery ────────────────────────────────────────────────────────
async function initModelStep() {
    var isOR = setupState.provider === 'openrouter';
    var isOllama = setupState.provider === 'ollama';
    var isNvidia = setupState.provider === 'nvidia';
    var isDeepSeek = setupState.provider === 'deepseek';
    var isOpenAICompat = setupState.provider === 'lmstudio' || setupState.provider === 'custom-openai';
    var isAnthropicCompat = setupState.provider === 'custom-anthropic';
    document.getElementById('tierToggle').style.display = isOR ? '' : 'none';
    document.getElementById('modelSearchWrap').style.display = (isOR || isOllama || isNvidia || isDeepSeek || isOpenAICompat || isAnthropicCompat) ? '' : 'none';
    document.getElementById('modelSearch').style.display = isOllama ? 'none' : '';
    document.getElementById('manualModelWrap').style.display = '';
    if (isOR) fetchModels(setupState.tier);
    else if (isOllama) await fetchOllamaModels();
    else if (isNvidia) await fetchNvidiaModels();
    else if (isDeepSeek) await fetchDeepSeekModels();
    else if (isOpenAICompat) await fetchOpenAICompatibleModels();
    else if (isAnthropicCompat) await fetchAnthropicCompatibleModels();
    else { document.getElementById('manualModel').placeholder = 'Default: ' + (defaults[setupState.provider] || ''); }
}

async function fetchOllamaModels() {
    var listEl = document.getElementById('modelList');
    var loadEl = document.getElementById('modelLoading');
    listEl.innerHTML = ''; loadEl.style.display = 'flex';
    try {
        var res = await fetch(API + '/api/ollama/models');
        var d = await res.json();
        if ((d.models || []).length === 0) {
            listEl.innerHTML = '<div style="padding:14px;color:var(--text2);font-size:0.8rem">No local models found.<br><br>Close dashboard and run <strong>Setup_Local_Models.bat</strong> in the Windows folder first to download local models!</div>';
        } else {
            renderModels(d.models.map(function (m) { return m.id; }));
        }
    } catch (e) {
        console.error('fetchOllamaModels failed:', e);
        listEl.innerHTML = '<div style="padding:14px;color:var(--text2);font-size:0.8rem">Failed to load local models.</div>';
    }
    loadEl.style.display = 'none';
}

async function fetchNvidiaModels() {
    var listEl = document.getElementById('modelList');
    var loadEl = document.getElementById('modelLoading');
    var curated = [
        'moonshotai/kimi-k2-instruct', 'moonshotai/kimi-k2-thinking', 'z-ai/glm4.7',
        'deepseek-ai/deepseek-v3.2', 'deepseek-ai/deepseek-v3.1-terminus', 'stepfun-ai/step-3.5-flash',
        'mistralai/mistral-large-3-675b-instruct-2512', 'qwen/qwen3-coder-480b-a35b-instruct',
        'mistralai/mistral-nemotron', 'bytedance/seed-oss-36b-instruct', 'mistralai/mamba-codestral-7b-v0.1',
        'google/gemma-7b', 'tiiuae/falcon3-7b-instruct', 'minimaxai/minimax-m2.7'
    ];
    listEl.innerHTML = ''; loadEl.style.display = 'flex';
    try {
        var res = await fetch(API + '/api/nvidia/models');
        var d = await res.json();
        var liveModels = d.models || [];
        allModels = Array.from(new Set(curated.concat(liveModels)));
        renderModels(allModels);
    } catch (e) {
        console.error('fetchNvidiaModels failed:', e);
        allModels = curated;
        renderModels(allModels);
    }
    loadEl.style.display = 'none';
}

async function fetchDeepSeekModels() {
    var listEl = document.getElementById('modelList');
    var loadEl = document.getElementById('modelLoading');
    listEl.innerHTML = ''; loadEl.style.display = 'flex';
    try {
        var res = await fetch(API + '/api/deepseek/models', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key: setupState.key })
        });
        var d = await res.json();
        allModels = (d.models && d.models.length) ? d.models : ['deepseek-v4-flash', 'deepseek-v4-pro'];
        renderModels(allModels);
    } catch (e) {
        console.error('fetchDeepSeekModels failed:', e);
        allModels = ['deepseek-v4-flash', 'deepseek-v4-pro'];
        renderModels(allModels);
    }
    loadEl.style.display = 'none';
}

async function fetchOpenAICompatibleModels() {
    var listEl = document.getElementById('modelList');
    var loadEl = document.getElementById('modelLoading');
    listEl.innerHTML = ''; loadEl.style.display = 'flex';
    try {
        var res = await fetch(API + '/api/openai-compatible/models', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ baseUrl: setupState.baseUrl, key: setupState.key })
        });
        var d = await res.json();
        allModels = d.models || [];
        if (allModels.length) renderModels(allModels);
        else listEl.innerHTML = '<div style="padding:14px;color:var(--text2);font-size:0.8rem">No models returned. Enter the model name manually below.</div>';
    } catch (e) {
        console.error('fetchOpenAICompatibleModels failed:', e);
        allModels = [];
        listEl.innerHTML = '<div style="padding:14px;color:var(--text2);font-size:0.8rem">Failed to load models. Enter the model name manually below.</div>';
    }
    loadEl.style.display = 'none';
}

async function fetchAnthropicCompatibleModels() {
    var listEl = document.getElementById('modelList');
    var loadEl = document.getElementById('modelLoading');
    listEl.innerHTML = ''; loadEl.style.display = 'flex';
    try {
        var res = await fetch(API + '/api/anthropic/models', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ baseUrl: setupState.baseUrl, key: setupState.key })
        });
        var d = await res.json();
        allModels = d.models || [];
        if (allModels.length) renderModels(allModels);
        else listEl.innerHTML = '<div style="padding:14px;color:var(--text2);font-size:0.8rem">No models returned. Enter the model name manually.</div>';
    } catch (e) {
        console.error('fetchAnthropicCompatibleModels failed:', e);
        allModels = [];
        listEl.innerHTML = '<div style="padding:14px;color:var(--text2);font-size:0.8rem">Failed to load models. Enter the model name manually.</div>';
    }
    loadEl.style.display = 'none';
}

async function fetchModels(tier) {
    var listEl = document.getElementById('modelList');
    var loadEl = document.getElementById('modelLoading');
    listEl.innerHTML = ''; loadEl.style.display = 'flex';
    try {
        var res = await fetch(API + '/api/models?type=' + tier);
        var d = await res.json();
        allModels = d.models || [];
        renderModels(allModels);
    } catch (e) {
        console.error('fetchModels failed:', e);
        listEl.innerHTML = '<div style="padding:14px;color:var(--text2);font-size:0.8rem">Failed to load models.</div>';
    }
    loadEl.style.display = 'none';
}

function renderModels(models) {
    document.getElementById('modelList').innerHTML = models.map(function (m) {
        var activeClass = setupState.model === m ? ' active' : '';
        return '<div class="model-item' + activeClass + '" data-action="pickModel" data-model="' + escHtml(m) + '"><div class="dot"></div>' + escHtml(m) + '</div>';
    }).join('');
}

function pickModel(id, el) {
    setupState.model = id;
    document.querySelectorAll('.model-item').forEach(function (m) { m.classList.remove('active'); });
    if (el) el.classList.add('active');
}

function filterModels() {
    var q = document.getElementById('modelSearch').value.toLowerCase();
    renderModels(allModels.filter(function (m) { return m.toLowerCase().indexOf(q) !== -1; }));
}

function switchTier(tier, btn) {
    setupState.tier = tier;
    setupState.model = '';
    document.querySelectorAll('.tier-btn').forEach(function (b) { b.classList.remove('active'); });
    btn.classList.add('active');
    fetchModels(tier);
}

// ─── Confirm & Save ─────────────────────────────────────────────────────────
function initConfirmStep() {
    document.getElementById('confirmProvider').textContent = providerNames[setupState.provider] || setupState.provider;
    var model = setupState.model || (document.getElementById('manualModel') ? document.getElementById('manualModel').value : '') || defaults[setupState.provider] || '';
    setupState.model = model;
    document.getElementById('confirmModel').textContent = model || '\u2014';
    document.getElementById('confirmKey').textContent = setupState.key
        ? setupState.key.slice(0, 8) + '...' + setupState.key.slice(-4)
        : 'None (Local)';
}

// ─── Data-driven saveConfig ─────────────────────────────────────────────────
async function saveConfig() {
    var btn = document.getElementById('btnSave');
    btn.disabled = true;
    btn.innerHTML = '<div class="spinner"></div> Saving...';

    var pc = PROVIDER_CONFIGS[setupState.provider] || {};
    var config = {};

    // Copy baseline config
    for (var key in pc) {
        if (Object.prototype.hasOwnProperty.call(pc, key)) {
            config[key] = pc[key];
        }
    }

    // Override with user-provided values
    if (!pc.OPENAI_API_KEY && setupState.key) {
        config.OPENAI_API_KEY = setupState.key;
    }
    if (!pc.OPENAI_BASE_URL && setupState.baseUrl) {
        config.OPENAI_BASE_URL = setupState.baseUrl;
    }
    if (!pc.OPENAI_BASE_URL && setupState.provider === 'lmstudio') {
        config.OPENAI_BASE_URL = setupState.baseUrl || 'http://localhost:1234/v1';
    }

    // Provider-specific keys
    if (setupState.provider === 'gemini') {
        config.GEMINI_API_KEY = setupState.key;
    } else if (setupState.provider === 'anthropic') {
        config.ANTHROPIC_API_KEY = setupState.key;
    }

    config.OPENAI_MODEL = setupState.model;
    config.AI_DISPLAY_MODEL = setupState.model;

    try {
        await fetch(API + '/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        showToast('Configuration saved', 'success');
        await loadConfig();
        loadProfiles();
        switchPage('chat');
    } catch (e) {
        console.error('saveConfig failed:', e);
        showToast('Failed to save', 'error');
    }
    btn.disabled = false;
    btn.innerHTML = 'Save Configuration';
}

// ─── Configuration Profiles ─────────────────────────────────────────────────
async function loadProfiles() {
    try {
        var res = await fetch(API + '/api/profiles');
        var data = await res.json();
        var profiles = data.profiles || [];
        var el = document.getElementById('profileList');
        if (!el) return;
        if (!profiles.length) {
            el.innerHTML = '<div style="padding:12px 14px;color:var(--text3);font-size:0.78rem">No saved profiles yet. Configure a provider and click <strong>Save Current</strong>.</div>';
            return;
        }
        el.innerHTML = profiles.map(function (p) {
            var name = escHtml(p.name);
            return '<div class="profile-item" id="prof_' + name + '">'
                + '<div class="prof-info" data-action="loadProfile" data-name="' + escHtml(p.name) + '" title="Click to apply">'
                + '<div class="prof-name">' + name + '</div>'
                + '<div class="prof-meta"><span>' + escHtml(p.provider || '?') + '</span><span>\u00b7</span><span>' + escHtml(p.model || '?') + '</span><span>\u00b7</span><span>' + relativeTime(p.modified) + '</span></div>'
                + '</div>'
                + '<div class="prof-actions">'
                + '<button class="prof-btn load" data-action="loadProfile" data-name="' + escHtml(p.name) + '" title="Apply this configuration">Load</button>'
                + '<button class="prof-btn del" data-action="deleteProfile" data-name="' + escHtml(p.name) + '" title="Delete this profile">\u2715</button>'
                + '</div>'
                + '</div>';
        }).join('');
    } catch (e) {
        console.error('loadProfiles failed:', e);
    }
}

async function saveProfile() {
    var name = prompt('Enter a name for this configuration profile:', cfg.AI_DISPLAY_MODEL || cfg.OPENAI_MODEL || 'My Config');
    if (!name || !name.trim()) return;
    try {
        var res = await fetch(API + '/api/profiles/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name.trim() })
        });
        var d = await res.json();
        if (d.success) { showToast('Profile "' + name.trim() + '" saved', 'success'); loadProfiles(); }
        else showToast(d.error || 'Failed to save profile', 'error');
    } catch (e) {
        console.error('saveProfile failed:', e);
        showToast('Failed to save profile', 'error');
    }
}

async function loadProfile(name) {
    if (!confirm('Load profile "' + name + '"? This will replace your current configuration.')) return;
    try {
        var res = await fetch(API + '/api/profiles/load', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name })
        });
        var d = await res.json();
        if (d.success) {
            showToast('Profile "' + name + '" loaded', 'success');
            await loadConfig();
            loadProfiles();
            switchPage('chat');
        } else showToast(d.error || 'Profile not found', 'error');
    } catch (e) {
        console.error('loadProfile failed:', e);
        showToast('Failed to load profile', 'error');
    }
}

async function deleteProfile(name) {
    if (!confirm('Delete profile "' + name + '"? This cannot be undone.')) return;
    try {
        var res = await fetch(API + '/api/profiles/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name })
        });
        var d = await res.json();
        if (d.success) { showToast('Profile "' + name + '" deleted', 'success'); loadProfiles(); }
        else showToast(d.error || 'Failed to delete', 'error');
    } catch (e) {
        console.error('deleteProfile failed:', e);
        showToast('Failed to delete profile', 'error');
    }
}

// ─── System Prompt Editor ────────────────────────────────────────────────────

var DEFAULT_PROMPT = 'You are a powerful AI coding agent running in a web dashboard. You have access to tools: write_file (max 10MB), append_file (append), write_file_chunk (write at offset), read_file (max 512KB), list_directory, execute_command, search_files. The current working directory is: {work_dir}. Use tools to actually perform actions - do not just describe what to do.';

async function loadSystemPrompt() {
    try {
        var res = await fetch(API + '/api/system-prompt');
        var d = await res.json();
        document.getElementById('systemPromptEditor').value = d.prompt || '';
        document.getElementById('defaultPromptRef').value = DEFAULT_PROMPT;
    } catch (e) {
        console.error('loadSystemPrompt failed:', e);
    }
}

async function saveSystemPrompt() {
    var prompt = document.getElementById('systemPromptEditor').value;
    try {
        await fetch(API + '/api/system-prompt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt: prompt })
        });
        var st = document.getElementById('sysPromptStatus');
        st.textContent = '\u2713 Saved';
        st.style.color = 'var(--success)';
        setTimeout(function () { st.textContent = ''; }, 2000);
    } catch (e) {
        console.error('saveSystemPrompt failed:', e);
        showToast('Failed to save system prompt', 'error');
    }
}

async function resetSystemPrompt() {
    if (!confirm('Reset system prompt to default? This will clear your custom instructions.')) return;
    document.getElementById('systemPromptEditor').value = '';
    await saveSystemPrompt();
}

// ─── Project Prompt Editor ───────────────────────────────────────────────────

async function loadProjectPrompt() {
    try {
        var res = await fetch(API + '/api/project-prompt');
        var d = await res.json();
        document.getElementById('projectPromptEditor').value = d.prompt || '';
    } catch (e) {
        console.error('loadProjectPrompt failed:', e);
    }
}

async function saveProjectPrompt() {
    var prompt = document.getElementById('projectPromptEditor').value;
    try {
        await fetch(API + '/api/project-prompt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt: prompt })
        });
        var st = document.getElementById('projPromptStatus');
        st.textContent = '\u2713 Saved';
        st.style.color = 'var(--success)';
        setTimeout(function () { st.textContent = ''; }, 2000);
    } catch (e) {
        console.error('saveProjectPrompt failed:', e);
        showToast('Failed to save project prompt', 'error');
    }
}

async function resetProjectPrompt() {
    if (!confirm('Clear project instructions?')) return;
    document.getElementById('projectPromptEditor').value = '';
    await saveProjectPrompt();
}

// ─── System Info ────────────────────────────────────────────────────────────
function formatBytes(bytes) {
    if (bytes === undefined || bytes === null) return '\u2014';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
    return (bytes / 1073741824).toFixed(2) + ' GB';
}

async function loadSystemInfo() {
    try {
        var res = await fetch(API + '/api/system');
        var d = await res.json();
        document.getElementById('sysPlatform').textContent = d.platform || '\u2014';
        document.getElementById('sysArch').textContent = d.arch || '\u2014';

        var info = getProviderInfo(cfg);
        document.getElementById('sysProviderName').textContent = info.pName;
        document.getElementById('sysProviderURL').textContent = info.providerURL;
        document.getElementById('sysProviderModel').textContent = info.model;

        if (d.memoryTotal !== undefined && d.memoryTotal !== null) {
            document.getElementById('sysMemTotal').textContent = formatBytes(d.memoryTotal);
            document.getElementById('sysMemUsed').textContent = formatBytes(d.memoryUsed);
            document.getElementById('sysMemFree').textContent = formatBytes(d.memoryTotal - d.memoryUsed);
            document.getElementById('sysCpuLoad').textContent = (d.cpuLoad !== undefined && d.cpuLoad !== null)
                ? d.cpuLoad.toFixed(1) + '%'
                : '\u2014';
        } else {
            document.getElementById('sysMemTotal').textContent = '\u2014';
            document.getElementById('sysMemUsed').textContent = '\u2014';
            document.getElementById('sysMemFree').textContent = '\u2014';
            document.getElementById('sysCpuLoad').textContent = '\u2014';
        }

        document.getElementById('sysGit').innerHTML = d.hasGit
            ? '<span class="badge badge-success">' + (d.portableGit ? 'USB' : 'System') + '</span>'
            : '<span class="badge badge-error">Not found</span>';
        document.getElementById('sysPython').innerHTML = d.hasPython
            ? '<span class="badge badge-success">' + (d.portablePython ? 'USB' : 'System') + '</span>'
            : '<span class="badge badge-error">Not found</span>';

        if (d.ollamaInstalled) {
            document.getElementById('cardOllama').style.display = 'block';
            try {
                var oRes = await fetch(API + '/api/ollama/status');
                var oData = await oRes.json();
                document.getElementById('sysOllamaStatus').innerHTML = oData.running
                    ? '<span class="badge badge-success">Running</span>'
                    : '<span class="badge badge-error">Stopped</span>';
                var actionsEl = document.getElementById('sysOllamaActions');
                if (oData.running) {
                    actionsEl.innerHTML = '<button class="btn btn-outline" style="padding:5px 12px;font-size:0.75rem" data-action="toggleOllama" data-ollama-action="stop">Stop</button>';
                } else {
                    actionsEl.innerHTML = '<button class="btn btn-primary" style="padding:5px 12px;font-size:0.75rem" data-action="toggleOllama" data-ollama-action="start">Start</button>';
                }
                var mRes = await fetch(API + '/api/ollama/models');
                var mData = await mRes.json();
                if (mData.models && mData.models.length > 0) {
                    document.getElementById('sysOllamaModels').innerHTML = '<strong>Installed Models:</strong><br>'
                        + mData.models.map(function (m) {
                            return '<div style="margin-top:6px;display:flex;align-items:center;gap:6px"><span>\u2022 ' + escHtml(m.name) + '</span> <span class="badge" style="background:rgba(255,255,255,0.06);color:var(--text2)">' + (m.label || 'Local') + '</span></div>';
                        }).join('');
                } else {
                    document.getElementById('sysOllamaModels').innerHTML = 'No local models installed.';
                }
            } catch (e) {
                console.error('loadSystemInfo ollama failed:', e);
            }
        } else {
            document.getElementById('cardOllama').style.display = 'none';
        }

        var container = document.getElementById('disksContainer');
        if (d.disks && d.disks.length) {
            var html = '<table style="width:100%;font-size:0.82rem;border-collapse:collapse;">'
                + '<thead><tr><th style="text-align:left;">Drive</th><th style="text-align:right;">Total</th><th style="text-align:right;">Free</th><th style="text-align:right;">Used %</th></tr></thead><tbody>';
            d.disks.forEach(function (disk) {
                var total = disk.size / (1024 * 1024 * 1024);
                var free = disk.freespace / (1024 * 1024 * 1024);
                var used = total - free;
                var percent = total > 0 ? (used / total * 100).toFixed(1) : 0;
                html += '<tr>'
                    + '<td>' + escHtml(disk.caption) + '</td>'
                    + '<td style="text-align:right;">' + total.toFixed(2) + ' GB</td>'
                    + '<td style="text-align:right;">' + free.toFixed(2) + ' GB</td>'
                    + '<td style="text-align:right;">' + percent + '%</td>'
                    + '</tr>';
            });
            html += '</tbody></table>';
            container.innerHTML = html;
        } else {
            container.innerHTML = '<div style="padding:10px 0;color:var(--text2);font-size:0.82rem">No drive data available</div>';
        }

        loadLogs();
    } catch (e) {
        console.error('loadSystemInfo failed:', e);
        showToast('Failed to load system info', 'error');
    }
}

// ─── Logs ───────────────────────────────────────────────────────────────────
async function loadLogs() {
    try {
        var res = await fetch(API + '/api/logs');
        var data = await res.json();
        var logs = data.logs;
        var el = document.getElementById('logList');
        if (!logs.length) {
            el.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text2);font-size:0.8rem">No logs found</div>';
            return;
        }
        el.innerHTML = logs.map(function (l) {
            return '<div class="log-entry" data-action="viewLog" data-path="' + escHtml(l.path) + '"><span class="log-name">' + escHtml(l.name) + '</span><span class="log-meta">' + (l.size / 1024).toFixed(1) + ' KB \u00b7 ' + new Date(l.modified).toLocaleDateString() + '</span></div>';
        }).join('');
    } catch (e) {
        console.error('loadLogs failed:', e);
    }
}

async function viewLog(path) {
    var viewer = document.getElementById('logViewer');
    viewer.style.display = 'block';
    viewer.textContent = 'Loading...';
    try {
        var res = await fetch(API + '/api/logs/read?path=' + encodeURIComponent(path));
        var data = await res.json();
        viewer.textContent = data.content || '(empty)';
    } catch (e) {
        console.error('viewLog failed:', e);
        viewer.textContent = 'Failed to read file.';
    }
}

// ─── Ollama Control ─────────────────────────────────────────────────────────
async function toggleOllama(action) {
    try {
        await fetch(API + '/api/ollama/' + action, { method: 'POST' });
        showToast('Ollama ' + (action === 'start' ? 'started' : 'stopped'), 'success');
        setTimeout(loadSystemInfo, 1500);
    } catch (e) {
        console.error('toggleOllama failed:', e);
        showToast('Failed to ' + action + ' Ollama', 'error');
    }
}

// ─── Actions ────────────────────────────────────────────────────────────────
async function launchAI(mode) {
    try {
        await fetch(API + '/api/launch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: mode })
        });
        showToast('AI launched in ' + mode + ' mode', 'success');
    } catch (e) {
        console.error('launchAI failed:', e);
        showToast('Failed to launch', 'error');
    }
}

function exportConfig() {
    window.open(API + '/api/config/export', '_blank');
}

async function importConfig(event) {
    var file = event.target.files[0];
    if (!file) return;
    var text = await file.text();
    try {
        await fetch(API + '/api/config/import', {
            method: 'POST',
            headers: { 'Content-Type': 'text/plain' },
            body: text
        });
        showToast('Config imported', 'success');
        loadConfig();
    } catch (e) {
        console.error('importConfig failed:', e);
        showToast('Import failed', 'error');
    }
    event.target.value = '';
}

async function shutdownServer() {
    if (!confirm('Shut down the server and close this page?')) return;
    try {
        await fetch(API + '/api/shutdown', { method: 'POST' });
    } catch (e) {
        // Server may close before response — that's expected
    }
    window.close();
    // Fallback if window.close() is blocked (not opened by script)
    setTimeout(function () {
        document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:Inter,system-ui,sans-serif;background:#0f1117;color:#e4e7ef;font-size:1.2rem">Server stopped. You may close this tab.</div>';
    }, 500);
}

// ─── Updates ────────────────────────────────────────────────────────────────
async function checkUpdates() {
    document.getElementById('updateCurrent').textContent = '...';
    document.getElementById('updateLatest').textContent = '...';
    document.getElementById('updateStatus').innerHTML = '<div style="display:flex;align-items:center;gap:8px;font-size:0.8rem;color:var(--text2)"><div class="spinner"></div> Checking...</div>';
    try {
        var res = await fetch(API + '/api/updates');
        var d = await res.json();
        document.getElementById('updateCurrent').textContent = d.current;
        document.getElementById('updateLatest').textContent = d.latest;
        if (d.updateAvailable) {
            document.getElementById('updateStatus').innerHTML = '<span class="badge badge-warning">Update available</span>';
            document.getElementById('btnUpdate').style.display = '';
        } else {
            document.getElementById('updateStatus').innerHTML = '<span class="badge badge-success">Up to date</span>';
            document.getElementById('btnUpdate').style.display = 'none';
        }
    } catch (e) {
        console.error('checkUpdates failed:', e);
        document.getElementById('updateStatus').innerHTML = '<span class="badge badge-error">Check failed</span>';
    }
}

async function installUpdate() {
    var btn = document.getElementById('btnUpdate');
    btn.disabled = true;
    btn.innerHTML = '<div class="spinner"></div> Updating...';
    try {
        var res = await fetch(API + '/api/updates/install', { method: 'POST' });
        var d = await res.json();
        if (d.success) { showToast('Updated to v' + d.version, 'success'); checkUpdates(); }
        else showToast('Update failed', 'error');
    } catch (e) {
        console.error('installUpdate failed:', e);
        showToast('Update failed', 'error');
    }
    btn.disabled = false;
    btn.innerHTML = 'Update Now';
}

// ─── Event Delegation (replaces inline onclick with data-* attributes) ─────
document.addEventListener('click', function (e) {
    var el = e.target.closest('[data-action]');
    if (!el) return;
    var action = el.dataset.action;
    var id = el.dataset.id;
    var name = el.dataset.name;
    var model = el.dataset.model;
    var path = el.dataset.path;
    var title = el.dataset.title;
    var approved = el.dataset.approved;
    var ollamaAction = el.dataset.ollamaAction;

    e.stopPropagation();

    switch (action) {
        case 'openChat':
            if (id) openChatById(id);
            break;
        case 'deleteChat':
            if (id && title) confirmDeleteChat(id, title);
            break;
        case 'loadProfile':
            if (name) loadProfile(name);
            break;
        case 'deleteProfile':
            if (name) deleteProfile(name);
            break;
        case 'pickModel':
            if (model) pickModel(model, el);
            break;
        case 'viewLog':
            if (path) viewLog(path);
            break;
        case 'toggleOllama':
            if (ollamaAction) toggleOllama(ollamaAction);
            break;
        case 'approve':
            if (id && approved !== undefined) approveToolCall(id, approved === 'true', el);
            break;
        case 'copyAssistant':
            copyAssistantMessage(messageIndex(el));
            break;
        case 'saveAssistant':
            saveAssistantMessage(messageIndex(el), el);
            break;
    }
});

// ─── Init ───────────────────────────────────────────────────────────────────
(function init() {
    var saved = localStorage.getItem('theme');
    if (saved) document.documentElement.dataset.theme = saved;
    loadConfig();
    loadChatList().then(function () {});
    initScrollTracking();
    loadWorkDir();
    var savedAgent = localStorage.getItem('agentMode');
    if (savedAgent === 'true') {
        agentMode = true;
        document.getElementById('agentToggle').checked = true;
        document.getElementById('workdirBar').style.display = 'flex';
    }
    updateInputToolbar();
    updateModeToggle();
    document.getElementById('chatInput').addEventListener('input', handleMentionInput);
    var lastChatId = localStorage.getItem('activeChatId');
    if (lastChatId) {
        openChatById(lastChatId).catch(function (e) {
            console.error('init openChatById failed:', e);
        });
    }
})();
