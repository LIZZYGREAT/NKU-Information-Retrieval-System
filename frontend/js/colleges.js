const FALLBACK_COLLEGES = [
    { college_id: 1, college_name: "文学院", category: "人文社科类" },
    { college_id: 2, college_name: "历史学院", category: "人文社科类" },
    { college_id: 3, college_name: "哲学院", category: "人文社科类" },
    { college_id: 4, college_name: "外国语学院", category: "人文社科类" },
    { college_id: 5, college_name: "汉语言文化学院", category: "人文社科类" },
    { college_id: 6, college_name: "法学院", category: "人文社科类" },
    { college_id: 7, college_name: "周恩来政府管理学院", category: "人文社科类" },
    { college_id: 8, college_name: "马克思主义学院", category: "人文社科类" },
    { college_id: 9, college_name: "社会学院", category: "人文社科类" },
    { college_id: 10, college_name: "新闻与传播学院", category: "人文社科类" },
    { college_id: 11, college_name: "经济学院", category: "人文社科类" },
    { college_id: 12, college_name: "金融学院", category: "人文社科类" },
    { college_id: 13, college_name: "商学院", category: "人文社科类" },
    { college_id: 14, college_name: "旅游与服务学院", category: "人文社科类" },
    { college_id: 15, college_name: "国际教育学院", category: "人文社科类" },
    { college_id: 16, college_name: "数学科学学院", category: "理工医学类" },
    { college_id: 17, college_name: "统计与数据科学学院", category: "理工医学类" },
    { college_id: 18, college_name: "物理科学学院", category: "理工医学类" },
    { college_id: 19, college_name: "电子信息与光学工程学院", category: "理工医学类" },
    { college_id: 20, college_name: "化学学院", category: "理工医学类" },
    { college_id: 21, college_name: "材料科学与工程学院", category: "理工医学类" },
    { college_id: 22, college_name: "生命科学学院", category: "理工医学类" },
    { college_id: 23, college_name: "环境科学与工程学院", category: "理工医学类" },
    { college_id: 24, college_name: "医学院", category: "理工医学类" },
    { college_id: 25, college_name: "药学院", category: "理工医学类" },
    { college_id: 26, college_name: "计算机学院", category: "理工医学类" },
    { college_id: 27, college_name: "软件学院", category: "理工医学类" },
    { college_id: 28, college_name: "密码与网络空间安全学院", category: "理工医学类" },
    { college_id: 29, college_name: "人工智能学院", category: "理工医学类" },
];

function renderColleges(selectEl, colleges, selectedId) {
    selectEl.innerHTML = '<option value="">-- 请选择学院 --</option>';
    const groups = {};
    colleges.forEach((c) => {
        const cat = c.category || "其他";
        if (!groups[cat]) {
            groups[cat] = document.createElement("optgroup");
            groups[cat].label = cat;
        }
        const opt = document.createElement("option");
        opt.value = c.college_id;
        opt.textContent = c.college_name;
        groups[cat].appendChild(opt);
    });
    Object.values(groups).forEach((g) => selectEl.appendChild(g));
    if (selectedId) selectEl.value = String(selectedId);
}

async function populateCollegeSelect(selectEl, selectedId) {
    try {
        const res = await window.apiClient.get("/user/colleges");
        const list = res.data && res.data.length ? res.data : FALLBACK_COLLEGES;
        renderColleges(selectEl, list, selectedId);
    } catch (e) {
        renderColleges(selectEl, FALLBACK_COLLEGES, selectedId);
    }
}

window.populateCollegeSelect = populateCollegeSelect;
