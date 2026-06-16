document.addEventListener('DOMContentLoaded', () => {
    window.renderAuthUI();
    const urlParams = new URLSearchParams(window.location.search);
    let currentQuery = urlParams.get('q') || '';
    let currentType = urlParams.get('type') || 'site';
    let currentPage = parseInt(urlParams.get('page'), 10) || 1;

    const topInput = document.getElementById('top-search-input');
    const searchBtn = document.getElementById('top-search-btn');
    const container = document.getElementById('results-container');
    const stats = document.getElementById('result-stats');
    const intentBar = document.getElementById('query-intent-bar');
    const pagination = document.getElementById('pagination-container');
    const typeTabs = document.querySelectorAll('.type-tab');

    function syncTypeTabs() {
        typeTabs.forEach((tab) => {
            tab.classList.toggle('active', tab.dataset.type === currentType);
        });
    }

    syncTypeTabs();

    typeTabs.forEach((tab) => {
        tab.addEventListener('click', () => {
            const t = tab.dataset.type;
            if (t === currentType || !currentQuery) return;
            currentType = t;
            currentPage = 1;
            syncTypeTabs();
            updateUrl();
            fetchResults();
        });
    });

    function updateUrl() {
        const url = new URL(window.location.href);
        url.searchParams.set('q', currentQuery);
        url.searchParams.set('type', currentType);
        url.searchParams.set('page', String(currentPage));
        history.replaceState(null, '', url);
    }

    if (currentQuery) {
        topInput.value = currentQuery;
        fetchResults();
    } else {
        container.innerHTML = '<p class="empty-msg">请输入检索词</p>';
    }

    function goSearch(page) {
        const q = topInput.value.trim();
        if (!q) return;
        currentQuery = q;
        currentPage = page || 1;
        window.location.href = `results.html?q=${encodeURIComponent(q)}&type=${currentType}&page=${currentPage}`;
    }

    searchBtn.addEventListener('click', () => goSearch(1));

    window.setupSearchSuggest({
        inputEl: topInput,
        listEl: document.getElementById('top-suggestions-list'),
        ghostEl: document.getElementById('top-search-ghost'),
        wrapperEl: document.querySelector('.results-toolbar'),
        getUserId: () => {
            const u = window.auth && window.auth.getUser ? window.auth.getUser() : null;
            return u ? u.user_id : null;
        },
        onSubmit: () => goSearch(1),
    });

    async function fetchResults() {
        container.innerHTML = '<p class="loading">检索中...</p>';
        const user = window.auth ? window.auth.getUser() : null;
        try {
            const response = await window.apiClient.post('/search', {
                query_text: currentQuery,
                search_type: currentType,
                user_id: user ? Number(user.user_id) : null,
                page: currentPage,
            });
            const data = response.data;
            currentPage = data.current_page || currentPage;
            renderResults(data);
            renderPagination(data);
        } catch (error) {
            let errMsg = error.message || '请求失败';
            container.innerHTML = `<p class="empty-msg" style="color:#d93025;">${errMsg}</p>`;
        }
    }

    function renderTagPills(tags, matched) {
        if (!tags || !tags.length) return '';
        const matchedSet = new Set((matched || []).map((m) => `${m.type}:${m.label.split(' ')[0]}`));
        const typeClass = { college: 'tag-college', macro: 'tag-macro', group: 'tag-group', topic: 'tag-topic' };
        const typeName = { college: '学院', macro: '大类', group: '学科群', topic: '主题' };
        return tags.map((t) => {
            const cls = typeClass[t.type] || 'tag-topic';
            const prefix = typeName[t.type] ? `${typeName[t.type]}:` : '';
            const label = t.label.split(' ')[0];
            const key = `${t.type}:${label}`;
            const hit = matchedSet.has(key);
            return `<span class="tag-pill ${cls}${hit ? ' tag-matched' : ''}">${prefix}${escapeHtml(t.label)}</span>`;
        }).join('');
    }

    function renderAttachments(items) {
        if (!items || !items.length) return '';
        return items.map((a) =>
            `<a class="attachment-link" href="${escapeAttr(a.url)}" target="_blank" rel="noopener">${escapeHtml(a.name || a.url)}</a>`
        ).join('');
    }

    function renderQueryIntent(intent) {
        if (!intent || !intent.tags || !intent.tags.length) {
            intentBar.innerHTML = '';
            return;
        }
        const typeClass = { college: 'tag-college', macro: 'tag-macro', group: 'tag-group', topic: 'tag-topic' };
        const pills = intent.tags.map((t) => {
            const cls = typeClass[t.type] || 'tag-topic';
            return `<span class="tag-pill ${cls}">${escapeHtml(t.label)}</span>`;
        }).join('');
        intentBar.innerHTML = `<div class="query-intent-bar"><span class="query-intent-label">搜索意图</span>${pills}</div>`;
    }

    function renderResults(data) {
        const results = data.results || [];
        const totalHits = data.total_hits || 0;
        const totalIndexed = data.total_indexed;
        let statText = `共 ${totalHits} 条可展示结果`;
        if (totalIndexed && totalIndexed > totalHits) {
            statText += `（索引库匹配约 ${totalIndexed} 条）`;
        }
        statText += ` · 第 ${data.current_page || 1} / ${data.total_pages || 1} 页`;
        if (data.personalized) statText += ' · 已按您的兴趣排序';
        stats.textContent = statText;
        renderQueryIntent(data.query_intent);
        container.innerHTML = '';

        if (!results.length) {
            container.innerHTML = '<p class="empty-msg">未找到匹配内容</p>';
            return;
        }

        const apiBase = window.APP_CONFIG.API_BASE_URL;
        results.forEach((item) => {
            const card = document.createElement('article');
            card.className = 'result-card';
            const snapshotUrl = `${apiBase}/snapshot?url=${encodeURIComponent(item.url)}`;
            const tagsHtml = renderTagPills(item.tags, item.matched_tags);
            const attachHtml = renderAttachments(item.attachments);
            const recBadge = item.personalized ? '<span class="rec-badge">与您相关</span>' : '';
            card.innerHTML = `
                <div class="result-head">
                    <a href="${escapeAttr(item.url)}" target="_blank" rel="noopener" class="result-title">${escapeHtml(item.title || '无标题')}</a>
                    <span class="result-badges">${recBadge}<span class="score-badge">${item.score}</span></span>
                </div>
                <div class="result-meta">
                    ${escapeHtml(item.url)}
                    <a class="snapshot-link" href="${escapeAttr(snapshotUrl)}" target="_blank" rel="noopener">快照</a>
                </div>
                ${tagsHtml ? `<div class="result-tags">${tagsHtml}</div>` : ''}
                ${attachHtml ? `<div class="result-attachments">${attachHtml}</div>` : ''}
                <div class="result-highlight">${item.highlight || ''}</div>
            `;
            container.appendChild(card);
        });
    }

    function renderPagination(data) {
        pagination.innerHTML = '';
        const totalPages = data.total_pages || 1;
        if (totalPages <= 1) return;

        const wrap = document.createElement('div');
        wrap.className = 'pagination-wrap';

        const nav = document.createElement('div');
        nav.className = 'pagination';

        const prev = document.createElement('button');
        prev.className = 'page-btn';
        prev.textContent = '上一页';
        prev.disabled = currentPage <= 1;
        prev.onclick = () => changePage(currentPage - 1);
        nav.appendChild(prev);

        const pages = buildPageList(currentPage, totalPages);
        pages.forEach((p) => {
            if (p === '...') {
                const span = document.createElement('span');
                span.className = 'page-ellipsis';
                span.textContent = '...';
                nav.appendChild(span);
            } else {
                const btn = document.createElement('button');
                btn.className = 'page-btn' + (p === currentPage ? ' active' : '');
                btn.textContent = String(p);
                btn.onclick = () => changePage(p);
                nav.appendChild(btn);
            }
        });

        const next = document.createElement('button');
        next.className = 'page-btn';
        next.textContent = '下一页';
        next.disabled = currentPage >= totalPages;
        next.onclick = () => changePage(currentPage + 1);
        nav.appendChild(next);

        wrap.appendChild(nav);

        const jump = document.createElement('div');
        jump.className = 'page-jump';
        jump.innerHTML = `
            <span>跳转到</span>
            <input type="number" id="page-jump-input" min="1" max="${totalPages}" value="${currentPage}">
            <span>页</span>
            <button type="button" class="btn btn-primary" id="page-jump-btn">确定</button>
        `;
        wrap.appendChild(jump);
        pagination.appendChild(wrap);

        document.getElementById('page-jump-btn').onclick = () => {
            const v = parseInt(document.getElementById('page-jump-input').value, 10);
            if (v >= 1 && v <= totalPages) changePage(v);
        };
        document.getElementById('page-jump-input').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') document.getElementById('page-jump-btn').click();
        });
    }

    function buildPageList(current, total) {
        if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
        const list = [1];
        if (current > 3) list.push('...');
        for (let i = Math.max(2, current - 1); i <= Math.min(total - 1, current + 1); i++) {
            if (!list.includes(i)) list.push(i);
        }
        if (current < total - 2) list.push('...');
        if (!list.includes(total)) list.push(total);
        return list;
    }

    function changePage(page) {
        window.location.href = `results.html?q=${encodeURIComponent(currentQuery)}&type=${currentType}&page=${page}`;
    }
});

function escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

function escapeAttr(s) {
    return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}
