// 전역 상태
let categories = {};
let currentCategory = null;
let currentSource = null;
let editMode = false;
/** 수집 기간: false=오늘만, true=오늘+어제 */
let includeYesterday = false;
/** 출처 추가 모달 유형: RSS | GOOGLE_NEWS */
let addSourceType = 'RSS';

const EMPTY_STATE_HTML = `
  <div class="empty-state">
    <div class="empty-visual" aria-hidden="true">
      <div class="empty-orb"></div>
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none">
        <path d="M4 7.5A2.5 2.5 0 0 1 6.5 5h11A2.5 2.5 0 0 1 20 7.5v9A2.5 2.5 0 0 1 17.5 19h-11A2.5 2.5 0 0 1 4 16.5v-9Z" stroke="currentColor" stroke-width="1.4"/>
        <path d="M8 9.5h8M8 12.5h5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
      </svg>
    </div>
    <h2>파이프라인을 시작하세요</h2>
    <p>왼쪽에서 카테고리를 고른 뒤 뉴스 소스를 선택하면<br>오늘 기사를 수집·추출합니다.</p>
  </div>
`;

document.addEventListener('DOMContentLoaded', async () => {
    await loadCategories();
    setupEventListeners();
});

async function loadCategories() {
    try {
        const response = await fetch('/api/categories');
        const data = await response.json();
        categories = data.categories;
        renderCategories();
    } catch (error) {
        console.error('카테고리 로드 오류:', error);
    }
}

function renderCategories() {
    const container = document.getElementById('categories');
    container.innerHTML = '';

    Object.keys(categories).forEach(category => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'category-btn' + (currentCategory === category ? ' active' : '');
        btn.textContent = category;
        btn.onclick = () => selectCategory(category, btn);
        container.appendChild(btn);
    });
}

function selectCategory(category, btn) {
    document.querySelectorAll('.category-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    currentCategory = category;
    currentSource = null;

    const hint = document.getElementById('sourcePanelHint');
    if (hint) {
        const n = (categories[category] || []).length;
        hint.textContent = `${category} · 소스 ${n}개`;
    }

    renderSources(category);
    clearResults();
}

function renderSources(category) {
    const container = document.getElementById('sources');
    container.innerHTML = '';

    const sources = categories[category] || [];
    if (sources.length === 0) {
        container.innerHTML = '<span class="panel-hint" style="padding:0">등록된 소스가 없습니다</span>';
        return;
    }

    sources.forEach(source => {
        const wrapper = document.createElement('div');
        wrapper.className = 'source-wrapper';

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'source-btn' + (currentSource && currentSource.url === source.url ? ' active' : '');
        const isGn = (source.type || '').toUpperCase() === 'GOOGLE_NEWS';
        if (isGn) {
            btn.innerHTML = `<span class="src-badge gn">GN</span>${escapeHtml(source.keyword || source.name)}`;
            btn.title = `Google News · ${source.keyword || source.name}\n${source.url}`;
        } else {
            btn.textContent = source.name;
            btn.title = source.url;
        }
        btn.onclick = () => fetchArticles(source, btn);
        wrapper.appendChild(btn);

        if (editMode) {
            const deleteBtn = document.createElement('button');
            deleteBtn.type = 'button';
            deleteBtn.className = 'delete-btn';
            deleteBtn.textContent = '×';
            deleteBtn.title = '삭제';
            deleteBtn.onclick = (e) => {
                e.stopPropagation();
                deleteSource(category, source.name);
            };
            wrapper.appendChild(deleteBtn);
        }

        container.appendChild(wrapper);
    });
}

async function fetchArticles(source, btn, rangeOverride = null) {
    document.querySelectorAll('.source-btn').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
    currentSource = source;
    if (rangeOverride !== null) {
        includeYesterday = !!rangeOverride;
    }
    const label = source.keyword || source.name || '피드';
    showLoading('수집 중…', `${label} 준비 중`);
    try {
        const response = await fetch('/api/fetch-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: source.url,
                include_yesterday: includeYesterday,
                type: source.type || 'RSS',
                keyword: source.keyword || null,
                name: label,
            })
        });
        const final = await readNdjsonStream(response, updateLoadingProgress);
        hideLoading();
        if (!final || !final.success) {
            showError(`오류: ${(final && final.error) || '수집 실패'}`);
            return;
        }
        const data = final.data;
        if (data && data.success) {
            displayArticles(data, source);
        } else {
            showError(`오류: ${(data && data.error) || '수집 실패'}`);
        }
    } catch (error) {
        hideLoading();
        showError(`요청 오류: ${error.message}`);
    }
}

function displayArticles(data, source) {
    setSourcesPanelVisible(true);
    const resultsArea = document.getElementById('results');
    resultsArea.innerHTML = '';

    const failedBadge = data.failed > 0
        ? `<span class="failed-badge">본문 미수집 ${data.failed}</span>`
        : `<span class="success-badge">본문 전체 수집</span>`;
    const saveBtnId = `saveBtn-${Date.now()}`;
    const rangeLabel = includeYesterday ? '오늘+어제' : '오늘만';
    const isGn = (source.type || '').toUpperCase() === 'GOOGLE_NEWS' || data.is_google_news;
    const kicker = isGn ? 'Google News' : 'Feed';
    const heading = isGn
        ? `키워드 · ${source.keyword || data.keyword || source.name}`
        : (data.title || source.name);

    const header = document.createElement('div');
    header.className = 'feed-header';
    header.innerHTML = `
        <div class="feed-header-top">
            <div>
                <span class="feed-kicker">${kicker}</span>
                <h3>${escapeHtml(heading)}</h3>
            </div>
            <div class="feed-header-actions">
                <div class="date-range-group" role="group" aria-label="수집 기간">
                    <button type="button" class="date-range-option ${!includeYesterday ? 'selected' : ''}"
                            data-range="today" aria-pressed="${!includeYesterday}">오늘만</button>
                    <button type="button" class="date-range-option ${includeYesterday ? 'selected' : ''}"
                            data-range="yesterday" aria-pressed="${includeYesterday}">오늘+어제</button>
                </div>
                <button class="btn-save" id="${saveBtnId}" type="button">DB 저장</button>
            </div>
        </div>
        <div class="feed-info">
            <span class="stat-chip"><span class="mono" title="${escapeHtml(source.url)}">${escapeHtml(source.url)}</span></span>
            <span class="stat-chip">피드 ${data.count}</span>
            <span class="stat-chip">기간 · ${rangeLabel} ${data.today_articles}건</span>
            ${failedBadge}
            <span class="hint-no-save">본문 실패 건은 DB에 저장되지 않습니다</span>
        </div>
    `;

    header.querySelectorAll('.date-range-option').forEach(rangeBtn => {
        rangeBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const wantYesterday = rangeBtn.getAttribute('data-range') === 'yesterday';
            if (wantYesterday === includeYesterday) return;
            const activeBtn = document.querySelector('.source-btn.active');
            fetchArticles(source, activeBtn || null, wantYesterday);
        });
    });
    header.querySelector(`#${saveBtnId}`).addEventListener('click', () => {
        saveToDb(source.name, source.url);
    });
    resultsArea.appendChild(header);

    // 기사만 스크롤 영역 (헤더와 분리 → 헤더 위로 비치지 않음)
    const scroll = document.createElement('div');
    scroll.className = 'results-scroll';

    if (data.articles && data.articles.length > 0) {
        const list = document.createElement('div');
        list.className = 'article-list';

        data.articles.forEach((article, index) => {
            const articleEl = document.createElement('div');
            articleEl.className = 'article';

            let date = article.published || '';
            try {
                date = new Date(article.published).toLocaleString('ko-KR', {
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit'
                });
            } catch (_) { /* keep raw */ }

            const methodBadge = getMethodBadge(article.method);
            const articleId = `article-${index}-${Date.now()}`;
            const noContent = !article.content || article.content === '본문을 가져올 수 없습니다.';

            const publisherBadge = article.publisher
                ? `<span class="publisher-badge" title="언론사">${escapeHtml(article.publisher)}</span>`
                : '';

            articleEl.innerHTML = `
                <div class="article-header" data-article-id="${articleId}">
                    <div class="article-title">
                        <span class="toggle-icon" data-toggle="${articleId}">▶</span>
                        <span class="article-title-text">${escapeHtml(article.title)}</span>
                    </div>
                    <div class="article-meta">
                        ${publisherBadge}
                        <span class="article-date">${escapeHtml(date)}</span>
                        ${methodBadge}
                    </div>
                </div>
                <div id="${articleId}" class="article-content-container">
                    <div class="article-content ${noContent ? 'no-content' : ''}">${escapeHtml(article.content || '본문을 가져올 수 없습니다.')}</div>
                    <a href="${escapeHtml(article.link)}" target="_blank" rel="noopener" class="article-link">원문 보기 →</a>
                </div>
            `;

            articleEl.querySelector('.article-header').addEventListener('click', () => {
                toggleArticle(articleId, articleEl);
            });

            list.appendChild(articleEl);
        });

        scroll.appendChild(list);
    } else {
        scroll.innerHTML = `
            <div class="empty-state" style="min-height:200px">
                <h2>해당 기간 기사가 없습니다</h2>
                <p>기간을 바꾸거나 다른 소스를 선택해 보세요.</p>
            </div>
        `;
    }

    resultsArea.appendChild(scroll);
}

function getMethodBadge(method) {
    const map = {
        'Readability':   { cls: 'readability',   label: 'Read' },
        'BeautifulSoup': { cls: 'beautifulsoup', label: 'BS4' },
        'ChosunFusion':  { cls: 'chosun',        label: 'Chosun' },
        'HankyungBody':  { cls: 'hankyung',      label: '한경' },
        'DongaBody':     { cls: 'donga',         label: '동아' },
        'MkBody':        { cls: 'hankyung',      label: '매경' },
        'GeekNewsBody':  { cls: 'readability',   label: 'GeekNews' },
        'JSON-LD':       { cls: 'jsonld',        label: 'JSON-LD' },
    };
    const m = map[method];
    if (m) {
        return `<span class="method-badge ${m.cls}" title="${escapeHtml(method)}">${m.label}</span>`;
    }
    return `<span class="method-badge failed" title="추출 실패">실패</span>`;
}

async function testAllRss() {
    showLoading('RSS 테스트 중…', '전체 피드 연결 확인');
    try {
        const response = await fetch('/api/test');
        const results = await response.json();
        hideLoading();
        displayTestResults(results);
    } catch (error) {
        hideLoading();
        showError(`테스트 오류: ${error.message}`);
    }
}

function displayTestResults(results) {
    const modal = document.getElementById('testModal');
    const resultsContainer = document.getElementById('testResults');
    resultsContainer.innerHTML = '';

    Object.entries(results).forEach(([category, feeds]) => {
        const categoryDiv = document.createElement('div');
        categoryDiv.className = 'category-result';

        const title = document.createElement('h3');
        title.textContent = category;
        categoryDiv.appendChild(title);

        feeds.forEach(feed => {
            const itemDiv = document.createElement('div');
            const ok = (feed.status || '').includes('정상');
            itemDiv.className = `test-item ${ok ? 'success' : 'error'}`;
            itemDiv.innerHTML = `
                <div class="test-item-name">${escapeHtml(feed.name)}</div>
                <div class="test-item-status">${escapeHtml(feed.status)} · ${escapeHtml(feed.message || '')}</div>
            `;
            categoryDiv.appendChild(itemDiv);
        });

        resultsContainer.appendChild(categoryDiv);
    });

    modal.classList.remove('hidden');
}

function escapeHtml(text) {
    if (text == null) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

function showLoading(title = '수집 중…', detail = '준비 중') {
    const el = document.getElementById('loading');
    const t = document.getElementById('loadingTitle');
    const d = document.getElementById('loadingDetail');
    const c = document.getElementById('loadingCount');
    const log = document.getElementById('loadingLog');
    if (t) t.textContent = title;
    if (d) d.textContent = detail;
    if (c) c.textContent = '';
    if (log) log.innerHTML = '';
    el.classList.remove('hidden');
}

function hideLoading() {
    document.getElementById('loading').classList.add('hidden');
}

function updateLoadingProgress(obj) {
    const msg = obj.message || '';
    const t = document.getElementById('loadingTitle');
    const d = document.getElementById('loadingDetail');
    const c = document.getElementById('loadingCount');
    const log = document.getElementById('loadingLog');

    const phase = obj.phase || '';
    if (phase === 'batch_start' || phase === 'start' || phase === 'fetch_rss') {
        if (t) t.textContent = '수집 중…';
    } else if (phase === 'saving') {
        if (t) t.textContent = '저장 중…';
    } else if (phase === 'batch_done' || phase === 'saved' || phase === 'collect_done') {
        if (t) t.textContent = '마무리 중…';
    } else if (phase === 'error' || phase === 'feed_error') {
        if (t) t.textContent = '오류 발생';
    }

    if (d && msg) d.textContent = msg;

    if (c) {
        if (obj.current != null && obj.total != null) {
            c.textContent = `${obj.current} / ${obj.total}`;
        } else if (obj.total_feeds != null) {
            c.textContent = `출처 ${obj.total_feeds}개`;
        } else if (obj.total_saved != null) {
            c.textContent = `저장 ${obj.total_saved}건`;
        } else {
            c.textContent = '';
        }
    }

    if (log && msg) {
        const li = document.createElement('li');
        if (phase === 'error' || phase === 'feed_error') li.className = 'is-error';
        const time = new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        li.textContent = `${time}  ${msg}`;
        log.appendChild(li);
        // 최근 80줄만 유지
        while (log.children.length > 80) log.removeChild(log.firstChild);
        log.scrollTop = log.scrollHeight;
    }
}

/** NDJSON 스트림 읽기 → progress 콜백, done 객체 반환 */
async function readNdjsonStream(response, onProgress) {
    if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `HTTP ${response.status}`);
    }
    if (!response.body) {
        throw new Error('스트림을 지원하지 않는 환경입니다');
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    let finalPayload = null;

    while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() || '';
        for (const line of lines) {
            if (!line.trim()) continue;
            let obj;
            try {
                obj = JSON.parse(line);
            } catch {
                continue;
            }
            if (obj.type === 'progress') {
                if (onProgress) onProgress(obj);
            } else if (obj.type === 'done') {
                finalPayload = obj;
            }
        }
    }
    if (buf.trim()) {
        try {
            const obj = JSON.parse(buf);
            if (obj.type === 'progress' && onProgress) onProgress(obj);
            if (obj.type === 'done') finalPayload = obj;
        } catch { /* ignore */ }
    }
    return finalPayload;
}

function setSourcesPanelVisible(visible) {
    const workspace = document.querySelector('.workspace');
    if (!workspace) return;
    workspace.classList.toggle('hide-sources', !visible);
}

function showError(message) {
    setSourcesPanelVisible(true);
    document.getElementById('results').innerHTML =
        `<div class="placeholder is-error">${escapeHtml(message)}</div>`;
}

function clearResults() {
    setSourcesPanelVisible(true);
    document.getElementById('results').innerHTML = EMPTY_STATE_HTML;
}

function setupEventListeners() {
    document.getElementById('testAllBtn').addEventListener('click', testAllRss);
    document.getElementById('saveAllBtn').addEventListener('click', saveAll);
    document.getElementById('dbStatsBtn').addEventListener('click', showDbStats);

    document.getElementById('addSourceBtn').addEventListener('click', openAddSourceModal);
    document.getElementById('closeAddModal').addEventListener('click', closeAddSourceModal);
    document.getElementById('cancelAddSource').addEventListener('click', closeAddSourceModal);
    document.getElementById('submitAddSource').addEventListener('click', submitAddSource);
    document.getElementById('addSourceModal').addEventListener('click', (e) => {
        if (e.target.id === 'addSourceModal') closeAddSourceModal();
    });
    document.querySelectorAll('.source-type-tab').forEach(tab => {
        tab.addEventListener('click', () => setAddSourceType(tab.dataset.type));
    });

    const editBtn = document.getElementById('editBtn');
    if (editBtn) editBtn.addEventListener('click', toggleEditMode);

    document.querySelector('#testModal .close-btn').addEventListener('click', () => {
        document.getElementById('testModal').classList.add('hidden');
    });
    document.getElementById('testModal').addEventListener('click', (e) => {
        if (e.target.id === 'testModal') {
            document.getElementById('testModal').classList.add('hidden');
        }
    });
}

function setAddSourceType(type) {
    addSourceType = type === 'GOOGLE_NEWS' ? 'GOOGLE_NEWS' : 'RSS';
    document.querySelectorAll('.source-type-tab').forEach(tab => {
        tab.classList.toggle('selected', tab.dataset.type === addSourceType);
    });
    const fieldsRss = document.getElementById('fieldsRss');
    const fieldsGn  = document.getElementById('fieldsGoogle');
    if (fieldsRss) fieldsRss.classList.toggle('hidden', addSourceType !== 'RSS');
    if (fieldsGn)  fieldsGn.classList.toggle('hidden', addSourceType !== 'GOOGLE_NEWS');
}

function openAddSourceModal() {
    const sel = document.getElementById('addCategory');
    sel.innerHTML = '<option value="">선택하세요</option>';
    Object.keys(categories).forEach(cat => {
        const opt = document.createElement('option');
        opt.value = cat;
        opt.textContent = cat;
        if (currentCategory && cat === currentCategory) opt.selected = true;
        sel.appendChild(opt);
    });
    const newOpt = document.createElement('option');
    newOpt.value = '__new__';
    newOpt.textContent = '+ 새 카테고리 직접 입력';
    sel.appendChild(newOpt);

    document.getElementById('addName').value = '';
    document.getElementById('addUrl').value = '';
    const kw = document.getElementById('addKeyword');
    if (kw) kw.value = '';
    document.getElementById('addSourceMsg').className = 'form-msg hidden';
    document.getElementById('addSourceMsg').textContent = '';
    setAddSourceType('RSS');
    document.getElementById('addSourceModal').classList.remove('hidden');
}

function closeAddSourceModal() {
    document.getElementById('addSourceModal').classList.add('hidden');
}

async function submitAddSource() {
    let category = document.getElementById('addCategory').value;
    const msg  = document.getElementById('addSourceMsg');

    if (category === '__new__') {
        category = prompt('새 카테고리 이름을 입력하세요:');
        if (!category || !category.trim()) return;
        category = category.trim();
    }

    if (!category) {
        msg.textContent = '카테고리를 선택하세요.';
        msg.className = 'form-msg error';
        return;
    }

    let body;
    if (addSourceType === 'GOOGLE_NEWS') {
        const keyword = (document.getElementById('addKeyword')?.value || '').trim();
        if (!keyword) {
            msg.textContent = '검색 키워드를 입력하세요.';
            msg.className = 'form-msg error';
            return;
        }
        body = { category, type: 'GOOGLE_NEWS', keyword };
    } else {
        const name = document.getElementById('addName').value.trim();
        const url  = document.getElementById('addUrl').value.trim();
        if (!name || !url) {
            msg.textContent = '출처 이름과 RSS URL을 입력하세요.';
            msg.className = 'form-msg error';
            return;
        }
        body = { category, type: 'RSS', name, url };
    }

    const btn = document.getElementById('submitAddSource');
    btn.disabled = true;
    btn.textContent = '추가 중…';

    try {
        const res = await fetch('/api/add-source', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await res.json();

        if (data.success) {
            categories = data.categories.categories || data.categories;
            renderCategories();
            if (currentCategory === category) renderSources(category);
            // 새 카테고리면 선택 상태 갱신
            if (!currentCategory || currentCategory !== category) {
                currentCategory = category;
                renderCategories();
                renderSources(category);
            }
            msg.textContent = data.message || '추가됨';
            msg.className = 'form-msg success';
            document.getElementById('addName').value = '';
            document.getElementById('addUrl').value = '';
            if (document.getElementById('addKeyword')) document.getElementById('addKeyword').value = '';
            setTimeout(closeAddSourceModal, 1000);
        } else {
            msg.textContent = data.error || '실패';
            msg.className = 'form-msg error';
        }
    } catch (e) {
        msg.textContent = '오류: ' + e.message;
        msg.className = 'form-msg error';
    } finally {
        btn.disabled = false;
        btn.textContent = '추가하기';
    }
}

function toggleArticle(articleId, articleEl) {
    const container = document.getElementById(articleId);
    if (!container) return;
    const card = articleEl || container.closest('.article');
    const icon = document.querySelector(`[data-toggle="${articleId}"]`);
    const isOpen = card ? card.classList.contains('is-open') : container.style.display === 'block';

    if (isOpen) {
        if (card) card.classList.remove('is-open');
        if (icon) icon.classList.remove('open');
    } else {
        if (card) card.classList.add('is-open');
        if (icon) icon.classList.add('open');
    }
}

function toggleEditMode() {
    editMode = !editMode;
    const editBtn = document.getElementById('editBtn');
    const label = document.getElementById('editBtnLabel');

    if (editBtn) editBtn.classList.toggle('active', editMode);
    if (label) label.textContent = editMode ? '편집 완료' : '편집';

    if (currentCategory) renderSources(currentCategory);
}

async function deleteSource(category, sourceName) {
    if (!confirm(`"${sourceName}"을(를) 삭제하시겠습니까?`)) return;

    try {
        const response = await fetch('/api/delete-source', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ category, source_name: sourceName })
        });
        const data = await response.json();

        if (data.success) {
            categories = data.categories.categories || data.categories;
            renderSources(category);
        } else {
            alert(`삭제 실패: ${data.error}`);
        }
    } catch (error) {
        alert(`삭제 중 오류: ${error.message}`);
    }
}

async function saveToDb(feedName, rssUrl) {
    const btn = document.querySelector('.btn-save');
    if (btn) {
        btn.disabled = true;
        btn.textContent = '저장 중…';
    }

    const src = currentSource || {};
    showLoading('수집·저장 중…', `${feedName} 시작`);
    try {
        const res = await fetch('/api/fetch-and-save-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: feedName,
                url: rssUrl,
                include_yesterday: includeYesterday,
                type: src.type || 'RSS',
                keyword: src.keyword || null,
            })
        });
        const final = await readNdjsonStream(res, updateLoadingProgress);
        hideLoading();
        if (!final || !final.success) {
            if (btn) {
                btn.textContent = '저장 실패';
                btn.style.background = '#DC2626';
                btn.disabled = false;
            }
            return;
        }
        const data = final.data || {};
        if (data.success && btn && data.db) {
            const { saved, skipped, no_content = 0, errors } = data.db;
            btn.textContent =
                `저장 ${saved} · 중복 ${skipped} · 본문없음 ${no_content}` +
                (errors ? ` · 오류 ${errors}` : '');
            btn.style.background = 'linear-gradient(180deg, #10B981 0%, #059669 100%)';
        } else if (btn) {
            btn.textContent = '저장 실패';
            btn.style.background = '#DC2626';
            btn.disabled = false;
        }
    } catch (e) {
        hideLoading();
        if (btn) {
            btn.textContent = '오류';
            btn.style.background = '#DC2626';
            btn.disabled = false;
        }
    }
}

async function saveAll() {
    if (!confirm(
        'DB sources 테이블에 등록된 RSS 출처로 수집·저장합니다.\n' +
        '(Google News 파생 소스 「언론사 - 키워드 (GN)」· google_news:// 는 제외)\n' +
        '시간이 걸릴 수 있습니다.'
    )) return;

    const btn = document.getElementById('saveAllBtn');
    const original = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span>저장 중…</span>';
    showLoading('전체 저장 중…', 'DB sources 조회 중 (GN 파생 제외)');

    try {
        const res = await fetch('/api/save-all-stream', { method: 'POST' });
        const final = await readNdjsonStream(res, updateLoadingProgress);
        hideLoading();
        btn.disabled = false;
        btn.innerHTML = original;

        if (!final || !final.success) {
            showError('저장 오류: ' + ((final && final.error) || '알 수 없는 오류'));
            return;
        }
        const data = final.data || {};
        const totalNoContent = data.total_no_content != null
            ? data.total_no_content
            : (data.detail || [])
                .filter(d => d.success)
                .reduce((s, d) => s + (d.db?.no_content || 0), 0);

        setSourcesPanelVisible(false);
        document.getElementById('results').innerHTML = `
            <div class="feed-header">
                <div class="feed-header-top">
                    <div>
                        <span class="feed-kicker">Batch · sources</span>
                        <h3>전체 저장 완료</h3>
                    </div>
                </div>
                <div class="feed-info">
                    <span class="stat-chip success-badge" style="border:none">저장 ${data.total_saved ?? 0}</span>
                    <span class="stat-chip">중복 ${data.total_skipped ?? 0}</span>
                    <span class="stat-chip">본문없음 ${totalNoContent}</span>
                </div>
            </div>
            <div class="results-scroll">
                <div class="save-all-results">
                    ${(data.detail || []).map(d => `
                        <div class="save-result-item ${d.success ? '' : 'error'}">
                            <span class="save-result-name">${escapeHtml(d.name)}</span>
                            <span class="save-result-category">${escapeHtml(d.category)}</span>
                            ${d.success
                                ? `<span class="save-result-stat">${d.db.saved} 저장 · ${d.db.skipped} 중복 · ${d.db.no_content || 0} 본문없음</span>`
                                : `<span class="save-result-stat">${escapeHtml(d.error || '')}</span>`
                            }
                        </div>`).join('')}
                </div>
            </div>
        `;
    } catch (e) {
        hideLoading();
        btn.disabled = false;
        btn.innerHTML = original;
        showError('저장 오류: ' + e.message);
    }
}

async function showDbStats() {
    showLoading('DB 조회 중…', '저장 현황 불러오는 중');
    try {
        const res = await fetch('/api/db-stats');
        const data = await res.json();
        hideLoading();
        if (!data.success) {
            showError('DB 조회 실패: ' + data.error);
            return;
        }

        setSourcesPanelVisible(false);
        document.getElementById('results').innerHTML = `
            <div class="feed-header">
                <div class="feed-header-top">
                    <div>
                        <span class="feed-kicker">Database</span>
                        <h3>저장 현황</h3>
                    </div>
                </div>
                <div class="feed-info">
                    <span class="stat-chip">소스 ${data.sources_count}</span>
                    <span class="stat-chip">기사 ${data.articles_count}</span>
                </div>
            </div>
            <div class="results-scroll">
                <div class="save-all-results">
                    ${data.top_sources.length === 0
                        ? '<div class="placeholder" style="min-height:120px">저장된 데이터가 없습니다</div>'
                        : data.top_sources.map(s => `
                            <div class="save-result-item">
                                <span class="save-result-name">${escapeHtml(s.name)}</span>
                                <span class="save-result-stat">${s.article_count}건</span>
                            </div>`).join('')
                    }
                </div>
            </div>
        `;
    } catch (e) {
        hideLoading();
        showError('DB 조회 오류: ' + e.message);
    }
}
