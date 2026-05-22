document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('search-input');
    const searchType = document.getElementById('search-type');
    const searchBtn = document.getElementById('search-btn');
    const suggestionsList = document.getElementById('suggestions-list');
    window.renderAuthUI();

    function executeSearch() {
        const queryText = searchInput.value.trim();
        if (!queryText) return;
        const type = searchType.value;
        window.location.href = `results.html?q=${encodeURIComponent(queryText)}&type=${encodeURIComponent(type)}`;
    }

    searchBtn.addEventListener('click', executeSearch);
    searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            executeSearch();
        }
    });

    function debounce(func, delay) {
        let timer;
        return function (...args) {
            clearTimeout(timer);
            timer = setTimeout(() => func.apply(this, args), delay);
        };
    }

    const fetchSuggestions = async () => {
        const query = searchInput.value.trim();
        if (!query) {
            suggestionsList.style.display = 'none';
            return;
        }
        const user = window.auth && window.auth.getUser ? window.auth.getUser() : null;
        const uid = user ? user.user_id : null;
        try {
            const { suggestions, correction } = await window.fetchQuerySuggestions(query, uid);
            window.renderSuggestionList(suggestionsList, suggestions, correction, (text) => {
                searchInput.value = text;
                suggestionsList.style.display = 'none';
                executeSearch();
            });
        } catch (error) {
            console.error('Failed to load suggestions:', error);
            suggestionsList.style.display = 'none';
        }
    };

    searchInput.addEventListener('input', debounce(fetchSuggestions, 280));
    document.addEventListener('click', (e) => {
        if (!searchInput.contains(e.target) && !suggestionsList.contains(e.target)) {
            suggestionsList.style.display = 'none';
        }
    });
});
