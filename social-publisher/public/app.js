(() => {
  const $ = id => document.getElementById(id);

  const PLATFORMS = {
    instagram: {
      name: 'Instagram',
      handle: '@yourbrand',
      hint: 'Image required · max 2,200 chars · 30 #tags',
      maxChars: 2200,
      maxHashtags: 30,
      requiresImage: true,
      iconClass: 'icon-instagram',
      svg: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="20" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1"/></svg>'
    },
    facebook: {
      name: 'Facebook',
      handle: 'Your Brand Page',
      hint: 'Page post · text, links & photo',
      maxChars: 63206,
      requiresImage: false,
      iconClass: 'icon-facebook',
      svg: '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M14 13.5h2.5l1-4H14v-2c0-1.03 0-2 2-2h1.5V2.14c-.326-.043-1.557-.14-2.857-.14C11.928 2 10 3.657 10 6.7v2.8H7v4h3V22h4v-8.5z"/></svg>'
    },
    gmb: {
      name: 'Google Business Profile',
      handle: 'Your Storefront · Google',
      hint: 'Local post + CTA · max 1,500 chars',
      maxChars: 1500,
      requiresImage: false,
      iconClass: 'icon-gmb',
      svg: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l2-5h14l2 5"/><path d="M3 9a3 3 0 0 0 6 0 3 3 0 0 0 6 0 3 3 0 0 0 6 0"/><path d="M5 12v8h14v-8"/></svg>'
    },
    linkedin: {
      name: 'LinkedIn',
      handle: 'Your Company · Followers',
      hint: 'Professional feed · max 3,000 chars',
      maxChars: 3000,
      requiresImage: false,
      iconClass: 'icon-linkedin',
      svg: '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M6.94 5a2 2 0 1 1-4-.002 2 2 0 0 1 4 .002zM7 8.48H3V21h4V8.48zm6.32 0H9.34V21h3.94v-6.57c0-3.66 4.77-4 4.77 0V21H22v-7.93c0-6.17-7.06-5.94-8.72-2.91l.04-1.68z"/></svg>'
    }
  };

  const EMOJI_CATEGORIES = {
    'Festivals & Party': ['🎉', '🪔', '✨', '🎊', '🎂', '🎁', '🥳', '🥂', '🎆', '🎇', '🕯️', '🌟', '🎄', '🌙', '💐', '🎈'],
    'Promo & Shop': ['🔥', '📣', '🛍️', '💸', '🏷️', '⚡', '🚀', '💎', '🛒', '📦', '✅', '👉', '⏰', '💯', '🏆', '🆕'],
    'Warmth & Smileys': ['😊', '🙏', '❤️', '🧡', '💛', '💚', '💙', '🤝', '👏', '🙌', '🤩', '😍', '🌞', '🌈', '☕', '🌻']
  };

  const HASHTAG_PACKS = {
    Promotional: ['#FlashSale', '#LimitedOffer', '#ShopNow', '#ExclusiveDeal', '#SaveBig'],
    Festival: ['#FestivalWishes', '#SeasonGreetings', '#Celebration', '#JoyAndPeace', '#FestiveVibes'],
    Announcement: ['#Announcement', '#BigNews', '#NowLive', '#NewLaunch', '#StayTuned'],
    Engagement: ['#SmallBusiness', '#Community', '#CustomerLove', '#BehindTheScenes']
  };

  const CTA_LABELS = {
    LEARN_MORE: 'Learn more',
    SHOP: 'Shop',
    ORDER: 'Order online',
    BOOK: 'Book',
    SIGN_UP: 'Sign up'
  };

  const state = {
    category: 'promotional',
    editingDraftId: null,
    templates: [],
    selectedPlatforms: ['instagram', 'facebook', 'gmb', 'linkedin'],
    activePreviewTab: 'all',
    image: null,
    imageOriginalName: null,
    imageUrl: null,
    config: { mode: 'sandbox', publicBaseUrl: '', platforms: {}, fields: {} },
    simulateFailures: new Set(),
    activeEmojiTab: Object.keys(EMOJI_CATEGORIES)[0],
    lastPublishPost: null,
    historyPosts: []
  };

  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));

  const quill = new Quill('#editor', {
    theme: 'snow',
    placeholder: 'Write your promotional offer, festival wish, or announcement… Use #hashtags, emojis, and links.',
    modules: {
      toolbar: [
        [{ header: [1, 2, false] }],
        ['bold', 'italic', 'underline', 'strike'],
        [{ list: 'ordered' }, { list: 'bullet' }],
        ['blockquote', 'link', 'clean']
      ]
    }
  });

  function getPlainText() {
    return quill.getText().replace(/\n$/, '').trim();
  }

  function extractHashtags(text) {
    const matches = text.match(/(^|[\s(])(#[a-zA-Z0-9_\u00C0-\u024F\u0900-\u097F]+)/g) || [];
    const set = new Set();
    matches.forEach(m => set.add(m.trim().replace(/^[(\s]+/, '')));
    return [...set];
  }

  function insertAtCursor(str) {
    quill.focus();
    const range = quill.getSelection(true) || { index: quill.getLength() - 1, length: 0 };
    quill.insertText(range.index, str);
    quill.setSelection(range.index + str.length);
  }

  function showError(msg) {
    const el = $('composer-error');
    if (!msg) {
      el.classList.add('hide');
      el.textContent = '';
      return;
    }
    el.textContent = msg;
    el.classList.remove('hide');
  }

  function formatBytes(bytes) {
    if (!bytes) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  }

  // Render Platforms
  function renderPlatforms() {
    const textLen = getPlainText().length;
    $('platform-list').innerHTML = Object.entries(PLATFORMS).map(([key, p]) => {
      const checked = state.selectedPlatforms.includes(key);
      const over = textLen > p.maxChars;
      const missingImg = key === 'instagram' && checked && !state.image;
      return `
        <label class="platform-card ${checked ? 'selected' : ''}">
          <input type="checkbox" value="${key}" ${checked ? 'checked' : ''}>
          <div class="platform-icon ${p.iconClass}">${p.svg}</div>
          <div class="platform-body">
            <div class="platform-title">
              <span>${p.name}</span>
            </div>
            <div class="platform-hint">${p.hint}</div>
            <div class="platform-meter ${over || missingImg ? 'over' : ''}">
              ${textLen.toLocaleString()} / ${p.maxChars.toLocaleString()} chars${missingImg ? ' · Image needed' : ''}
            </div>
          </div>
        </label>
      `;
    }).join('');

    $('platform-list').querySelectorAll('input[type="checkbox"]').forEach(cb => {
      cb.onchange = () => {
        if (cb.checked) {
          if (!state.selectedPlatforms.includes(cb.value)) state.selectedPlatforms.push(cb.value);
        } else {
          state.selectedPlatforms = state.selectedPlatforms.filter(x => x !== cb.value);
        }
        if (state.activePreviewTab !== 'all' && !state.selectedPlatforms.includes(state.activePreviewTab)) {
          state.activePreviewTab = 'all';
        }
        renderPlatforms();
        renderPreviews();
      };
    });
  }

  // Render Emoji Drawer
  function renderEmojis() {
    $('emoji-tabs').innerHTML = Object.keys(EMOJI_CATEGORIES).map(cat => `
      <button type="button" class="drawer-tab ${state.activeEmojiTab === cat ? 'active' : ''}" data-ecat="${cat}">${cat}</button>
    `).join('');

    $('emoji-tabs').querySelectorAll('button').forEach(btn => {
      btn.onclick = () => {
        state.activeEmojiTab = btn.dataset.ecat;
        renderEmojis();
      };
    });

    $('emoji-grid').innerHTML = EMOJI_CATEGORIES[state.activeEmojiTab].map(emoji => `
      <button type="button" class="emoji-btn" title="Insert ${emoji}">${emoji}</button>
    `).join('');

    $('emoji-grid').querySelectorAll('button').forEach(btn => {
      btn.onclick = () => insertAtCursor(btn.textContent);
    });
  }

  // Render Hashtag Packs
  function renderHashtagPacks() {
    $('hashtag-packs').innerHTML = Object.entries(HASHTAG_PACKS).map(([group, tags]) => `
      <div class="pack-row">
        <span class="pack-label">${group}</span>
        ${tags.map(t => `<button type="button" class="tag-btn" data-tag="${t}">${t}</button>`).join('')}
      </div>
    `).join('');

    $('hashtag-packs').querySelectorAll('button').forEach(btn => {
      btn.onclick = () => {
        const current = getPlainText();
        const prefix = current && !current.endsWith(' ') && !current.endsWith('\n') ? ' ' : '';
        insertAtCursor(`${prefix}${btn.dataset.tag} `);
      };
    });
  }

  function addCustomHashtag() {
    const input = $('custom-hashtag-input');
    const cleaned = input.value.trim().replace(/^#+/, '').replace(/\s+/g, '');
    if (!cleaned) return;
    const current = getPlainText();
    const prefix = current && !current.endsWith(' ') && !current.endsWith('\n') ? ' ' : '';
    insertAtCursor(`${prefix}#${cleaned} `);
    input.value = '';
  }

  // Live metrics & preview updates
  function updateMetrics() {
    const text = getPlainText();
    const tags = extractHashtags(text);
    $('char-count').textContent = `${text.length.toLocaleString()} chars`;
    $('hashtag-count').textContent = `${tags.length} hashtag${tags.length === 1 ? '' : 's'}`;
    $('hashtag-count').classList.toggle('warn', tags.length > 30);

    const metaBox = $('detected-meta');
    if (tags.length) {
      $('detected-hashtags').innerHTML = tags.map(t => `<span class="meta-pill">${esc(t)}</span>`).join('');
      metaBox.classList.remove('hide');
    } else {
      metaBox.classList.add('hide');
    }

    renderPlatforms();
    renderPreviews();
  }

  function formatPreviewText(text) {
    const tokenRe = /(https?:\/\/[^\s)<>"]+)|((?:^|\s)#[a-zA-Z0-9_\u00C0-\u024F\u0900-\u097F]+)/g;
    let out = '';
    let last = 0;
    for (const match of text.matchAll(tokenRe)) {
      const idx = match.index;
      if (idx > last) out += esc(text.slice(last, idx));
      if (match[1]) {
        out += `<span class="mock-link">${esc(match[1])}</span>`;
      } else if (match[2]) {
        const leadingSpace = match[2].match(/^\s*/)[0];
        const tag = match[2].slice(leadingSpace.length);
        out += `${esc(leadingSpace)}<span class="mock-tag">${esc(tag)}</span>`;
      }
      last = idx + match[0].length;
    }
    if (last < text.length) out += esc(text.slice(last));
    return out;
  }

  function validatePlatformClient(key, text) {
    const p = PLATFORMS[key];
    const warns = [];
    if (!text && !state.image) warns.push('Post content cannot be empty.');
    if (text.length > p.maxChars) warns.push(`Exceeds ${p.maxChars.toLocaleString()} character limit (${text.length.toLocaleString()}).`);
    if (key === 'instagram' && !state.image) warns.push('Instagram requires an image attachment.');
    if (key === 'instagram') {
      const tags = extractHashtags(text);
      if (tags.length > 30) warns.push(`Instagram allows max 30 hashtags (${tags.length} used).`);
    }
    const ctaUrl = $('cta-url').value.trim();
    if (key === 'gmb' && ctaUrl && !/^https?:\/\//i.test(ctaUrl)) {
      warns.push('GMB CTA URL should start with http:// or https://');
    }
    return warns;
  }

  function buildMockCard(key, text) {
    const p = PLATFORMS[key];
    const warns = validatePlatformClient(key, text);
    const ctaType = $('cta-type').value;
    const ctaUrl = $('cta-url').value.trim();

    const footers = {
      instagram: '<span>♡ Like</span><span>💬 Comment</span><span>↗ Share</span><span>🔖 Save</span>',
      facebook: '<span>👍 Like</span><span>💬 Comment</span><span>↗ Share</span>',
      gmb: '<span>📍 View on Google</span><span>↗ Share</span>',
      linkedin: '<span>👍 Like</span><span>💬 Comment</span><span>🔁 Repost</span><span>➤ Send</span>'
    };

    const mediaBlock = state.imageUrl
      ? `<div class="mock-media"><img src="${esc(state.imageUrl)}" alt="Post preview"></div>`
      : '';

    const ctaBlock = key === 'gmb' && ctaType && ctaUrl
      ? `<div class="mock-cta"><a class="mock-cta-btn" href="${esc(ctaUrl)}" target="_blank" rel="noopener">${esc(CTA_LABELS[ctaType] || 'Learn more')}</a></div>`
      : '';

    const bodyText = text
      ? `<div class="mock-body">${formatPreviewText(text)}</div>`
      : `<div class="mock-body" style="color:var(--ink-light);font-style:italic">No caption text yet…</div>`;

    return `
      <div class="mock-card">
        <div class="mock-head">
          <div class="platform-icon ${p.iconClass}">${p.svg}</div>
          <div>
            <div class="mock-author">${p.name}</div>
            <div class="mock-sub">${p.handle} · Preview</div>
          </div>
        </div>
        ${key === 'instagram' ? mediaBlock + bodyText : bodyText + mediaBlock}
        ${ctaBlock}
        <div class="mock-foot">${footers[key]}</div>
        ${warns.map(w => `<div class="mock-warn">⚠ ${esc(w)}</div>`).join('')}
      </div>
    `;
  }

  function renderPreviews() {
    const selected = state.selectedPlatforms;
    const tabsEl = $('preview-tabs');
    const stageEl = $('preview-stage');

    if (!selected.length) {
      tabsEl.innerHTML = '';
      stageEl.innerHTML = '<div class="empty-state"><p>Select at least one platform to see live previews.</p></div>';
      return;
    }

    const tabs = [['all', `All (${selected.length})`], ...selected.map(k => [k, PLATFORMS[k].name])];
    tabsEl.innerHTML = tabs.map(([k, label]) => `
      <button type="button" class="pv-tab ${state.activePreviewTab === k ? 'active' : ''}" data-pv="${k}">${label}</button>
    `).join('');

    tabsEl.querySelectorAll('button').forEach(btn => {
      btn.onclick = () => {
        state.activePreviewTab = btn.dataset.pv;
        renderPreviews();
      };
    });

    const text = getPlainText();
    if (!text && !state.image) {
      stageEl.innerHTML = '<div class="empty-state"><p>Write your post or upload an image to preview how it renders on each selected platform.</p></div>';
      return;
    }

    const listToShow = state.activePreviewTab === 'all' ? selected : [state.activePreviewTab];
    stageEl.innerHTML = listToShow.map(k => buildMockCard(k, text)).join('');
  }

  // Image Upload
  async function uploadImageFile(file) {
    if (!file) return;
    showError('');
    const fd = new FormData();
    fd.append('image', file);
    try {
      const res = await fetch('/api/upload', { method: 'POST', body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Upload failed.');
      state.image = data.file;
      state.imageOriginalName = data.originalName || file.name;
      state.imageUrl = data.url;
      $('thumb-img').src = data.url;
      $('thumb-name').textContent = state.imageOriginalName;
      $('thumb-meta').textContent = `${formatBytes(data.size)} · Ready to publish`;
      $('dropzone-empty').classList.add('hide');
      $('dropzone-preview').classList.remove('hide');
      renderPlatforms();
      renderPreviews();
    } catch (err) {
      showError(err.message);
    }
  }

  function clearImage() {
    state.image = null;
    state.imageOriginalName = null;
    state.imageUrl = null;
    $('file-input').value = '';
    $('dropzone-preview').classList.add('hide');
    $('dropzone-empty').classList.remove('hide');
    renderPlatforms();
    renderPreviews();
  }

  // Status Rendering & Retry
  function statusBadge(status) {
    const label = status === 'success' ? 'Success' : status === 'failed' ? 'Failed' : 'Publishing…';
    return `<span class="badge ${status}">${label}</span>`;
  }

  function renderPublishStatus(post) {
    state.lastPublishPost = post;
    const card = $('status-card');
    const list = $('status-list');
    card.classList.remove('hide');

    const hasFailures = post.results.some(r => r.status === 'failed');
    $('retry-all-btn').classList.toggle('hide', !hasFailures);

    const okCount = post.results.filter(r => r.status === 'success').length;
    $('status-subtitle').textContent = `${okCount} of ${post.results.length} platform(s) succeeded`;

    list.innerHTML = post.results.map(r => {
      const p = PLATFORMS[r.platform];
      return `
        <div class="status-item">
          <div class="status-row">
            <div class="status-left">
              <div class="platform-icon ${p.iconClass}" style="width:24px;height:24px;border-radius:6px">${p.svg}</div>
              <span>${p.name}</span>
            </div>
            ${statusBadge(r.status)}
          </div>
          ${r.status === 'success' ? `
            <div class="status-detail">ID: <code>${esc(r.external_id || 'published')}</code></div>
            <div class="status-actions">
              <a href="${esc(r.url)}" target="_blank" rel="noopener" class="btn btn-secondary btn-sm">View post ↗</a>
            </div>
          ` : r.status === 'failed' ? `
            <div class="status-detail err">${esc(r.error)}</div>
            <div class="status-actions">
              <button type="button" class="btn btn-secondary btn-sm retry-one-btn" data-id="${post.id}" data-platform="${r.platform}">Retry ${p.name}</button>
            </div>
          ` : `
            <div class="status-detail">Sending request to ${p.name}…</div>
          `}
        </div>
      `;
    }).join('');

    list.querySelectorAll('.retry-one-btn').forEach(btn => {
      btn.onclick = () => retryPost(Number(btn.dataset.id), btn.dataset.platform);
    });
  }

  async function retryPost(postId, platform = null) {
    try {
      const res = await fetch(`/api/posts/${postId}/retry`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(platform ? { platform } : {})
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Retry failed.');
      if (state.lastPublishPost && state.lastPublishPost.id === postId) {
        renderPublishStatus(data);
      }
      await loadHistory();
    } catch (err) {
      showError(err.message);
    }
  }

  // Publish Action
  async function publishPost() {
    showError('');
    const text = getPlainText();
    const platforms = [...state.selectedPlatforms];
    if (!platforms.length) {
      return showError('Please select at least one social media platform.');
    }
    if (!text && !state.image) {
      return showError('Please write a message or attach an image before publishing.');
    }

    $('publish-btn').disabled = true;
    $('publish-btn').textContent = 'Publishing…';

    // Show immediate pending status cards
    $('status-card').classList.remove('hide');
    $('retry-all-btn').classList.add('hide');
    $('status-subtitle').textContent = `Publishing to ${platforms.length} platform(s)…`;
    $('status-list').innerHTML = platforms.map(k => `
      <div class="status-item">
        <div class="status-row">
          <div class="status-left">
            <div class="platform-icon ${PLATFORMS[k].iconClass}" style="width:24px;height:24px;border-radius:6px">${PLATFORMS[k].svg}</div>
            <span>${PLATFORMS[k].name}</span>
          </div>
          ${statusBadge('pending')}
        </div>
        <div class="status-detail">Dispatching via API…</div>
      </div>
    `).join('');

    try {
      const payload = {
        draftId: state.editingDraftId,
        html: quill.root.innerHTML,
        category: state.category,
        image: state.image,
        imageOriginalName: state.imageOriginalName,
        ctaType: $('cta-type').value || null,
        ctaUrl: $('cta-url').value.trim() || null,
        platforms,
        simulateFailures: [...state.simulateFailures]
      };
      const res = await fetch('/api/publish', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Publishing failed.');
      state.editingDraftId = null;
      renderPublishStatus(data);
      await Promise.all([loadHistory(), loadHealth()]);
    } catch (err) {
      showError(err.message);
    } finally {
      $('publish-btn').disabled = false;
      $('publish-btn').textContent = 'Submit & Publish';
    }
  }

  // History Loading & Actions
  async function loadHistory() {
    const params = new URLSearchParams();
    const postStatus = $('filter-post-status').value;
    const q = $('history-search').value.trim();
    const cat = $('filter-category').value;
    const plat = $('filter-platform').value;
    const status = $('filter-status').value;
    params.set('postStatus', postStatus);
    if (q) params.set('q', q);
    if (cat) params.set('category', cat);
    if (plat) params.set('platform', plat);
    if (status) params.set('status', status);

    const res = await fetch(`/api/posts?${params.toString()}`);
    const posts = await res.json();
    state.historyPosts = posts;

    // Update topbar count from published total when unfiltered
    if (postStatus === 'published' && !q && !cat && !plat && !status) {
      $('history-count-pill').textContent = posts.length;
    }

    const totalSuccess = posts.reduce((acc, p) => acc + p.results.filter(r => r.status === 'success').length, 0);
    const totalFailed = posts.reduce((acc, p) => acc + p.results.filter(r => r.status === 'failed').length, 0);
    $('stat-total').textContent = posts.length;
    $('stat-success').textContent = totalSuccess;
    $('stat-failed').textContent = totalFailed;

    const listEl = $('history-list');
    if (!posts.length) {
      listEl.innerHTML = '<div class="empty-state"><p>No posts or drafts match your filters yet.</p></div>';
      return;
    }

    listEl.innerHTML = posts.map(post => {
      const dateStr = new Date(post.created_at.replace(' ', 'T') + 'Z').toLocaleString();
      const isDraft = post.post_status === 'draft';
      const hasFailed = post.results.some(r => r.status === 'failed');
      return `
        <div class="history-item">
          <div>
            <div class="history-meta">
              <span class="badge cat">${esc(post.category || 'general')}</span>
              ${isDraft ? '<span class="badge pending">Draft</span>' : ''}
              <span>${esc(dateStr)}</span>
              ${post.hashtags?.length ? `<span>· ${post.hashtags.length} #tags</span>` : ''}
            </div>
            <div class="history-content">
              ${post.image ? `<img class="history-thumb" src="/uploads/${esc(post.image)}" alt="Post image">` : ''}
              <p class="history-text">${esc(post.text.slice(0, 260))}${post.text.length > 260 ? '…' : ''}</p>
            </div>
            <div class="history-actions">
              <button type="button" class="btn btn-secondary btn-sm reuse-btn" data-id="${post.id}">${isDraft ? 'Edit Draft' : 'Reuse in Editor'}</button>
              ${hasFailed ? `<button type="button" class="btn btn-secondary btn-sm history-retry-btn" data-id="${post.id}">Retry Failed</button>` : ''}
              <button type="button" class="btn btn-danger-ghost btn-sm delete-post-btn" data-id="${post.id}">Delete</button>
            </div>
          </div>
          <div class="history-results">
            ${post.results.length ? post.results.map(r => `
              <div class="history-res-row">
                <strong>${PLATFORMS[r.platform]?.name || r.platform}</strong>
                <div style="display:flex;align-items:center;gap:8px">
                  ${statusBadge(r.status)}
                  ${r.status === 'success' && r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">View ↗</a>` : ''}
                </div>
                ${r.error ? `<div class="history-res-err">${esc(r.error)}</div>` : ''}
              </div>
            `).join('') : '<div class="history-res-row"><span style="color:var(--ink-light)">Saved draft (not published yet)</span></div>'}
          </div>
        </div>
      `;
    }).join('');

    listEl.querySelectorAll('.history-retry-btn').forEach(btn => {
      btn.onclick = () => retryPost(Number(btn.dataset.id));
    });

    listEl.querySelectorAll('.reuse-btn').forEach(btn => {
      btn.onclick = () => {
        const post = state.historyPosts.find(p => p.id === Number(btn.dataset.id));
        if (!post) return;
        state.editingDraftId = post.post_status === 'draft' ? post.id : null;
        setCategory(post.category || 'general');
        quill.clipboard.dangerouslyPasteHTML(post.html || '');
        $('cta-type').value = post.cta_type || '';
        $('cta-url').value = post.cta_url || '';
        if (post.image) {
          state.image = post.image;
          state.imageOriginalName = post.image_original_name || post.image;
          state.imageUrl = `/uploads/${post.image}`;
          $('thumb-img').src = state.imageUrl;
          $('thumb-name').textContent = state.imageOriginalName;
          $('thumb-meta').textContent = 'Loaded from database';
          $('dropzone-empty').classList.add('hide');
          $('dropzone-preview').classList.remove('hide');
        } else {
          clearImage();
        }
        switchView('compose');
        updateMetrics();
      };
    });

    listEl.querySelectorAll('.delete-post-btn').forEach(btn => {
      btn.onclick = async () => {
        await fetch(`/api/posts/${btn.dataset.id}`, { method: 'DELETE' });
        await Promise.all([loadHistory(), loadHealth()]);
      };
    });
  }

  // Database Health & Templates
  async function loadHealth() {
    try {
      const res = await fetch('/api/health');
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error('DB check failed');
      $('db-pill').classList.add('ok');
      $('db-pill').classList.remove('err');
      $('db-pill-text').textContent = `SQLite Connected (${data.counts.posts} posts)`;
    } catch {
      $('db-pill').classList.add('err');
      $('db-pill').classList.remove('ok');
      $('db-pill-text').textContent = 'DB Disconnected';
    }
  }

  async function loadTemplates() {
    const res = await fetch('/api/templates');
    state.templates = await res.json();
    const bar = $('template-bar');
    bar.innerHTML = `<span class="label-inline">Templates:</span>` + state.templates.map(tpl => `
      <span class="tpl-chip-wrap">
        <button type="button" class="tpl-btn" data-id="${tpl.id}">${esc(tpl.name)}</button>
        ${tpl.is_default ? '' : `<button type="button" class="tpl-del-btn" data-del="${tpl.id}" title="Delete template">&times;</button>`}
      </span>
    `).join('');

    bar.querySelectorAll('.tpl-btn').forEach(btn => {
      btn.onclick = () => {
        const tpl = state.templates.find(t => t.id === Number(btn.dataset.id));
        if (!tpl) return;
        setCategory(tpl.category || 'general');
        quill.clipboard.dangerouslyPasteHTML(tpl.html || '');
        $('cta-type').value = tpl.cta_type || '';
        $('cta-url').value = tpl.cta_url || '';
        showError('');
        updateMetrics();
      };
    });

    bar.querySelectorAll('.tpl-del-btn').forEach(btn => {
      btn.onclick = async () => {
        await fetch(`/api/templates/${btn.dataset.del}`, { method: 'DELETE' });
        await Promise.all([loadTemplates(), loadHealth()]);
      };
    });
  }

  async function saveCurrentAsTemplate() {
    showError('');
    if (!getPlainText()) return showError('Write content in the editor before saving a template.');
    const name = window.prompt('Name for this reusable template:');
    if (!name || !name.trim()) return;
    const res = await fetch('/api/templates', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name.trim(),
        category: state.category,
        html: quill.root.innerHTML,
        ctaType: $('cta-type').value || null,
        ctaUrl: $('cta-url').value.trim() || null
      })
    });
    const data = await res.json();
    if (!res.ok) return showError(data.error || 'Could not save template.');
    await Promise.all([loadTemplates(), loadHealth()]);
  }

  async function saveDraft() {
    showError('');
    if (!getPlainText() && !state.image) {
      return showError('Write post content or attach an image before saving a draft.');
    }
    const res = await fetch('/api/drafts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: state.editingDraftId,
        html: quill.root.innerHTML,
        category: state.category,
        image: state.image,
        imageOriginalName: state.imageOriginalName,
        ctaType: $('cta-type').value || null,
        ctaUrl: $('cta-url').value.trim() || null
      })
    });
    const data = await res.json();
    if (!res.ok) return showError(data.error || 'Could not save draft.');
    state.editingDraftId = data.id;
    $('status-card').classList.remove('hide');
    $('retry-all-btn').classList.add('hide');
    $('status-subtitle').textContent = 'Draft saved in SQLite database';
    $('status-list').innerHTML = `<div class="status-item"><div class="status-row"><strong>Draft #${data.id}</strong><span class="badge pending">Saved</span></div><div class="status-detail">Find it anytime under Publishing History → Saved drafts.</div></div>`;
    await loadHealth();
  }

  // Config / Mode Modal
  async function loadConfig() {
    try {
      const res = await fetch('/api/config');
      state.config = await res.json();
      const isLive = state.config.mode === 'live';
      $('mode-pill').classList.toggle('live', isLive);
      $('mode-pill-text').textContent = isLive ? 'Live API Mode' : 'Sandbox Mode';
      $('sandbox-helper').classList.toggle('hide', isLive);

      if (!isLive) {
        $('sim-fail-checks').innerHTML = Object.entries(PLATFORMS).map(([k, p]) => `
          <label><input type="checkbox" value="${k}" ${state.simulateFailures.has(k) ? 'checked' : ''}> Fail ${p.name}</label>
        `).join('');
        $('sim-fail-checks').querySelectorAll('input').forEach(cb => {
          cb.onchange = () => {
            if (cb.checked) state.simulateFailures.add(cb.value);
            else state.simulateFailures.delete(cb.value);
          };
        });
      }
    } catch {
      $('mode-pill-text').textContent = 'Offline';
    }
  }

  function openConfigModal() {
    const cfg = state.config;
    const fields = cfg.fields || {};
    const rows = Object.values(cfg.platforms || {}).map(p => `
      <div class="cfg-row">
        <div class="cfg-head">
          <strong>${esc(p.name)}</strong>
          <span class="badge ${p.configured ? 'success' : 'pending'}">${p.configured ? 'Credentials Ready' : 'Not Configured'}</span>
        </div>
        <div class="cfg-env">
          ${p.configured
        ? 'All required credentials are saved.'
        : `Missing: ${p.missingEnv.map(k => `<code>${esc(k)}</code>`).join(', ')}`}
        </div>
      </div>
    `).join('');

    const credFields = [
      ['META_PAGE_ID', 'Facebook Page ID'],
      ['META_PAGE_TOKEN', 'Meta Page Access Token (Facebook & Instagram)'],
      ['META_IG_USER_ID', 'Instagram Business Account ID'],
      ['LINKEDIN_TOKEN', 'LinkedIn OAuth Bearer Token'],
      ['LINKEDIN_AUTHOR_URN', 'LinkedIn Author URN (urn:li:person:...)'],
      ['GOOGLE_CLIENT_ID', 'Google OAuth Client ID'],
      ['GOOGLE_CLIENT_SECRET', 'Google OAuth Client Secret'],
      ['GOOGLE_REFRESH_TOKEN', 'Google OAuth Refresh Token'],
      ['GMB_ACCOUNT_ID', 'GMB Account ID'],
      ['GMB_LOCATION_ID', 'GMB Location ID']
    ];

    $('config-modal-body').innerHTML = `
      <p style="margin-top:0;font-size:0.84rem;color:var(--ink-muted)">
        Settings saved here are persisted in the SQLite database (<code>settings</code> table) and override <code>.env</code> defaults immediately.
      </p>
      ${rows}
      <form id="config-form" class="cfg-form-grid">
        <div class="cfg-field">
          <label for="cfg-mode">Publishing Mode</label>
          <select id="cfg-mode">
            <option value="sandbox" ${cfg.mode === 'sandbox' ? 'selected' : ''}>Sandbox (Simulated APIs)</option>
            <option value="live" ${cfg.mode === 'live' ? 'selected' : ''}>Live (Official Platform APIs)</option>
          </select>
        </div>
        <div class="cfg-field">
          <label for="cfg-base-url">Public Base URL (needed by Instagram &amp; GMB to fetch images)</label>
          <input id="cfg-base-url" type="url" value="${esc(cfg.publicBaseUrl || '')}" placeholder="https://your-domain.com">
        </div>
        ${credFields.map(([k, label]) => {
      const info = fields[k] || {};
      const placeholder = info.isSet
        ? `Saved (${info.preview}) — leave blank to keep`
        : `Enter ${k}`;
      return `
            <div class="cfg-field">
              <label for="cfg-${k}">${esc(label)} <code>${k}</code></label>
              <input id="cfg-${k}" data-envkey="${k}" type="${info.isSecret ? 'password' : 'text'}" value="${!info.isSecret ? esc(info.preview || '') : ''}" placeholder="${esc(placeholder)}">
            </div>
          `;
    }).join('')}
        <div class="modal-actions">
          <button type="button" id="cancel-config-btn" class="btn btn-secondary btn-sm">Cancel</button>
          <button type="submit" class="btn btn-primary btn-sm">Save Settings to DB</button>
        </div>
      </form>
    `;

    $('cancel-config-btn').onclick = () => $('config-modal').classList.add('hide');
    $('config-form').onsubmit = async e => {
      e.preventDefault();
      const values = {};
      $('config-form').querySelectorAll('[data-envkey]').forEach(input => {
        const val = input.value.trim();
        if (val) values[input.dataset.envkey] = val;
      });
      const res = await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: $('cfg-mode').value,
          publicBaseUrl: $('cfg-base-url').value.trim(),
          values
        })
      });
      if (res.ok) {
        await Promise.all([loadConfig(), loadHealth()]);
        $('config-modal').classList.add('hide');
      }
    };

    $('config-modal').classList.remove('hide');
  }

  function setCategory(cat) {
    state.category = cat;
    document.querySelectorAll('.category-row .chip').forEach(c => {
      c.classList.toggle('active', c.dataset.category === cat);
    });
  }

  function switchView(view) {
    const isCompose = view === 'compose';
    $('view-compose').classList.toggle('hide', !isCompose);
    $('view-history').classList.toggle('hide', isCompose);
    $('tab-compose').classList.toggle('active', isCompose);
    $('tab-history').classList.toggle('active', !isCompose);
    if (!isCompose) loadHistory();
  }

  // Event Wiring
  $('tab-compose').onclick = () => switchView('compose');
  $('tab-history').onclick = () => switchView('history');

  document.querySelectorAll('.category-row .chip').forEach(chip => {
    chip.onclick = () => setCategory(chip.dataset.category);
  });

  $('save-template-btn').onclick = saveCurrentAsTemplate;

  $('clear-editor-btn').onclick = () => {
    state.editingDraftId = null;
    setCategory('promotional');
    quill.setContents([]);
    $('cta-type').value = '';
    $('cta-url').value = '';
    clearImage();
    showError('');
    $('status-card').classList.add('hide');
    updateMetrics();
  };

  $('toggle-emoji-btn').onclick = () => {
    $('emoji-drawer').classList.toggle('hide');
    $('hashtag-drawer').classList.add('hide');
    $('link-drawer').classList.add('hide');
  };

  $('toggle-hashtag-btn').onclick = () => {
    $('hashtag-drawer').classList.toggle('hide');
    $('emoji-drawer').classList.add('hide');
    $('link-drawer').classList.add('hide');
  };

  $('open-link-btn').onclick = () => {
    $('link-drawer').classList.toggle('hide');
    $('emoji-drawer').classList.add('hide');
    $('hashtag-drawer').classList.add('hide');
  };

  $('add-hashtag-btn').onclick = addCustomHashtag;
  $('custom-hashtag-input').onkeydown = e => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addCustomHashtag();
    }
  };

  $('insert-link-confirm').onclick = () => {
    const url = $('link-url-input').value.trim();
    const label = $('link-text-input').value.trim() || url;
    if (!/^https?:\/\//i.test(url)) {
      return showError('Please enter a valid link starting with http:// or https://');
    }
    showError('');
    quill.focus();
    const range = quill.getSelection(true) || { index: quill.getLength() - 1, length: 0 };
    quill.insertText(range.index, label, 'link', url);
    quill.insertText(range.index + label.length, ' ');
    quill.setSelection(range.index + label.length + 1);
    $('link-url-input').value = '';
    $('link-text-input').value = '';
    $('link-drawer').classList.add('hide');
  };

  // Dropzone events
  const dz = $('dropzone');
  dz.onclick = e => {
    if (e.target.closest('button')) return;
    $('file-input').click();
  };
  dz.ondragover = e => { e.preventDefault(); dz.classList.add('dragover'); };
  dz.ondragleave = () => dz.classList.remove('dragover');
  dz.ondrop = e => {
    e.preventDefault();
    dz.classList.remove('dragover');
    if (e.dataTransfer.files?.[0]) uploadImageFile(e.dataTransfer.files[0]);
  };
  $('file-input').onchange = e => {
    if (e.target.files?.[0]) uploadImageFile(e.target.files[0]);
  };
  $('replace-img-btn').onclick = () => $('file-input').click();
  $('remove-img-btn').onclick = clearImage;

  $('select-all-btn').onclick = () => {
    state.selectedPlatforms = Object.keys(PLATFORMS);
    renderPlatforms();
    renderPreviews();
  };

  $('clear-all-btn').onclick = () => {
    state.selectedPlatforms = [];
    renderPlatforms();
    renderPreviews();
  };

  $('preview-btn').onclick = () => {
    showError('');
    if (!state.selectedPlatforms.length) return showError('Select at least one platform to preview.');
    if (!getPlainText() && !state.image) return showError('Write post content or attach an image to preview.');
    renderPreviews();
    $('preview-card').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  };

  $('save-draft-btn').onclick = saveDraft;
  $('publish-btn').onclick = publishPost;
  $('retry-all-btn').onclick = () => {
    if (state.lastPublishPost) retryPost(state.lastPublishPost.id);
  };

  $('cta-type').onchange = renderPreviews;
  $('cta-url').oninput = renderPreviews;

  $('filter-post-status').onchange = loadHistory;
  $('history-search').oninput = loadHistory;
  $('filter-category').onchange = loadHistory;
  $('filter-platform').onchange = loadHistory;
  $('filter-status').onchange = loadHistory;

  $('mode-pill').onclick = openConfigModal;
  $('close-config-modal').onclick = () => $('config-modal').classList.add('hide');
  $('config-modal').onclick = e => {
    if (e.target === $('config-modal')) $('config-modal').classList.add('hide');
  };

  quill.on('text-change', updateMetrics);

  // Initial render
  renderEmojis();
  renderHashtagPacks();
  renderPlatforms();
  renderPreviews();
  loadHealth();
  loadTemplates();
  loadConfig();
  loadHistory();
})();
