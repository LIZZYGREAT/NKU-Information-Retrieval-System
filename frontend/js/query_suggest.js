const SOURCE_LABEL = {
    history: '历史',
    prefix: '补全',
    contains: '相关',
    fuzzy: '相关',
    correct: '纠错',
    engine_en: '英文引擎',
};

async function fetchQuerySuggestions(prefix, userId) {
    const q = (prefix || '').trim();
    if (!q) return { suggestions: [], correction: null };
    let url = `/query/suggest?q=${encodeURIComponent(q)}&limit=8`;
    if (userId) url += `&user_id=${userId}`;
    const res = await window.apiClient.get(url);
    const suggestions = (res.data && res.data.suggestions) || [];
    let correction = null;
    try {
        const cr = await window.apiClient.get(`/query/correct?q=${encodeURIComponent(q)}`);
        if (cr.data && cr.data.changed) correction = cr.data;
    } catch (_) {}
    return { suggestions, correction };
}

function renderSuggestionList(listEl, suggestions, correction, onPick) {
    listEl.innerHTML = '';
    if (correction && correction.corrected) {
        const li = document.createElement('li');
        li.className = 'suggest-correct';
        li.innerHTML = `<span class="suggest-tag">纠错</span> 您是否要找：<strong>${escapeHtml(correction.corrected)}</strong>`;
        li.addEventListener('click', () => onPick(correction.corrected));
        listEl.appendChild(li);
    }
    if (!suggestions.length && !correction) {
        listEl.style.display = 'none';
        return;
    }
    suggestions.forEach((item) => {
        const li = document.createElement('li');
        const tag = SOURCE_LABEL[item.source] || item.source;
        li.innerHTML = `<span class="suggest-tag">${tag}</span> ${escapeHtml(item.text)}`;
        li.addEventListener('click', () => onPick(item.text));
        listEl.appendChild(li);
    });
    listEl.style.display = 'block';
}

function escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

window.fetchQuerySuggestions = fetchQuerySuggestions;
window.renderSuggestionList = renderSuggestionList;
