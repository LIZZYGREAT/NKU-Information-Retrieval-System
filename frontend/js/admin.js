(function () {
    if (!window.adminAuth.isLoggedIn()) {
        location.href = 'admin_login.html';
        return;
    }

    const admin = window.adminAuth.getAdmin();
    document.getElementById('admin-user-label').textContent = `管理员: ${admin.username}`;

    let currentTable = 'User';
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
    document.getElementById('btn-user-site').onclick = () => window.adminAuth.enterUserSite();
    document.getElementById('btn-user-login').onclick = () => window.adminAuth.enterUserLogin();
    document.getElementById('btn-search').onclick = () => { page = 1; loadTable(); };
    document.getElementById('btn-add-filter').onclick = addFilter;
    document.getElementById('btn-clear-filters').onclick = () => {
        activeFilters = [];
        renderFilterTags();
        page = 1;
        loadTable();
    };
    document.getElementById('filter-op').onchange = syncFilterValueInput;
    document.getElementById('keyword').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { page = 1; loadTable(); }
    });
    document.getElementById('filter-value').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') addFilter();
    });
    document.getElementById('btn-prev').onclick = () => { if (page > 1) { page--; loadTable(); } };
    document.getElementById('btn-next').onclick = () => {
        const max = Math.ceil((meta.total || 0) / pageSize);
        if (page < max) { page++; loadTable(); }
    };
    document.getElementById('btn-add').onclick = () => openForm('create', {});

    async function loadStats() {
        const res = await window.apiClient.adminRequest('/admin/stats');
        const row = document.getElementById('stats-row');
        row.innerHTML = '';
        const labels = {
            User: '用户', WebPageCache: '网页', SearchLog: '搜索日志',
            CollegeDomain: '学院', UserProfile: '画像', UserPreference: '偏好', PageLinks: '链接',
        };
        Object.entries(res.data).forEach(([k, v]) => {
            const d = document.createElement('div');
            d.className = 'stat-card';
            d.innerHTML = `<div class="num">${v}</div><div class="lbl">${labels[k] || k}</div>`;
            row.appendChild(d);
        });
    }

    async function loadNav() {
        const res = await window.apiClient.adminRequest('/admin/tables');
        const nav = document.getElementById('table-nav');
        nav.innerHTML = '';
        res.data.forEach((t) => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'admin-nav-btn' + (t.name === currentTable ? ' active' : '');
            btn.textContent = t.label;
            btn.onclick = () => {
                currentTable = t.name;
                page = 1;
                activeFilters = [];
                document.querySelectorAll('.admin-nav-btn').forEach((b) => b.classList.remove('active'));
                btn.classList.add('active');
                renderFilterTags();
                loadTable();
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
        const fieldSel = document.getElementById('filter-field');
        const opSel = document.getElementById('filter-op');
        const ops = meta.filter_ops || Object.keys(OP_LABELS).map((op) => ({ op, label: OP_LABELS[op] }));
        fieldSel.innerHTML = fields.map((f) => `<option value="${f}">${f}</option>`).join('');
        opSel.innerHTML = ops.map((o) => `<option value="${o.op}">${o.label}</option>`).join('');
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
        loadTable();
    }

    function renderFilterTags() {
        const box = document.getElementById('filter-tags');
        box.innerHTML = '';
        activeFilters.forEach((f, i) => {
            const tag = document.createElement('span');
            tag.className = 'filter-tag';
            const val = f.op === 'is_null' || f.op === 'is_not_null' ? '' : ` "${f.value}"`;
            tag.innerHTML = `${f.field} ${OP_LABELS[f.op] || f.op}${val}<button type="button" title="移除">×</button>`;
            tag.querySelector('button').onclick = () => {
                activeFilters.splice(i, 1);
                renderFilterTags();
                page = 1;
                loadTable();
            };
            box.appendChild(tag);
        });
    }

    async function loadTable() {
        const kw = document.getElementById('keyword').value.trim();
        let q = `page=${page}&page_size=${pageSize}&keyword=${encodeURIComponent(kw)}`;
        if (activeFilters.length) {
            q += `&filters=${encodeURIComponent(JSON.stringify(activeFilters))}`;
        }
        const res = await window.apiClient.adminRequest(`/admin/data/${currentTable}?${q}`);
        meta = res.data;
        fillFilterControls();
        if (meta.active_filters) activeFilters = meta.active_filters;
        renderFilterTags();
        const thead = document.querySelector('#data-table thead');
        const tbody = document.querySelector('#data-table tbody');
        const cols = meta.columns.slice();
        if (currentTable === 'WebPageCache' && !cols.includes('tags')) cols.push('tags');
        thead.innerHTML = `<tr>${cols.map((c) => `<th>${c}</th>`).join('')}<th>操作</th></tr>`;
        tbody.innerHTML = '';
        meta.rows.forEach((row) => {
            const tr = document.createElement('tr');
            const pk = row[meta.pk];
            tr.innerHTML = cols.map((c) => `<td title="${esc(row[c])}">${esc(row[c])}</td>`).join('')
                + `<td class="row-actions"><button type="button" class="btn" data-act="edit">编辑</button>`
                + `<button type="button" class="btn" data-act="del">删除</button></td>`;
            tr.querySelector('[data-act="edit"]').onclick = () => openForm('edit', row, pk);
            tr.querySelector('[data-act="del"]').onclick = () => delRow(pk);
            tbody.appendChild(tr);
        });
        const max = Math.max(1, Math.ceil(meta.total / pageSize));
        document.getElementById('page-info').textContent = `第 ${page}/${max} 页，共 ${meta.total} 条`;
        document.getElementById('btn-add').style.display =
            meta.insertable && meta.insertable.length ? '' : 'none';
    }

    function esc(v) {
        if (v == null) return '';
        const s = typeof v === 'object' ? JSON.stringify(v) : String(v);
        return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
    }

    function openForm(mode, row, pk) {
        const fields = mode === 'create' ? meta.insertable : meta.editable;
        const root = document.getElementById('modal-root');
        root.innerHTML = '';
        const mask = document.createElement('div');
        mask.className = 'modal-mask';
        const box = document.createElement('div');
        box.className = 'modal-box';
        box.innerHTML = `<h3 style="margin-top:0">${mode === 'create' ? '新增' : '编辑'} · ${currentTable}</h3><form id="row-form"></form>`;
        const form = box.querySelector('#row-form');
        fields.forEach((f) => {
            const lab = document.createElement('label');
            lab.textContent = f;
            const val = row[f] != null ? row[f] : '';
            let input;
            if (f === 'tags') {
                input = document.createElement('textarea');
                input.rows = 3;
                input.value = typeof val === 'object' ? JSON.stringify(val, null, 2) : val;
            } else if (f === 'role' && currentTable === 'User') {
                input = document.createElement('select');
                ['user', 'admin'].forEach((o) => {
                    const opt = document.createElement('option');
                    opt.value = o; opt.textContent = o;
                    if (val === o) opt.selected = true;
                    input.appendChild(opt);
                });
            } else if (f === 'role' && currentTable === 'UserProfile') {
                input = document.createElement('select');
                ['本科生', '研究生', '教职工', '访客'].forEach((o) => {
                    const opt = document.createElement('option');
                    opt.value = o; opt.textContent = o;
                    if (val === o) opt.selected = true;
                    input.appendChild(opt);
                });
            } else if (f === 'search_type') {
                input = document.createElement('select');
                ['site', 'phrase', 'wildcard', 'document'].forEach((o) => {
                    const opt = document.createElement('option');
                    opt.value = o; opt.textContent = o;
                    if (val === o) opt.selected = true;
                    input.appendChild(opt);
                });
            } else {
                input = document.createElement('input');
                input.type = f === 'password' ? 'password' : 'text';
                input.value = val;
            }
            input.name = f;
            form.appendChild(lab);
            form.appendChild(input);
        });
        const actions = document.createElement('div');
        actions.className = 'modal-actions';
        actions.innerHTML = '<button type="button" class="btn" id="m-cancel">取消</button><button type="submit" class="btn btn-primary">保存</button>';
        form.appendChild(actions);
        box.querySelector('#m-cancel').onclick = () => { root.innerHTML = ''; };
        form.onsubmit = async (e) => {
            e.preventDefault();
            const data = {};
            fields.forEach((f) => {
                const el = form.elements[f];
                if (!el || !el.value) return;
                if (f === 'tags') {
                    try { data[f] = JSON.parse(el.value); } catch { alert('tags 须为合法 JSON'); return; }
                } else data[f] = el.value;
            });
            try {
                if (mode === 'create') {
                    await window.apiClient.adminRequest(`/admin/data/${currentTable}`, {
                        method: 'POST',
                        body: JSON.stringify({ data }),
                    });
                } else {
                    await window.apiClient.adminRequest(`/admin/data/${currentTable}/${encodeURIComponent(pk)}`, {
                        method: 'PUT',
                        body: JSON.stringify({ data }),
                    });
                }
                root.innerHTML = '';
                loadTable();
                loadStats();
            } catch (ex) {
                alert(ex.message);
            }
        };
        mask.appendChild(box);
        root.appendChild(mask);
    }

    async function delRow(pk) {
        if (!confirm('确认删除该记录？')) return;
        try {
            await window.apiClient.adminRequest(`/admin/data/${currentTable}/${encodeURIComponent(pk)}`, {
                method: 'DELETE',
            });
            loadTable();
            loadStats();
        } catch (ex) {
            alert(ex.message);
        }
    }

    loadNav().then(loadStats).then(loadTable);
})();
