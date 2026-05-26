const BASE_URL = (window.APP_CONFIG && window.APP_CONFIG.API_BASE_URL) || '/api';
const REQUEST_TIMEOUT_MS = 30000;

const apiClient = {
    async request(endpoint, options = {}) {
        const url = `${BASE_URL}${endpoint}`;
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers
        };
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
        const config = { ...options, headers, signal: controller.signal };
        try {
            const response = await fetch(url, config);
            clearTimeout(timer);
            let data;
            try {
                data = await response.json();
            } catch {
                throw new Error('服务器响应格式错误');
            }
            if (!response.ok) {
                if (response.status === 401) {
                    localStorage.removeItem('user');
                    localStorage.removeItem('admin');
                }
                const detail = data.detail;
                const msg = Array.isArray(detail)
                    ? detail.map((d) => {
                        const field = Array.isArray(d.loc) ? d.loc.filter(x => x !== 'body').join('.') : '';
                        const prefix = field ? `${field}: ` : '';
                        return prefix + (d.msg || JSON.stringify(d));
                    }).join('; ')
                    : (detail || data.message || '请求失败');
                throw new Error(msg);
            }
            return data;
        } catch (error) {
            clearTimeout(timer);
            if (error.name === 'AbortError') {
                throw new Error('请求超时，请确认后端服务已启动');
            }
            console.error(`API Error [${endpoint}]:`, error);
            throw error;
        }
    },
    get(endpoint) {
        return this.request(endpoint, { method: 'GET' });
    },
    post(endpoint, body) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(body)
        });
    },
    put(endpoint, body) {
        return this.request(endpoint, {
            method: 'PUT',
            body: JSON.stringify(body),
        });
    },
    delete(endpoint, body = null) {
        const options = { method: 'DELETE' };
        if (body) options.body = JSON.stringify(body);
        return this.request(endpoint, options);
    },
    adminRequest(endpoint, options = {}) {
        const admin = window.adminAuth && window.adminAuth.getAdmin();
        if (!admin) throw new Error('未登录管理后台');
        return this.request(endpoint, {
            ...options,
            headers: { 'X-Admin-Id': String(admin.user_id), ...(options.headers || {}) },
        });
    },
};

window.apiClient = apiClient;
