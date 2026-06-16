document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('search-input');
    const searchBtn = document.getElementById('search-btn');
    const suggestionsList = document.getElementById('suggestions-list');
    const ghostEl = document.getElementById('search-ghost');
    const wrapperEl = document.querySelector('.search-box');
    window.renderAuthUI();

    function executeSearch() {
        const queryText = searchInput.value.trim();
        if (!queryText) return;
        window.location.href = `results.html?q=${encodeURIComponent(queryText)}&type=site`;
    }

    searchBtn.addEventListener('click', executeSearch);

    window.setupSearchSuggest({
        inputEl: searchInput,
        listEl: suggestionsList,
        ghostEl,
        wrapperEl,
        getUserId: () => {
            const u = window.auth && window.auth.getUser ? window.auth.getUser() : null;
            return u ? u.user_id : null;
        },
        onSubmit: executeSearch,
    });
});
