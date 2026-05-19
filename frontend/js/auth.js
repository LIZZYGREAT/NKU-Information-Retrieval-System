// frontend/js/auth.js

const auth = {
    /**
     * 检查当前是否处于登录状态
     * @returns {boolean}
     */
    isLoggedIn() {
        return localStorage.getItem('user') !== null;
    },

    /**
     * 获取当前登录的用户信息
     * @returns {object|null} {user_id, username, role}
     */
    getUser() {
        const userStr = localStorage.getItem('user');
        if (!userStr) return null;
        try {
            return JSON.parse(userStr);
        } catch (e) {
            this.clearSession();
            return null;
        }
    },

    /**
     * 发起登录请求并持久化状态
     */
    async login(username, password) {
        try {
            const result = await window.apiClient.post('/user/login', {
                username,
                password
            });
            
            // 登录成功，将后端返回的用户信息存入 LocalStorage
            if (result.code === 200 && result.data) {
                localStorage.setItem('user', JSON.stringify(result.data));
                return result.data;
            }
        } catch (error) {
            throw error;
        }
    },

    /**
     * 发起注册请求
     */
    async register(username, email, password) {
        try {
            const result = await window.apiClient.post('/user/register', {
                username,
                email,
                password
            });
            return result.data;
        } catch (error) {
            throw error;
        }
    },

    /**
     * 触发带有数据库事务的彻底注销操作
     */
    async deleteAccount() {
        const user = this.getUser();
        if (!user || !user.user_id) return false;

        try {
            // 调用后端的 DELETE /api/user/logout_permanently 接口
            const result = await window.apiClient.delete(`/user/logout_permanently?user_id=${user.user_id}`);
            if (result.code === 200) {
                this.clearSession();
                return true;
            }
        } catch (error) {
            throw error;
        }
    },

    /**
     * 清除本地会话
     */
    clearSession() {
        localStorage.removeItem('user');
    }
};

window.auth = auth;