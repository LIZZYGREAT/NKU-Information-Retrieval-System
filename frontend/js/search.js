// frontend/js/search.js

document.addEventListener('DOMContentLoaded', () => {
    // 1. DOM 节点获取
    const searchInput = document.getElementById('search-input');
    const searchType = document.getElementById('search-type');
    const searchBtn = document.getElementById('search-btn');
    const suggestionsList = document.getElementById('suggestions-list');
    window.renderAuthUI();

    // 3. 执行搜索跳转逻辑
    function executeSearch() {
        const queryText = searchInput.value.trim();
        if (!queryText) return;

        const type = searchType.value;
        // 将检索词与类型拼接为 URL 参数，交由结果页进行处理与数据请求
        const targetUrl = `results.html?q=${encodeURIComponent(queryText)}&type=${encodeURIComponent(type)}`;
        window.location.href = targetUrl;
    }

    searchBtn.addEventListener('click', executeSearch);
    searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            executeSearch();
        }
    });

    // 4. 联想词功能实现与防抖控制
    function debounce(func, delay) {
        let timer;
        return function(...args) {
            clearTimeout(timer);
            timer = setTimeout(() => func.apply(this, args), delay);
        };
    }

    const fetchSuggestions = async () => {
        const query = searchInput.value.trim();
        const user = window.auth.getUser();
        
        // 仅在输入框有内容且用户已登录时触发个性化联想词
        if (!query || !user) {
            suggestionsList.style.display = 'none';
            return;
        }

        try {
            const result = await window.apiClient.get(`/log/suggestions?user_id=${user.user_id}`);
            const suggestions = result.data.suggestions;

            if (suggestions && suggestions.length > 0) {
                // 渲染前清理历史节点
                suggestionsList.innerHTML = '';
                suggestions.forEach(item => {
                    const li = document.createElement('li');
                    li.textContent = item;
                    // 点击联想词自动补全并执行搜索
                    li.addEventListener('click', () => {
                        searchInput.value = item;
                        suggestionsList.style.display = 'none';
                        executeSearch();
                    });
                    suggestionsList.appendChild(li);
                });
                suggestionsList.style.display = 'block';
            } else {
                suggestionsList.style.display = 'none';
            }
        } catch (error) {
            console.error('Failed to load suggestions:', error);
            suggestionsList.style.display = 'none';
        }
    };

    // 绑定防抖处理后的输入事件，延迟时间设为 300ms
    searchInput.addEventListener('input', debounce(fetchSuggestions, 300));

    // 点击页面空白处关闭联想词下拉框
    document.addEventListener('click', (e) => {
        if (!searchInput.contains(e.target) && !suggestionsList.contains(e.target)) {
            suggestionsList.style.display = 'none';
        }
    });
});