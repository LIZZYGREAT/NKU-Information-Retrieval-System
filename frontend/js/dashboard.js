document.addEventListener('DOMContentLoaded', () => {
    // 权限校验拦截
    if (!window.auth.isLoggedIn()) {
        window.location.href = 'login.html?redirect=user_dashboard.html';
        return;
    }

    const user = window.auth.getUser();
    document.getElementById('info-username').textContent = user.username;

    // 获取并渲染近期查询日志
    loadSearchLogs();

    async function loadSearchLogs() {
        const list = document.getElementById('log-list');
        try {
            const response = await window.apiClient.get(`/log/suggestions?user_id=${user.user_id}`);
            const logs = response.data.suggestions;
            
            if (logs && logs.length > 0) {
                logs.forEach(log => {
                    const li = document.createElement('li');
                    li.textContent = log;
                    list.appendChild(li);
                });
            } else {
                list.innerHTML = '<li>暂无查询记录</li>';
            }
        } catch (error) {
            list.innerHTML = `<li style="color:red;">日志获取失败: ${error.message}</li>`;
        }
    }

    // 绑定注销账号事件，触发底层事务逻辑
    document.getElementById('delete-account-btn').addEventListener('click', async () => {
        const confirmDelete = confirm('确定要彻底注销吗？此操作涉及多张数据库表的级联删除，无法恢复。');
        if (!confirmDelete) return;

        try {
            const success = await window.auth.deleteAccount();
            if (success) {
                alert('账号已注销成功，相关数据已清理。');
                window.location.href = 'index.html';
            }
        } catch (error) {
            alert(`注销失败: ${error.message}`);
        }
    });
});