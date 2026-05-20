document.addEventListener('DOMContentLoaded', () => {
    if (window.auth.isLoggedIn()) {
        window.location.href = 'index.html';
        return;
    }

    const params = new URLSearchParams(window.location.search);
    if (params.get('registered') === '1') {
        document.getElementById('error-msg').style.color = '#137333';
        document.getElementById('error-msg').textContent = '注册成功，请登录';
    }

    const form = document.getElementById('login-form');
    const errorEl = document.getElementById('error-msg');
    const submitBtn = document.getElementById('submit-btn');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        errorEl.textContent = '';
        submitBtn.disabled = true;

        const username = document.getElementById('username').value.trim();
        const password = document.getElementById('password').value;

        try {
            await window.auth.login(username, password);
            const redirect = new URLSearchParams(window.location.search).get('redirect') || 'index.html';
            window.location.href = redirect;
        } catch (err) {
            errorEl.textContent = err.message || '登录失败';
            submitBtn.disabled = false;
        }
    });
});
