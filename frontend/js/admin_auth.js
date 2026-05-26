const adminAuth = {
    getAdmin() {
        const s = localStorage.getItem('admin');
        if (!s) return null;
        try {
            return JSON.parse(s);
        } catch {
            localStorage.removeItem('admin');
            return null;
        }
    },
    isLoggedIn() {
        return !!this.getAdmin();
    },
    async login(account, password) {
        const res = await window.apiClient.post('/admin/login', { account, password });
        if (res.code === 200 && res.data) {
            localStorage.setItem('admin', JSON.stringify(res.data));
            return res.data;
        }
        throw new Error('登录失败');
    },
    logout() {
        localStorage.removeItem('admin');
    },
    enterUserSite() {
        window.location.href = 'index.html';
    },
    enterUserLogin() {
        window.location.href = 'login.html';
    },
};

window.adminAuth = adminAuth;
