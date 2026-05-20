document.addEventListener('DOMContentLoaded', () => {
    if (window.auth.isLoggedIn()) {
        window.location.href = 'index.html';
        return;
    }

    const form = document.getElementById('register-form');
    const errorEl = document.getElementById('error-msg');
    const submitBtn = document.getElementById('submit-btn');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        errorEl.textContent = '';

        const username = document.getElementById('username').value.trim();
        const email = document.getElementById('email').value.trim();
        const password = document.getElementById('password').value;
        const password2 = document.getElementById('password2').value;

        if (password !== password2) {
            errorEl.textContent = '两次输入的密码不一致';
            return;
        }

        submitBtn.disabled = true;

        try {
            await window.auth.register(username, email, password);
            window.location.href = 'login.html?registered=1';
        } catch (err) {
            errorEl.textContent = err.message || '注册失败';
            submitBtn.disabled = false;
        }
    });
});
