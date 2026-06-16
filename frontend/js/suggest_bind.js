function setupSearchSuggest(opts) {
    const {
        inputEl,
        listEl,
        ghostEl,
        wrapperEl,
        getUserId,
        onSubmit,
    } = opts;

    let listItems = [];
    let reqSeq = 0;
    let composing = false;

    function debounce(fn, ms) {
        let t;
        return (...args) => {
            clearTimeout(t);
            t = setTimeout(() => fn(...args), ms);
        };
    }

    function onPick(text) {
        inputEl.value = text;
        listEl.style.display = 'none';
        if (ghostEl) ghostEl.style.display = 'none';
    }

    async function showHistory() {
        const seq = ++reqSeq;
        const uid = getUserId ? getUserId() : null;
        try {
            const rows = await window.fetchSearchHistory(uid);
            if (seq !== reqSeq) return;
            if (ghostEl) ghostEl.style.display = 'none';
            listItems = window.renderHistoryList(listEl, rows, onPick);
        } catch (e) {
            console.error('history failed:', e);
            listEl.style.display = 'none';
            listItems = [];
        }
    }

    async function fetchNow() {
        if (composing) return;
        const trimmed = inputEl.value.trim();
        if (!trimmed) {
            await showHistory();
            return;
        }
        const seq = ++reqSeq;
        const uid = getUserId ? getUserId() : null;
        try {
            const { suggestions, correction, top_completion, continuations } =
                await window.fetchQuerySuggestions(trimmed, uid);
            if (seq !== reqSeq) return;
            window.updateGhostText(ghostEl, inputEl, top_completion);
            listItems = window.renderSuggestionList(
                listEl,
                suggestions,
                correction,
                continuations,
                trimmed,
                onPick
            );
        } catch (e) {
            if (seq !== reqSeq) return;
            console.error('suggest failed:', e);
        }
    }

    const debouncedFetch = debounce(fetchNow, 200);

    inputEl.addEventListener('compositionstart', () => { composing = true; });
    inputEl.addEventListener('compositionend', () => {
        composing = false;
        fetchNow();
    });
    inputEl.addEventListener('input', () => {
        if (!composing) debouncedFetch();
    });
    inputEl.addEventListener('focus', () => {
        fetchNow();
    });

    if (wrapperEl) {
        document.addEventListener('mousedown', (e) => {
            if (wrapperEl.contains(e.target)) return;
            listEl.style.display = 'none';
        });
    }

    if (window.bindSuggestKeyboard) {
        window.bindSuggestKeyboard(
            inputEl,
            listEl,
            () => listItems,
            onPick,
            onSubmit
        );
    }

    return { refresh: fetchNow };
}

window.setupSearchSuggest = setupSearchSuggest;
