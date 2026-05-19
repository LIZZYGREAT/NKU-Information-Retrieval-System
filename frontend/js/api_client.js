// frontend/js/api_client.js

const BASE_URL = 'http://localhost:8000/api';

const apiClient = {
    /**
     * 核心请求封装函数
     * @param {string} endpoint - API 路由端点
     * @param {object} options - Fetch 配置项
     * @returns {Promise<any>} 解析后的 JSON 数据
     */
    async request(endpoint, options = {}) {
        const url = `${BASE_URL}${endpoint}`;
        
        // 默认设置 JSON 请求头
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers
        };

        const config = {
            ...options,
            headers
        };

        try {
            const response = await fetch(url, config);
            const data = await response.json();

            // 处理 HTTP 错误状态码
            if (!response.ok) {
                // 401 权限校验失败拦截
                if (response.status === 401) {
                    console.warn("认证失败或凭证过期");
                    localStorage.removeItem('user'); // 清除本地无效凭证
                }
                // 抛出后端返回的错误详情
                throw new Error(data.detail || data.message || '请求失败');
            }

            return data;
        } catch (error) {
            console.error(`API Error [${endpoint}]:`, error);
            throw error;
        }
    },

    // GET 请求封装
    get(endpoint) {
        return this.request(endpoint, { method: 'GET' });
    },

    // POST 请求封装
    post(endpoint, body) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(body)
        });
    },

    // DELETE 请求封装
    delete(endpoint, body = null) {
        const options = { method: 'DELETE' };
        if (body) {
            options.body = JSON.stringify(body);
        }
        return this.request(endpoint, options);
    }
};

// 暴露为全局对象供其他页面脚本调用
window.apiClient = apiClient;