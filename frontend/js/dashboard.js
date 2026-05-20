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

    const colleges = [
        { id: 1, name: '文学院', type: '人文社科类' }, { id: 2, name: '历史学院', type: '人文社科类' },
        { id: 3, name: '哲学院', type: '人文社科类' }, { id: 4, name: '外国语学院', type: '人文社科类' },
        { id: 5, name: '法学院', type: '人文社科类' }, { id: 6, name: '周恩来政府管理学院', type: '人文社科类' },
        { id: 7, name: '马克思主义学院', type: '人文社科类' }, { id: 8, name: '汉语言文化学院', type: '人文社科类' },
        { id: 9, name: '国际教育学院', type: '人文社科类' }, { id: 10, name: '经济学院', type: '人文社科类' },
        { id: 11, name: '金融学院', type: '人文社科类' }, { id: 12, name: '商学院', type: '人文社科类' },
        { id: 13, name: '旅游与服务学院', type: '人文社科类' }, { id: 14, name: '社会学院', type: '人文社科类' },
        { id: 15, name: '新闻与传播学院', type: '人文社科类' },
        { id: 16, name: '数学科学学院', type: '理工医学类' }, { id: 17, name: '物理科学学院', type: '理工医学类' },
        { id: 18, name: '化学学院', type: '理工医学类' }, { id: 19, name: '生命科学学院', type: '理工医学类' },
        { id: 20, name: '环境科学与工程学院', type: '理工医学类' }, { id: 21, name: '材料科学与工程学院', type: '理工医学类' },
        { id: 22, name: '电子信息与光学工程学院', type: '理工医学类' }, { id: 23, name: '计算机学院', type: '理工医学类' },
        { id: 24, name: '人工智能学院', type: '理工医学类' }, { id: 25, name: '软件学院', type: '理工医学类' },
        { id: 26, name: '密码与网络空间安全学院', type: '理工医学类' }, { id: 27, name: '统计与数据科学学院', type: '理工医学类' },
        { id: 28, name: '医学院', type: '理工医学类' }, { id: 29, name: '药学院', type: '理工医学类' }
    ];

    // 1. 初始化学院下拉框
    function initColleges() {
        collegeSelect.innerHTML = '<option value="">-- 请选择学院 --</option>';
        let optgroupArt = document.createElement('optgroup');
        optgroupArt.label = "人文社科类";
        let optgroupSci = document.createElement('optgroup');
        optgroupSci.label = "理工医学类";

        colleges.forEach(c => {
            let opt = document.createElement('option');
            opt.value = c.id;
            opt.textContent = c.name;
            if (c.type === '人文社科类') optgroupArt.appendChild(opt);
            else optgroupSci.appendChild(opt);
        });

        collegeSelect.appendChild(optgroupArt);
        collegeSelect.appendChild(optgroupSci);
    }
    initColleges();

    async function loadUserProfile() {
        try {
            const res = await window.apiClient.get(`/user/profile?user_id=${user.user_id}`);
            const profile = res.data;

            if (profile.username) usernameEl.textContent = profile.username;
            if (profile.email) emailEl.textContent = profile.email;

            roleSelect.value = profile.role || '访客';
            
            if (profile.role === '访客') {
                collegeSelect.disabled = true;
            } else {
                collegeSelect.disabled = false;
                collegeSelect.value = profile.college_id || '';
            }

            const checkboxes = document.querySelectorAll('input[name="interest"]');
            checkboxes.forEach(cb => {
                cb.checked = profile.interests.includes(cb.value);
            });
        } catch (error) {
            console.error('加载画像失败', error);
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