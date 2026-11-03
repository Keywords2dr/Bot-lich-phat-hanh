let allImages = [];
let pubList = [
    { name: 'Kim-Dong' },
    { name: 'IPM' },
    { name: 'NXB-Tre' },
    { name: 'AMAK' }
];
let activeFilter = 'ALL';
let reportPubFilter = 'ALL';
let reportStatusFilter = 'ALL';
let currentMode = 'latest';
let currentLogs = '';
let currentErrorReport = '';
let lastResults = [];
let currentAbortController = null;

const PUB_STYLES = {
    'Kim-Dong': {
        badge: 'bg-red-500/20 text-red-300 border-red-500/40',
        dot: 'bg-red-500',
        bar: 'bg-red-500',
        filterActive: 'bg-red-600 text-white font-bold shadow-lg shadow-red-600/25'
    },
    'IPM': {
        badge: 'bg-green-500/20 text-green-300 border-green-500/40',
        dot: 'bg-green-500',
        bar: 'bg-green-500',
        filterActive: 'bg-green-600 text-white font-bold shadow-lg shadow-green-600/25'
    },
    'NXB-Tre': {
        badge: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40',
        dot: 'bg-yellow-400',
        bar: 'bg-yellow-400',
        filterActive: 'bg-yellow-500 text-slate-950 font-bold shadow-lg shadow-yellow-500/25'
    },
    'AMAK': {
        badge: 'bg-sky-400/20 text-white border-sky-300/50',
        dot: 'bg-sky-300',
        bar: 'bg-sky-400',
        filterActive: 'bg-sky-400 text-slate-950 font-bold shadow-lg shadow-sky-400/25'
    }
};

function getPubStyle(pubName) {
    return PUB_STYLES[pubName] || {
        badge: 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40',
        dot: 'bg-indigo-400',
        bar: 'bg-indigo-500',
        filterActive: 'bg-indigo-500 text-white'
    };
}

function showToast(msg) {
    const toast = document.getElementById('toast');
    document.getElementById('toast-msg').innerText = msg;
    toast.classList.remove('hidden');
    clearTimeout(window._toastTimer);
    window._toastTimer = setTimeout(() => toast.classList.add('hidden'), 2600);
}

function switchView(viewName) {
    const views = ['dashboard', 'gallery', 'console'];
    views.forEach(v => {
        document.getElementById(`view-${v}`).classList.toggle('hidden', v !== viewName);
        const navBtn = document.getElementById(`nav-${v}`);
        navBtn.classList.toggle('active', v === viewName);
    });

    const titles = {
        dashboard: ['Trung Tâm Điều Khiển', 'Cấu hình thông số quét, theo dõi log trực tiếp và kiểm tra báo cáo'],
        gallery: ['Kho Lưu Trữ Ảnh', 'Quản lý, tìm kiếm và xem chi tiết toàn bộ lịch phát hành đã tải về máy'],
        console: ['Nhật Ký & Báo Lỗi', 'Kiểm tra log hệ thống chi tiết và sao chép nhanh thông tin chẩn đoán']
    };
    document.getElementById('view-title').innerText = titles[viewName][0];
    document.getElementById('view-subtitle').innerText = titles[viewName][1];
}

function setMode(mode) {
    currentMode = mode;
    document.querySelectorAll('.mode-btn').forEach(btn => {
        const active = btn.dataset.mode === mode;
        btn.className = active
            ? 'mode-btn py-2.5 px-3 rounded-xl border border-indigo-500 bg-indigo-500/20 text-indigo-200 font-bold text-left transition'
            : 'mode-btn py-2.5 px-3 rounded-xl border border-slate-800 bg-slate-900/60 text-slate-400 hover:text-slate-200 font-semibold text-left transition';
    });

    document.getElementById('input-single').classList.toggle('hidden', mode !== 'single');
    document.getElementById('input-year').classList.toggle('hidden', mode !== 'full_year' && mode !== 'range');
    document.getElementById('input-range').classList.toggle('hidden', mode !== 'range');
}

function toggleAllPubs(checked) {
    document.querySelectorAll('.pub-cb').forEach(cb => cb.checked = checked);
}

function resetForm() {
    toggleAllPubs(true);
    setMode('latest');
    document.querySelectorAll('.src-cb').forEach(cb => cb.checked = true);
    showToast('Đã đặt lại cấu hình mặc định');
}

async function copyText(text, successMsg) {
    if (!text || !text.trim()) {
        showToast('Chưa có dữ liệu để sao chép!');
        return;
    }
    try {
        await navigator.clipboard.writeText(text);
    } catch {
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
    }
    showToast(successMsg);
}

function copyLogs() {
    copyText(currentLogs, 'Đã sao chép toàn bộ Log vào Clipboard!');
}

function copyErrorReport() {
    copyText(currentErrorReport, 'Đã sao chép Báo cáo lỗi vào Clipboard!');
}

function getFilteredReportResults() {
    return lastResults.filter(r => {
        const matchPub = reportPubFilter === 'ALL' || r.publisher.toLowerCase() === reportPubFilter.toLowerCase();
        let matchStatus = true;
        if (reportStatusFilter === 'SUCCESS') matchStatus = r.status === 'SUCCESS';
        else if (reportStatusFilter === 'NOT_PUBLISHED') matchStatus = r.status === 'NOT_PUBLISHED';
        else if (reportStatusFilter === 'FAILED') matchStatus = r.status !== 'SUCCESS' && r.status !== 'NOT_PUBLISHED';
        return matchPub && matchStatus;
    });
}

function copyResultsSummary() {
    const filtered = getFilteredReportResults();
    if (!filtered.length) {
        showToast('Không có dữ liệu trong bộ lọc hiện tại để copy!');
        return;
    }
    const text = filtered
        .map(r => `${r.publisher.padEnd(10)} | ${r.target.padEnd(8)} | ${r.status.padEnd(13)} | ${r.message}`)
        .join('\n');
    copyText(text, `Đã sao chép ${filtered.length} dòng kết quả!`);
}

function downloadLogs() {
    if (!currentLogs.trim()) {
        showToast('Chưa có log để tải về!');
        return;
    }
    const blob = new Blob([currentLogs], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `lichbot_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.log`;
    a.click();
    URL.revokeObjectURL(url);
}

function clearLogs() {
    currentLogs = '';
    document.getElementById('live-log-box').innerHTML = '<div class="text-slate-500">Đã xóa log.</div>';
    document.getElementById('console-full-log').innerText = 'Đã xóa log.';
    showToast('Đã làm sạch nhật ký');
}

function formatLogLineHTML(line) {
    const escaped = line.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const lower = line.toLowerCase();
    if (line.includes('===')) {
        return `<div class="text-indigo-400 font-bold pt-2 border-t border-slate-800/60">${escaped}</div>`;
    }
    if (lower.includes('[da huy]') || lower.includes('loi:') || lower.includes('khong tim thay')) {
        return `<div class="text-rose-400 font-semibold">${escaped}</div>`;
    }
    if (lower.includes('da tim thay') || lower.includes('da luu may') || lower.includes('lay ngay lich')) {
        return `<div class="text-emerald-400 font-semibold">${escaped}</div>`;
    }
    if (lower.includes('nghi giua cac nxb') || lower.includes('[policy]') || lower.includes('chua dang')) {
        return `<div class="text-amber-300">${escaped}</div>`;
    }
    if (lower.includes('bo qua')) {
        return `<div class="text-slate-500">${escaped}</div>`;
    }
    if (lower.includes('khop, thang')) {
        return `<div class="text-cyan-300">${escaped}</div>`;
    }
    return `<div class="text-slate-300">${escaped}</div>`;
}

function renderColoredLogs(rawText) {
    const box = document.getElementById('live-log-box');
    const lines = rawText.split('\n').filter(l => l.trim() !== '');
    box.innerHTML = lines.map(formatLogLineHTML).join('');
    box.scrollTop = box.scrollHeight;
}

async function openLocalFolder() {
    const res = await fetch('/api/open-folder', { method: 'POST' });
    const data = await res.json();
    if (data.ok) {
        showToast('Đã mở thư mục fb_downloads trên Windows!');
    } else {
        showToast(data.error || 'Không thể mở thư mục');
    }
}

function openLightbox(name) {
    const item = allImages.find(x => x.name === name);
    document.getElementById('lb-img').src = `/downloads/${name}?t=${Date.now()}`;
    document.getElementById('lb-title').innerText = name;
    document.getElementById('lb-meta').innerText = item
        ? `NXB: ${item.publisher} • Kỳ: ${item.period || 'N/A'} • Dung lượng: ${item.size_kb} KB • Cập nhật: ${item.mtime}`
        : '';
    document.getElementById('lb-download').href = `/downloads/${name}`;
    document.getElementById('lb-delete').onclick = () => deleteImage(name);
    document.getElementById('lightbox').classList.remove('hidden');
}

function closeLightbox() {
    document.getElementById('lightbox').classList.add('hidden');
}

async function deleteImage(name) {
    if (!confirm(`Bạn có chắc muốn xóa ảnh "${name}" khỏi máy?`)) return;
    const res = await fetch(`/api/images/${encodeURIComponent(name)}`, { method: 'DELETE' });
    if (res.ok) {
        const data = await res.json();
        allImages = data.images || [];
        closeLightbox();
        updateGalleryUI();
        showToast(`Đã xóa ${name}`);
    }
}

function updateGalleryUI() {
    document.getElementById('sidebar-img-count').innerText = allImages.length;
    renderGalleryFilters();
    renderGallery();
}

function renderGalleryFilters() {
    const container = document.getElementById('gallery-filters');
    const items = ['ALL', ...pubList.map(p => p.name)];
    container.innerHTML = items.map(name => {
        const count = name === 'ALL'
            ? allImages.length
            : allImages.filter(i => i.publisher.toLowerCase() === name.toLowerCase()).length;
        const active = activeFilter === name;
        let cls = 'bg-slate-900 border border-slate-800 text-slate-300 hover:border-slate-700 px-3.5 py-1.5 rounded-xl transition font-medium';
        if (active) {
            cls = name === 'ALL'
                ? 'bg-indigo-600 text-white font-bold px-3.5 py-1.5 rounded-xl shadow-lg shadow-indigo-600/25'
                : `${getPubStyle(name).filterActive} px-3.5 py-1.5 rounded-xl`;
        }
        const label = name === 'ALL' ? `Tất cả (${count})` : `${name} (${count})`;
        return `<button onclick="setGalleryFilter('${name}')" class="${cls}">${label}</button>`;
    }).join('');
}

function setGalleryFilter(name) {
    activeFilter = name;
    renderGalleryFilters();
    renderGallery();
}

function renderGallery() {
    const grid = document.getElementById('gallery-grid');
    const q = (document.getElementById('gallery-search')?.value || '').trim().toLowerCase();

    const filtered = allImages.filter(img => {
        const matchPub = activeFilter === 'ALL' || img.publisher.toLowerCase() === activeFilter.toLowerCase();
        const matchQuery = !q || img.name.toLowerCase().includes(q) || (img.period && img.period.toLowerCase().includes(q));
        return matchPub && matchQuery;
    });

    if (!filtered.length) {
        grid.innerHTML = `<div class="col-span-full panel-card p-12 text-center text-slate-500 text-sm">Không tìm thấy poster nào khớp với bộ lọc hiện tại.</div>`;
        return;
    }

    grid.innerHTML = filtered.map(img => {
        const style = getPubStyle(img.publisher);
        return `
        <div onclick="openLightbox('${img.name}')" class="group cursor-pointer panel-card overflow-hidden hover:border-indigo-500/60 transition flex flex-col shadow-lg">
            <div class="relative h-48 bg-slate-950 overflow-hidden">
                <img src="/downloads/${img.name}" loading="lazy" class="w-full h-full object-cover group-hover:scale-105 transition duration-300">
                <span class="absolute top-2.5 left-2.5 backdrop-blur-md text-[11px] font-bold px-2.5 py-0.5 rounded-lg border ${style.badge}">
                    ${img.publisher}
                </span>
                ${img.period ? `<span class="absolute top-2.5 right-2.5 bg-slate-950/90 backdrop-blur text-[11px] font-mono font-semibold text-amber-300 px-2.5 py-0.5 rounded-lg border border-amber-500/30">${img.period}</span>` : ''}
            </div>
            <div class="p-3.5 flex flex-col gap-1 mt-auto border-t border-slate-800/70 bg-slate-900/50">
                <div class="text-xs font-semibold text-slate-200 truncate">${img.name}</div>
                <div class="flex justify-between items-center text-[11px] text-slate-400">
                    <span>${img.mtime}</span>
                    <span class="font-mono text-slate-300">${img.size_kb} KB</span>
                </div>
            </div>
        </div>`;
    }).join('');
}

function statusBadgeHTML(status) {
    if (status === 'SUCCESS') {
        return '<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-[11px] font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">✓ THÀNH CÔNG</span>';
    }
    if (status === 'NOT_PUBLISHED') {
        return '<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-[11px] font-bold bg-amber-500/15 text-amber-300 border border-amber-500/30">⏳ CHƯA ĐĂNG</span>';
    }
    if (status === 'NOT_FOUND') {
        return '<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-[11px] font-bold bg-rose-500/15 text-rose-400 border border-rose-500/30">✕ KHÔNG THẤY</span>';
    }
    return '<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-[11px] font-bold bg-rose-600/25 text-rose-300 border border-rose-500/40">⚠ LỖI</span>';
}

/* ==== BỘ LỌC & HIỂN THỊ BÁO CÁO NÂNG CAO ==== */
function setReportPubFilter(pubName) {
    reportPubFilter = pubName;
    renderReportSection();
}

function setReportStatusFilter(statusKey) {
    reportStatusFilter = statusKey;
    renderReportSection();
}

function findMatchingImage(publisher, target, message) {
    const fileMatch = message.match(/([A-Za-z0-9_-]+_\d{4}-\d{2}\.(?:jpg|jpeg|png|webp))/i);
    if (fileMatch) {
        const found = allImages.find(i => i.name.toLowerCase() === fileMatch[1].toLowerCase());
        if (found) return found.name;
    }
    if (target && target !== 'Mới nhất') {
        const prefix = `${publisher}_${target}`.toLowerCase();
        const found = allImages.find(i => i.name.toLowerCase().startsWith(prefix));
        if (found) return found.name;
    }
    return null;
}

function renderReportSection() {
    if (!lastResults.length) {
        document.getElementById('report-empty').classList.remove('hidden');
        document.getElementById('report-table-wrap').classList.add('hidden');
        document.getElementById('report-toolbar').classList.add('hidden');
        document.getElementById('report-count-badge').classList.add('hidden');
        return;
    }

    document.getElementById('report-empty').classList.add('hidden');
    document.getElementById('report-table-wrap').classList.remove('hidden');
    document.getElementById('report-toolbar').classList.remove('hidden');
    document.getElementById('report-count-badge').classList.remove('hidden');

    // 1. Thẻ tóm tắt tiến độ theo từng NXB có trong phiên chạy
    const uniquePubs = [...new Set(lastResults.map(r => r.publisher))];
    const summaryEl = document.getElementById('report-pub-summary');
    summaryEl.innerHTML = uniquePubs.map(pubName => {
        const rows = lastResults.filter(r => r.publisher === pubName);
        const okRows = rows.filter(r => r.status === 'SUCCESS').length;
        const pct = rows.length ? Math.round((okRows / rows.length) * 100) : 0;
        const style = getPubStyle(pubName);
        const isSelected = reportPubFilter === pubName;
        const ringCls = isSelected ? 'ring-2 ring-indigo-400 bg-slate-800/90' : 'bg-slate-950/80 hover:bg-slate-900';
        return `
        <div onclick="setReportPubFilter('${isSelected ? 'ALL' : pubName}')" class="cursor-pointer p-2.5 rounded-xl border border-slate-800 transition ${ringCls}">
            <div class="flex justify-between items-center text-xs">
                <span class="font-bold flex items-center gap-1.5 text-slate-200">
                    <span class="w-2 h-2 rounded-full ${style.dot}"></span>
                    ${pubName}
                </span>
                <span class="font-mono font-bold text-slate-300">${okRows}/${rows.length}</span>
            </div>
            <div class="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden mt-2">
                <div class="h-full ${style.bar} transition-all duration-300" style="width: ${pct}%"></div>
            </div>
        </div>`;
    }).join('');

    // 2. Nút lọc theo NXB
    const pubFiltersEl = document.getElementById('report-pub-filters');
    const pubOptions = ['ALL', ...uniquePubs];
    pubFiltersEl.innerHTML = pubOptions.map(name => {
        const count = name === 'ALL'
            ? lastResults.length
            : lastResults.filter(r => r.publisher === name).length;
        const active = reportPubFilter === name;
        let cls = 'bg-slate-950 border border-slate-800 text-slate-400 hover:text-slate-200 px-3 py-1 rounded-lg transition font-semibold';
        if (active) {
            cls = name === 'ALL'
                ? 'bg-indigo-600 text-white font-bold px-3 py-1 rounded-lg shadow'
                : `${getPubStyle(name).filterActive} px-3 py-1 rounded-lg`;
        }
        const label = name === 'ALL' ? `Tất cả NXB (${count})` : `${name} (${count})`;
        return `<button onclick="setReportPubFilter('${name}')" class="${cls}">${label}</button>`;
    }).join('');

    // 3. Nút lọc theo Trạng Thái
    const statusOptions = [
        { key: 'ALL', label: 'Mọi trạng thái' },
        { key: 'SUCCESS', label: '✓ Thành công' },
        { key: 'NOT_PUBLISHED', label: '⏳ Chưa đăng' },
        { key: 'FAILED', label: '✕ Lỗi / Không thấy' }
    ];
    const statusFiltersEl = document.getElementById('report-status-filters');
    statusFiltersEl.innerHTML = statusOptions.map(st => {
        const active = reportStatusFilter === st.key;
        const cls = active
            ? 'bg-slate-200 text-slate-950 font-bold px-2.5 py-1 rounded-lg'
            : 'bg-slate-950 border border-slate-800 text-slate-400 hover:text-slate-200 px-2.5 py-1 rounded-lg transition';
        return `<button onclick="setReportStatusFilter('${st.key}')" class="${cls}">${st.label}</button>`;
    }).join('');

    // 4. Render các dòng kết quả sau khi lọc
    const filtered = getFilteredReportResults();
    document.getElementById('report-count-badge').innerText = `${filtered.length}/${lastResults.length} mục`;

    const tbody = document.getElementById('result-tbody');
    if (!filtered.length) {
        tbody.innerHTML = `<tr><td colspan="6" class="py-8 text-center text-slate-500">Không có mục nào khớp với bộ lọc đang chọn.</td></tr>`;
        return;
    }

    tbody.innerHTML = filtered.map((r, idx) => {
        const style = getPubStyle(r.publisher);
        const imgName = r.status === 'SUCCESS' ? findMatchingImage(r.publisher, r.target, r.message) : null;
        const actionHTML = imgName
            ? `<button onclick="openLightbox('${imgName}')" class="text-[11px] bg-indigo-500/15 hover:bg-indigo-500/30 text-indigo-300 border border-indigo-500/30 px-2.5 py-1 rounded-lg font-semibold transition">🖼 Xem ảnh</button>`
            : `<span class="text-slate-600">—</span>`;

        return `
        <tr class="hover:bg-slate-800/40 transition">
            <td class="py-3 px-4 text-center font-mono text-slate-500">${idx + 1}</td>
            <td class="py-3 px-4">
                <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-lg border text-xs font-bold ${style.badge}">
                    <span class="w-1.5 h-1.5 rounded-full ${style.dot}"></span>
                    ${r.publisher}
                </span>
            </td>
            <td class="py-3 px-4 font-mono font-bold text-amber-300">${r.target}</td>
            <td class="py-3 px-4">${statusBadgeHTML(r.status)}</td>
            <td class="py-3 px-4 text-slate-300">${r.message}</td>
            <td class="py-3 px-4 text-right whitespace-nowrap">${actionHTML}</td>
        </tr>`;
    }).join('');
}

function setRunningUI(running, cancelled = false) {
    const btnRun = document.getElementById('btn-run');
    const btnCancel = document.getElementById('btn-cancel');
    const headerCancel = document.getElementById('header-cancel-btn');
    const status = document.getElementById('runner-status');

    btnRun.disabled = running;
    btnCancel.classList.toggle('hidden', !running);
    headerCancel.classList.toggle('hidden', !running);

    if (running) {
        btnRun.innerHTML = '<span class="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full"></span> <span>Đang quét Facebook...</span>';
        btnRun.classList.add('opacity-70', 'cursor-not-allowed');
        status.className = 'flex items-center gap-2 bg-amber-500/15 border border-amber-500/40 text-amber-300 px-3.5 py-2 rounded-xl text-xs font-bold';
        status.innerHTML = '<span class="w-2 h-2 rounded-full bg-amber-400 animate-ping"></span><span>Đang thực thi...</span>';
    } else if (cancelled) {
        btnRun.innerHTML = '<span>🚀 Bắt Đầu Quét Lịch</span>';
        btnRun.classList.remove('opacity-70', 'cursor-not-allowed');
        status.className = 'flex items-center gap-2 bg-rose-500/15 border border-rose-500/40 text-rose-300 px-3.5 py-2 rounded-xl text-xs font-bold';
        status.innerHTML = '<span class="w-2 h-2 rounded-full bg-rose-400"></span><span>Đã dừng bởi người dùng</span>';
    } else {
        btnRun.innerHTML = '<span>🚀 Bắt Đầu Quét Lịch</span>';
        btnRun.classList.remove('opacity-70', 'cursor-not-allowed');
        status.className = 'flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 px-3.5 py-2 rounded-xl text-xs font-bold';
        status.innerHTML = '<span class="w-2 h-2 rounded-full bg-emerald-400"></span><span>Sẵn sàng</span>';
    }
}

async function cancelScan() {
    showToast('🛑 Đang gửi lệnh dừng tiến trình...');
    try {
        await fetch('/api/cancel', { method: 'POST' });
    } catch {}
    if (currentAbortController) {
        currentAbortController.abort();
    }
}

async function startScan() {
    const pubs = [...document.querySelectorAll('.pub-cb:checked')].map(e => e.value);
    const srcs = [...document.querySelectorAll('.src-cb:checked')].map(e => e.value);
    const fullLog = document.getElementById('console-full-log');

    const singleYearEl = document.getElementById('single_year_sel');
    const singleMonthEl = document.getElementById('single_month_sel');
    const singleYear = singleYearEl ? singleYearEl.value : '2026';
    const singleMonth = singleMonthEl ? String(singleMonthEl.value).padStart(2, '0') : '11';
    const singleTarget = `${singleYear}-${singleMonth}`;

    const yearEl = document.getElementById('year_sel');
    const startMonthEl = document.getElementById('start_month_sel');
    const endMonthEl = document.getElementById('end_month_sel');

    const year = yearEl ? yearEl.value : '2026';
    const startMonth = startMonthEl ? parseInt(startMonthEl.value) : 1;
    const endMonth = endMonthEl ? parseInt(endMonthEl.value) : 12;

    currentLogs = '';
    currentErrorReport = '';
    document.getElementById('live-log-box').innerHTML = '';
    fullLog.innerText = '';
    document.getElementById('dashboard-error-banner').classList.add('hidden');
    document.getElementById('sidebar-err-badge').classList.add('hidden');

    currentAbortController = new AbortController();
    setRunningUI(true);

    let wasCancelled = false;
    try {
        const res = await fetch('/api/stream-run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            signal: currentAbortController.signal,
            body: JSON.stringify({
                publishers: pubs,
                mode: currentMode,
                single_target: singleTarget,
                year: year,
                start_month: startMonth,
                end_month: endMonth,
                sources: srcs,
                use_local: document.getElementById('use_local').checked,
                use_drive: document.getElementById('use_drive').checked
            })
        });

        const reader = res.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const events = buffer.split('\n\n');
            buffer = events.pop();

            for (const ev of events) {
                if (!ev.startsWith('data: ')) continue;
                const payload = JSON.parse(ev.slice(6));
                if (payload.type === 'log') {
                    currentLogs += payload.text;
                    renderColoredLogs(currentLogs);
                    fullLog.innerText = currentLogs;
                    fullLog.scrollTop = fullLog.scrollHeight;
                } else if (payload.type === 'done') {
                    wasCancelled = Boolean(payload.cancelled);
                    handleScanDone(payload);
                }
            }
        }
    } catch (err) {
        if (err.name === 'AbortError') {
            wasCancelled = true;
            currentLogs += '\n[ĐÃ HỦY] Đã ngắt tiến trình quét ngay lập tức theo yêu cầu người dùng.\n';
            renderColoredLogs(currentLogs);
            fullLog.innerText = currentLogs;
            showToast('Đã hủy tiến trình quét thành công!');
        } else {
            currentErrorReport = `[LỖI KẾT NỐI SERVER] ${err}`;
            showErrors(currentErrorReport);
        }
    } finally {
        currentAbortController = null;
        setRunningUI(false, wasCancelled);
    }
}

function showErrors(text) {
    document.getElementById('dashboard-error-text').innerText = text;
    document.getElementById('console-error-box').innerText = text;
    document.getElementById('dashboard-error-banner').classList.remove('hidden');
    document.getElementById('sidebar-err-badge').classList.remove('hidden');
}

function handleScanDone(data) {
    document.getElementById('kpi-time').innerText = `${data.elapsed || 0}s`;

    if (data.images) {
        allImages = data.images;
        updateGalleryUI();
    }

    const results = data.results || [];
    lastResults = results;
    reportPubFilter = 'ALL';
    reportStatusFilter = 'ALL';

    const total = results.length;
    const okCount = results.filter(r => r.status === 'SUCCESS').length;
    const unpubCount = results.filter(r => r.status === 'NOT_PUBLISHED').length;
    const failCount = results.filter(r => r.status !== 'SUCCESS' && r.status !== 'NOT_PUBLISHED').length;

    document.getElementById('kpi-total').innerText = total;
    document.getElementById('kpi-success').innerText = okCount;
    document.getElementById('kpi-unpublished').innerText = unpubCount;
    document.getElementById('kpi-failed').innerText = failCount;

    renderReportSection();

    const errLines = [];
    if (data.cancelled) {
        errLines.push('[ĐÃ HỦY] Phiên chạy đã được dừng giữa chừng bởi người dùng.');
    } else if (!data.ok && data.error) {
        errLines.push(`[LỖI HỆ THỐNG] ${data.error}`);
        if (data.traceback) errLines.push(data.traceback);
    }
    results.filter(r => r.status !== 'SUCCESS').forEach(r => {
        errLines.push(`[${r.status}] ${r.publisher} (Kỳ ${r.target}): ${r.message}`);
    });

    if (errLines.length > 0) {
        currentErrorReport = errLines.join('\n');
        showErrors(currentErrorReport);
    } else {
        document.getElementById('console-error-box').innerText = 'Tuyệt vời! Phiên quét vừa rồi không có lỗi nào.';
    }
}

async function initApp() {
    setMode('latest');
    try {
        const res = await fetch('/api/init');
        const data = await res.json();
        if (data.publishers && data.publishers.length) {
            pubList = data.publishers;
        }
        allImages = data.images || [];
        if (data.max_period) {
            document.getElementById('sb-max-period').innerText = data.max_period;
        }
    } catch {}
    updateGalleryUI();
}

initApp();