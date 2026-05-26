function adminPortalHref() {
    return window.adminAuth && window.adminAuth.isLoggedIn() ? 'admin.html' : 'admin_login.html';
}

function renderAuthUI(containerId) {
    const authSection = document.getElementById(containerId || 'auth-section');
    if (!authSection || !window.auth) return;
    const adminLink = `<a href="${adminPortalHref()}" class="btn" style="margin-left:10px;">管理后台</a>`;

    if (window.auth.isLoggedIn()) {
        const user = window.auth.getUser();
        authSection.innerHTML = `
            <span>欢迎, ${user.username}</span>
            <button type="button" onclick="location.href='user_dashboard.html'" style="margin-left:10px;">用户中心</button>
            ${adminLink}
            <button type="button" id="logout-btn" style="margin-left:10px;">退出</button>
        `;
        document.getElementById('logout-btn').addEventListener('click', () => {
            window.auth.clearSession();
            location.reload();
        });
    } else {
        authSection.innerHTML = `
            <a href="login.html">登录</a>
            <a href="register.html" style="margin-left:10px;">注册</a>
            ${adminLink}
        `;
    }
}

window.renderAuthUI = renderAuthUI;
