(function () {
    if (!window.adminAuth.isLoggedIn()) {
        location.href = 'admin_login.html';
        return;
    }

    const admin = window.adminAuth.getAdmin();
    document.getElementById('admin-user-label').textContent = `管理员: ${admin.username}`;

    let currentView = 'View_UserSearchActivity';
    let page = 1;
    let meta = {};
    const pageSize = 20;
    let activeFilters = [];
    const OP_LABELS = {
        eq: '等于', ne: '不等于', contains: '包含', starts_with: '开头是', ends_with: '结尾是',
        gt: '大于', gte: '大于等于', lt: '小于', lte: '小于等于',
        is_null: '为空', is_not_null: '不为空',
    };

    document.getElementById('btn-logout').onclick = () => {
        window.adminAuth.logout();
        location.href = 'admin_login.html';
    };
    document.getElementById('btn-graph').onclick = () => { location.href = 'admin_graph.html'; };
    document.getElementById('btn-search').onclick = () => { page = 1; loadView(); };
    document.getElementById('btn-add-filter').onclick = addFilter;
    document.getElementById('btn-clear-filters').onclick = () => {
        activeFilters = [];
        renderFilterTags();
        page = 1;
        loadView();
    };
    document.getElementById('filter-op').onchange = syncFilterValueInput;
    document.getElementById('btn-prev').onclick = () => { if (page > 1) { page--; loadView(); } };
    document.getElementById('btn-next').onclick = () => {
        const max = Math.ceil((meta.total || 0) / pageSize);
        if (page < max) { page++; loadView(); }
    };

    async function loadOverview() {
        const res = await window.apiClient.adminRequest('/admin/views/overview');
        const d = res.data;
        const row = document.getElementById('overview-row');
        const items = [
            ['用户总数', d.total_users],
            ['检索总次数', d.total_searches],
            ['网页缓存', d.total_pages],
            ['近7日检索', d.searches_7d],
            ['近7日活跃用户', d.active_users_7d],
            ['最热检索词', d.top_query ? `${d.top_query} (${d.top_query_count})` : '-'],
        ];
        row.innerHTML = items.map(([lbl, num]) =>
            `<div class="stat-card"><div class="num" style="font-size:14px">${esc(num)}</div><div class="lbl">${lbl}</div></div>`
        ).join('');
    }

    async function loadNav() {
        const res = await window.apiClient.adminRequest('/admin/views');
        const nav = document.getElementById('view-nav');
        nav.innerHTML = '';
        res.data.forEach((v) => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'admin-nav-btn' + (v.name === currentView ? ' active' : '');
            btn.textContent = v.label;
            btn.title = v.description || '';
            btn.onclick = () => {
                currentView = v.name;
                page = 1;
                activeFilters = [];
                document.querySelectorAll('.admin-nav-btn').forEach((b) => b.classList.remove('active'));
                btn.classList.add('active');
                renderFilterTags();
                loadView();
            };
            nav.appendChild(btn);
        });
    }

    function syncFilterValueInput() {
        const op = document.getElementById('filter-op').value;
        const el = document.getElementById('filter-value');
        const noVal = op === 'is_null' || op === 'is_not_null';
        el.disabled = noVal;
        if (noVal) el.value = '';
    }

    function fillFilterControls() {
        const fields = meta.filterable || meta.columns || [];
        document.getElementById('filter-field').innerHTML =
            fields.map((f) => `<option value="${f}">${f}</option>`).join('');
        const ops = meta.filter_ops || [];
        document.getElementById('filter-op').innerHTML =
            ops.map((o) => `<option value="${o.op}">${o.label}</option>`).join('');
        syncFilterValueInput();
    }

    function addFilter() {
        const field = document.getElementById('filter-field').value;
        const op = document.getElementById('filter-op').value;
        const value = document.getElementById('filter-value').value.trim();
        if (op !== 'is_null' && op !== 'is_not_null' && !value) {
            alert('请填写筛选值');
            return;
        }
        const item = { field, op };
        if (op !== 'is_null' && op !== 'is_not_null') item.value = value;
        activeFilters.push(item);
        document.getElementById('filter-value').value = '';
        renderFilterTags();
        page = 1;
        loadView();
    }

    function renderFilterTags() {
        const box = document.getElementById('filter-tags');
        box.innerHTML = '';
        activeFilters.forEach((f, i) => {
            const tag = document.createElement('span');
            tag.className = 'filter-tag';
            const val = f.op === 'is_null' || f.op === 'is_not_null' ? '' : ` "${f.value}"`;
            tag.innerHTML = `${f.field} ${OP_LABELS[f.op] || f.op}${val}<button type="button">×</button>`;
            tag.querySelector('button').onclick = () => {
                activeFilters.splice(i, 1);
                renderFilterTags();
                page = 1;
                loadView();
            };
            box.appendChild(tag);
        });
    }

    async function loadView() {
        const kw = document.getElementById('keyword').value.trim();
        let q = `page=${page}&page_size=${pageSize}&keyword=${encodeURIComponent(kw)}`;
        if (activeFilters.length) {
            q += `&filters=${encodeURIComponent(JSON.stringify(activeFilters))}`;
        }
        const res = await window.apiClient.adminRequest(`/admin/views/${currentView}?${q}`);
        meta = res.data;
        document.getElementById('view-desc').textContent = meta.description || '';
        fillFilterControls();
        if (meta.active_filters) activeFilters = meta.active_filters;
        renderFilterTags();

        const cols = meta.columns;
        document.querySelector('#data-table thead').innerHTML =
            `<tr>${cols.map((c) => `<th>${c}</th>`).join('')}</tr>`;
        const tbody = document.querySelector('#data-table tbody');
        tbody.innerHTML = '';
        meta.rows.forEach((row) => {
            const tr = document.createElement('tr');
            tr.innerHTML = cols.map((c) => `<td title="${esc(row[c])}">${esc(row[c])}</td>`).join('');
            tbody.appendChild(tr);
        });
        const max = Math.max(1, Math.ceil(meta.total / pageSize));
        document.getElementById('page-info').textContent = `第 ${page}/${max} 页，共 ${meta.total} 条`;
    }

    function esc(v) {
        if (v == null) return '';
        const s = typeof v === 'object' ? JSON.stringify(v) : String(v);
        return s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
    }

    loadOverview().then(loadNav).then(loadView);
})();
