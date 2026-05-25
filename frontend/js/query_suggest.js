const SOURCE_LABEL = {
    history: '历史',
    prefix: '补全',
    continuation: '续写',
    contains: '相关',
    fuzzy: '相关',
    correct: '纠错',
    token: '分词',
    hot: '热门',
    engine_en: '英文',
};

function escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

async function fetchSearchHistory(userId) {
    let url = '/query/history?limit=8';
    if (userId) url += `&user_id=${userId}`;
    const res = await window.apiClient.get(url);
    return (res.data && res.data.suggestions) || [];
}

async function fetchQuerySuggestions(prefix, userId) {
    const q = (prefix || '').trim();
    if (!q) {
        return { suggestions: [], correction: null, top_completion: null, continuations: [] };
    }
    let url = `/query/associate?q=${encodeURIComponent(q)}&limit=8`;
    if (userId) url += `&user_id=${userId}`;
    const res = await window.apiClient.get(url);
    const data = res.data || {};
    return {
        suggestions: data.suggestions || [],
        correction: data.correction && data.correction.changed ? data.correction : null,
        top_completion: data.top_completion || null,
        continuations: data.continuations || [],
    };
}

function highlightContinuation(query, full) {
    if (!full || !full.startsWith(query)) return escapeHtml(full || '');
    const typed = escapeHtml(query);
    const rest = escapeHtml(full.slice(query.length));
    return `${typed}<span class="suggest-rest">${rest}</span>`;
}

function renderSuggestionList(listEl, suggestions, correction, continuations, query, onPick) {
    listEl.innerHTML = '';
    const items = [];

    if (correction && correction.corrected) {
        items.push({
            type: 'correct',
            html: `<span class="suggest-tag">纠错</span> 您是否要找：<strong>${escapeHtml(correction.corrected)}</strong>`,
            value: correction.corrected,
        });
    }

    (continuations || []).forEach((c) => {
        items.push({
            type: 'continuation',
            html: `<span class="suggest-tag">${SOURCE_LABEL.continuation}</span> ${highlightContinuation(query, c.full)}`,
            value: c.full,
        });
    });

    (suggestions || []).forEach((item) => {
        if ((continuations || []).some((c) => c.full === item.text)) return;
        const tag = SOURCE_LABEL[item.source] || item.source;
        const html = item.text.startsWith(query)
            ? `<span class="suggest-tag">${tag}</span> ${highlightContinuation(query, item.text)}`
            : `<span class="suggest-tag">${tag}</span> ${escapeHtml(item.text)}`;
        items.push({ type: item.source, html, value: item.text });
    });

    if (!items.length) {
        listEl.style.display = 'none';
        return [];
    }

    items.forEach((item, idx) => {
        const li = document.createElement('li');
        li.dataset.index = String(idx);
        li.innerHTML = item.html;
        li.addEventListener('click', () => onPick(item.value, idx));
        listEl.appendChild(li);
    });
    listEl.style.display = 'block';
    return items;
}

function renderHistoryList(listEl, rows, onPick) {
    listEl.innerHTML = '';
    if (!rows || !rows.length) {
        listEl.style.display = 'none';
        return [];
    }
    const items = rows.map((row) => {
        const tag = SOURCE_LABEL[row.source] || '历史';
        return {
            html: `<span class="suggest-tag">${tag}</span> ${escapeHtml(row.text)}`,
            value: row.text,
        };
    });
    items.forEach((item, idx) => {
        const li = document.createElement('li');
        li.className = 'suggest-history';
        li.innerHTML = item.html;
        li.addEventListener('click', () => onPick(item.value, idx));
        listEl.appendChild(li);
    });
    listEl.style.display = 'block';
    return items;
}

function bindSuggestKeyboard(inputEl, listEl, getItems, onPick, onEnter) {
    let activeIndex = -1;

    function refreshActive() {
        const lis = listEl.querySelectorAll('li');
        lis.forEach((li, i) => li.classList.toggle('active', i === activeIndex));
    }

    inputEl.addEventListener('keydown', (e) => {
        const items = getItems();
        if (!items.length || listEl.style.display === 'none') {
            return;
        }
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            activeIndex = (activeIndex + 1) % items.length;
            refreshActive();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            activeIndex = activeIndex <= 0 ? items.length - 1 : activeIndex - 1;
            refreshActive();
        } else if (e.key === 'Tab' && activeIndex >= 0) {
            e.preventDefault();
            onPick(items[activeIndex].value, activeIndex);
        } else if (e.key === 'Enter' && activeIndex >= 0) {
            e.preventDefault();
            onPick(items[activeIndex].value, activeIndex);
        } else if (e.key === 'Enter') {
            onEnter();
        }
    });

    return { reset() { activeIndex = -1; refreshActive(); } };
}

function updateGhostText(ghostEl, inputEl, topCompletion) {
    if (!ghostEl) return;
    const typed = inputEl ? inputEl.value : '';
    if (!topCompletion || !topCompletion.suffix || !typed || !topCompletion.full.startsWith(typed)) {
        ghostEl.innerHTML = '';
        ghostEl.style.display = 'none';
        return;
    }
    let mirror = ghostEl.parentElement.querySelector('.ghost-measure');
    if (!mirror) {
        mirror = document.createElement('span');
        mirror.className = 'ghost-measure';
        mirror.setAttribute('aria-hidden', 'true');
        const cs = getComputedStyle(inputEl);
        mirror.style.font = cs.font;
        mirror.style.letterSpacing = cs.letterSpacing;
        mirror.style.visibility = 'hidden';
        mirror.style.position = 'absolute';
        mirror.style.whiteSpace = 'pre';
        ghostEl.parentElement.appendChild(mirror);
    }
    mirror.textContent = typed;
    const pad = parseFloat(getComputedStyle(inputEl).paddingLeft) || 20;
    ghostEl.style.paddingLeft = `${pad + mirror.offsetWidth}px`;
    ghostEl.innerHTML = `<span class="ghost-suffix">${escapeHtml(topCompletion.suffix)}</span>`;
    ghostEl.style.display = 'block';
}

window.fetchSearchHistory = fetchSearchHistory;
window.fetchQuerySuggestions = fetchQuerySuggestions;
window.renderSuggestionList = renderSuggestionList;
window.renderHistoryList = renderHistoryList;
window.bindSuggestKeyboard = bindSuggestKeyboard;
window.updateGhostText = updateGhostText;
