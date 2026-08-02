"""Patch index.html to add configuration profile management UI."""
import sys

with open('dashboard/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

print(f"Read {len(html)} bytes", flush=True)

# ── 1. CSS: add profile styles before </style> ──
profile_css = '''
/* Profile list */
.profile-list{max-height:260px;overflow-y:auto}
.profile-item{display:flex;align-items:center;gap:10px;padding:11px 14px;border-bottom:1px solid var(--border);font-size:0.8rem;cursor:pointer;transition:background 0.15s}
.profile-item:last-child{border-bottom:none}
.profile-item:hover{background:var(--surface2)}
.profile-item.active{background:var(--accent-subtle);border-left:3px solid var(--accent)}
.profile-item .prof-info{flex:1;min-width:0}
.profile-item .prof-name{font-weight:600;font-size:0.82rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.profile-item .prof-meta{font-size:0.67rem;color:var(--text2);margin-top:1px;display:flex;gap:8px}
.profile-item .prof-actions{display:flex;gap:4px;flex-shrink:0}
.profile-item .prof-btn{background:none;border:1px solid var(--border);color:var(--text2);cursor:pointer;font-size:0.68rem;padding:3px 8px;border-radius:5px;font-family:inherit;transition:all 0.15s}
.profile-item .prof-btn:hover{border-color:var(--text2);color:var(--text)}
.profile-item .prof-btn.load:hover{border-color:var(--accent);color:var(--accent)}
.profile-item .prof-btn.del:hover{border-color:var(--error);color:var(--error)}
'''

if '</style>' in html:
    html = html.replace('</style>', profile_css + '\n</style>')
    print("1. CSS injected", flush=True)
else:
    print("ERROR: </style> not found!", flush=True)
    sys.exit(1)

# ── 2. HTML: add profiles card before wizard steps ──
profiles_card = '''        <!-- Configuration Profiles -->
        <div class="card" id="profilesCard">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
            <div><h2 style="margin-bottom:2px">Configuration Profiles</h2><p class="subtitle" style="margin-bottom:0">Save and switch between provider configurations</p></div>
            <button class="btn btn-outline" onclick="saveProfile()" style="flex-shrink:0">Save Current</button>
          </div>
          <div class="profile-list" id="profileList">
            <div style="padding:12px 14px;color:var(--text3);font-size:0.78rem">Loading profiles...</div>
          </div>
        </div>

'''

marker = '<div class="step active" id="step1">'
if marker in html:
    html = html.replace(
        '        <div class="steps">\n          ' + marker,
        profiles_card + '        <div class="steps">\n          ' + marker
    )
    print("2. HTML card injected", flush=True)
else:
    print("ERROR: step1 marker not found!", flush=True)
    sys.exit(1)

# ── 3. JS: add profile functions ──
profile_js = '''
// ─── Configuration Profiles ──────────────────────────────────────────────────
async function loadProfiles() {
  try {
    const res = await fetch(`${API}/api/profiles`);
    const data = await res.json();
    const profiles = data.profiles || [];
    const el = document.getElementById('profileList');
    if (!el) return;
    if (!profiles.length) {
      el.innerHTML = '<div style="padding:12px 14px;color:var(--text3);font-size:0.78rem">No saved profiles yet. Configure a provider and click <strong>Save Current</strong>.</div>';
      return;
    }
    el.innerHTML = profiles.map(p => {
      const en = escHtml(p.name);
      return `<div class="profile-item" id="prof_${en}">
        <div class="prof-info" onclick="loadProfile('${en.replace(/'/g, "\\\\'")}')" title="Click to apply">
          <div class="prof-name">${en}</div>
          <div class="prof-meta"><span>${escHtml(p.provider||'?')}</span><span>·</span><span>${escHtml(p.model||'?')}</span><span>·</span><span>${relativeTime(p.modified)}</span></div>
        </div>
        <div class="prof-actions">
          <button class="prof-btn load" onclick="loadProfile('${en.replace(/'/g, "\\\\'")}')" title="Apply this configuration">Load</button>
          <button class="prof-btn del" onclick="deleteProfile('${en.replace(/'/g, "\\\\'")}')" title="Delete this profile">✕</button>
        </div>
      </div>`;
    }).join('');
  } catch {}
}

async function saveProfile() {
  const name = prompt('Enter a name for this configuration profile:', cfg.AI_DISPLAY_MODEL || cfg.OPENAI_MODEL || 'My Config');
  if (!name || !name.trim()) return;
  try {
    const res = await fetch(`${API}/api/profiles/save`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim() })
    });
    const d = await res.json();
    if (d.success) { showToast('Profile "' + name.trim() + '" saved', 'success'); loadProfiles(); }
    else showToast(d.error || 'Failed to save profile', 'error');
  } catch { showToast('Failed to save profile', 'error'); }
}

async function loadProfile(name) {
  if (!confirm('Load profile "' + name + '"? This will replace your current configuration.')) return;
  try {
    const res = await fetch(`${API}/api/profiles/load`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name })
    });
    const d = await res.json();
    if (d.success) {
      showToast('Profile "' + name + '" loaded', 'success');
      await loadConfig();
      loadProfiles();
      switchPage('chat');
    } else showToast(d.error || 'Profile not found', 'error');
  } catch { showToast('Failed to load profile', 'error'); }
}

async function deleteProfile(name) {
  if (!confirm('Delete profile "' + name + '"? This cannot be undone.')) return;
  try {
    const res = await fetch(`${API}/api/profiles/delete`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name })
    });
    const d = await res.json();
    if (d.success) { showToast('Profile "' + name + '" deleted', 'success'); loadProfiles(); }
    else showToast(d.error || 'Failed to delete', 'error');
  } catch { showToast('Failed to delete profile', 'error'); }
}
'''

sys_marker = "// ─── System Info "
if sys_marker in html:
    html = html.replace(sys_marker, profile_js + '\n' + sys_marker)
    print("3. JS functions injected", flush=True)
else:
    print("ERROR: System Info marker not found!", flush=True)
    sys.exit(1)

# ── 4. Call loadProfiles() when switching to setup page ──
old = "if (name === 'system') loadSystemInfo();"
new = "if (name === 'setup') loadProfiles();\n  if (name === 'system') loadSystemInfo();"
if old in html:
    html = html.replace(old, new)
    print("4. switchPage hook injected", flush=True)
else:
    print("ERROR: switchPage hook marker not found!", flush=True)
    sys.exit(1)

# ── 5. Refresh profiles after saving config ──
old2 = "showToast('Configuration saved','success');\n    await loadConfig();\n    switchPage('chat');"
new2 = "showToast('Configuration saved','success');\n    await loadConfig();\n    loadProfiles();\n    switchPage('chat');"
if old2 in html:
    html = html.replace(old2, new2)
    print("5. saveConfig refresh injected", flush=True)
else:
    print("ERROR: saveConfig marker not found!", flush=True)
    sys.exit(1)

with open('dashboard/index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f"SUCCESS: Written {len(html)} bytes", flush=True)
