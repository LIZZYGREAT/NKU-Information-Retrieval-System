document.addEventListener('DOMContentLoaded', () => {
    // 权限校验拦截
    if (!window.auth.isLoggedIn()) {
        window.location.href = 'login.html?redirect=user_dashboard.html';
        return;
    }

    const user = window.auth.getUser();
    const usernameEl = document.getElementById('info-username');
    const emailEl = document.getElementById('info-email');
    usernameEl.textContent = user.username || '—';
    emailEl.textContent = user.email || '—';

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


    const roleSelect = document.getElementById('role-select');
    const collegeSelect = document.getElementById('college-select');
    const profileForm = document.getElementById('profile-form');

    async function loadUserProfile() {
        try {
            const res = await window.apiClient.get(`/user/profile?user_id=${user.user_id}`);
            const profile = res.data;

            if (profile.username) usernameEl.textContent = profile.username;
            if (profile.email) emailEl.textContent = profile.email;

            await window.populateCollegeSelect(collegeSelect, profile.college_id);

            roleSelect.value = profile.role || '访客';
            
            if (profile.role === '访客') {
                collegeSelect.disabled = true;
            } else {
                collegeSelect.disabled = false;
            }

            const checkboxes = document.querySelectorAll('input[name="interest"]');
            checkboxes.forEach(cb => {
                cb.checked = profile.interests.includes(cb.value);
            });
        } catch (error) {
            console.error('加载画像失败', error);
            await window.populateCollegeSelect(collegeSelect);
        }
    }
    
    loadUserProfile();

    // 2. 身份切换联动
    roleSelect.addEventListener('change', (e) => {
        if (e.target.value === '访客') {
            collegeSelect.value = '';
            collegeSelect.disabled = true;
        } else {
            collegeSelect.disabled = false;
        }
    });

    // 3. 提交修改
    profileForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const role = roleSelect.value;
        const collegeId = collegeSelect.value;
        const checkedInterests = Array.from(document.querySelectorAll('input[name="interest"]:checked'))
            .map(cb => cb.value);

        if (role !== '访客' && !collegeId) {
            alert('请选择所属学院');
            return;
        }

        const msgEl = document.getElementById('save-msg');
        msgEl.textContent = '保存中...';
        msgEl.style.color = '#5f6368';

        try {
            // 直接调用已封装好的 auth 方法复写数据
            await window.auth.completeOnboarding(role, collegeId, checkedInterests);
            await loadUserProfile();
            msgEl.textContent = '修改已保存生效';
            msgEl.style.color = 'green';
            setTimeout(() => msgEl.textContent = '', 3000);
        } catch (error) {
            msgEl.textContent = '保存失败: ' + error.message;
            msgEl.style.color = 'red';
        }
    });
});