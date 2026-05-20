// frontend/js/onboarding.js
document.addEventListener('DOMContentLoaded', () => {
    // 强制鉴权拦截
    if (!window.auth.isLoggedIn()) {
        window.location.href = 'login.html';
        return;
    }

    // 与 SQL 插入顺序完全对应的学院字典
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

    const roleSelect = document.getElementById('role-select');
    const collegeSelect = document.getElementById('college-select');
    const form = document.getElementById('onboarding-form');
    const errorEl = document.getElementById('error-msg');
    const skipBtn = document.getElementById('skip-btn');
    const submitBtn = document.getElementById('submit-btn');

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

    // 2. 角色与学院的表单联动
    roleSelect.addEventListener('change', (e) => {
        if (e.target.value === '访客') {
            collegeSelect.value = '';
            collegeSelect.disabled = true;
        } else {
            collegeSelect.disabled = false;
        }
    });

    // 3. 执行写入与跳转逻辑
    async function executeOnboarding(payload) {
        errorEl.textContent = '';
        submitBtn.disabled = true;
        skipBtn.disabled = true;

        try {
            await window.auth.completeOnboarding(payload.role, payload.collegeId, payload.interests);
            window.location.href = 'index.html';
        } catch (err) {
            errorEl.textContent = err.message || '配置保存失败';
            submitBtn.disabled = false;
            skipBtn.disabled = false;
        }
    }

    // 4. 标准提交流程
    form.addEventListener('submit', (e) => {
        e.preventDefault();
        const role = roleSelect.value;
        const collegeId = collegeSelect.value;
        
        if (role !== '访客' && !collegeId) {
            errorEl.textContent = '请选择所属学院';
            return;
        }

        const checkedInterests = Array.from(document.querySelectorAll('input[name="interest"]:checked'))
            .map(cb => cb.value);

        executeOnboarding({ role: role, collegeId: collegeId, interests: checkedInterests });
    });

    // 5. 跳过兜底流程
    skipBtn.addEventListener('click', () => {
        executeOnboarding({ role: '访客', collegeId: null, interests: ['综合'] });
    });
});