document.addEventListener('DOMContentLoaded', async () => {
    if (!window.auth.isLoggedIn()) {
        window.location.href = 'login.html';
        return;
    }

    const roleSelect = document.getElementById('role-select');
    const collegeSelect = document.getElementById('college-select');
    const form = document.getElementById('onboarding-form');
    const errorEl = document.getElementById('error-msg');
    const skipBtn = document.getElementById('skip-btn');
    const submitBtn = document.getElementById('submit-btn');

    try {
        await window.populateCollegeSelect(collegeSelect);
    } catch (e) {
        errorEl.textContent = '学院列表加载失败';
        errorEl.style.color = 'red';
    }

    roleSelect.addEventListener('change', (e) => {
        if (e.target.value === '访客') {
            collegeSelect.value = '';
            collegeSelect.disabled = true;
        } else {
            collegeSelect.disabled = false;
        }
    });

    async function executeOnboarding(payload) {
        submitBtn.disabled = true;
        skipBtn.disabled = true;
        errorEl.textContent = '';
        try {
            await window.auth.completeOnboarding(payload.role, payload.collegeId, payload.interests);
            window.location.href = 'index.html';
        } catch (err) {
            errorEl.textContent = err.message || '保存失败';
            errorEl.style.color = 'red';
            submitBtn.disabled = false;
            skipBtn.disabled = false;
        }
    }

    form.addEventListener('submit', (e) => {
        e.preventDefault();
        const role = roleSelect.value;
        const collegeId = collegeSelect.value;
        const checkedInterests = Array.from(document.querySelectorAll('input[name="interest"]:checked'))
            .map((cb) => cb.value);
        if (role !== '访客' && !collegeId) {
            alert('请选择所属学院');
            return;
        }
        executeOnboarding({ role, collegeId, interests: checkedInterests });
    });

    skipBtn.addEventListener('click', () => {
        executeOnboarding({ role: '访客', collegeId: null, interests: ['综合'] });
    });
});
