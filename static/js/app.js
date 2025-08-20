
// ================================
// 全局变量和配置
// ================================
const apiBase = location.origin;
let keywordsData = {};
let currentCookieId = '';
let editCookieId = '';
let authToken = localStorage.getItem('auth_token');
let dashboardData = {
    accounts: [],
    totalKeywords: 0
};

// 账号关键词缓存
let accountKeywordCache = {};
let cacheTimestamp = 0;
const CACHE_DURATION = 30000; // 30秒缓存

// 商品列表搜索和分页相关变量
let allItemsData = []; // 存储所有商品数据
let filteredItemsData = []; // 存储过滤后的商品数据
let currentItemsPage = 1; // 当前页码
let itemsPerPage = 20; // 每页显示数量
let totalItemsPages = 0; // 总页数
let currentSearchKeyword = ''; // 当前搜索关键词

// 订单列表搜索和分页相关变量
let allOrdersData = []; // 存储所有订单数据
let filteredOrdersData = []; // 存储过滤后的订单数据
let currentOrdersPage = 1; // 当前页码
let ordersPerPage = 20; // 每页显示数量
let totalOrdersPages = 0; // 总页数
let currentOrderSearchKeyword = ''; // 当前搜索关键词

// ================================
// 通用功能 - 菜单切换和导航
// ================================
function showSection(sectionName) {
    console.log('切换到页面:', sectionName); // 调试信息

    // 隐藏所有内容区域
    document.querySelectorAll('.content-section').forEach(section => {
    section.classList.remove('active');
    });

    // 移除所有菜单项的active状态
    document.querySelectorAll('.nav-link').forEach(link => {
    link.classList.remove('active');
    });

    // 显示选中的内容区域
    const targetSection = document.getElementById(sectionName + '-section');
    if (targetSection) {
    targetSection.classList.add('active');
    console.log('页面已激活:', sectionName + '-section'); // 调试信息
    } else {
    console.error('找不到页面元素:', sectionName + '-section'); // 调试信息
    }

    // 设置对应菜单项为active（修复event.target问题）
    const menuLinks = document.querySelectorAll('.nav-link');
    menuLinks.forEach(link => {
    if (link.onclick && link.onclick.toString().includes(`showSection('${sectionName}')`)) {
        link.classList.add('active');
    }
    });

    // 根据不同section加载对应数据
    switch(sectionName) {
    case 'dashboard':        // 【仪表盘菜单】
        loadDashboard();
        break;
    case 'accounts':         // 【账号管理菜单】
        loadCookies();
        break;
    case 'items':           // 【商品管理菜单】
        loadItems();
        break;
    case 'items-reply':           // 【商品回复管理菜单】
        loadItemsReplay();
        break;
    case 'orders':          // 【订单管理菜单】
        loadOrders();
        break;
    case 'auto-reply':      // 【自动回复菜单】
        refreshAccountList();
        break;
    case 'cards':           // 【卡券管理菜单】
        loadCards();
        break;
    case 'auto-delivery':   // 【自动发货菜单】
        loadDeliveryRules();
        break;
    case 'notification-channels':  // 【通知渠道菜单】
        loadNotificationChannels();
        break;
    case 'message-notifications':  // 【消息通知菜单】
        loadMessageNotifications();
        break;
    case 'system-settings':    // 【系统设置菜单】
        loadSystemSettings();
        break;
    case 'logs':            // 【日志管理菜单】
        // 自动加载系统日志
        setTimeout(() => {
            // 检查是否在正确的页面并且元素存在
            const systemLogContainer = document.getElementById('systemLogContainer');
            if (systemLogContainer) {
                console.log('首次进入日志页面，自动加载日志...');
                loadSystemLogs();
            }
        }, 100);
        break;
    case 'user-management':  // 【用户管理菜单】
        loadUserManagement();
        break;
    case 'data-management':  // 【数据管理菜单】
        loadDataManagement();
        break;
    }

    // 如果切换到非日志页面，停止自动刷新
    if (sectionName !== 'logs' && window.autoRefreshInterval) {
    clearInterval(window.autoRefreshInterval);
    window.autoRefreshInterval = null;
    const button = document.querySelector('#autoRefreshText');
    const icon = button?.previousElementSibling;
    if (button) {
        button.textContent = '开启自动刷新';
        if (icon) icon.className = 'bi bi-play-circle me-1';
    }
    }
}

// 移动端侧边栏切换
function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('show');
}

// ================================
// 【仪表盘菜单】相关功能
// ================================

// 加载仪表盘数据
async function loadDashboard() {
    try {
    toggleLoading(true);

    // 获取账号列表
    const cookiesResponse = await fetch(`${apiBase}/cookies/details`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (cookiesResponse.ok) {
        const cookiesData = await cookiesResponse.json();

        // 为每个账号获取关键词信息
        const accountsWithKeywords = await Promise.all(
        cookiesData.map(async (account) => {
            try {
            const keywordsResponse = await fetch(`${apiBase}/keywords/${account.id}`, {
                headers: {
                'Authorization': `Bearer ${authToken}`
                }
            });

            if (keywordsResponse.ok) {
                const keywordsData = await keywordsResponse.json();
                return {
                ...account,
                keywords: keywordsData,
                keywordCount: keywordsData.length
                };
            } else {
                return {
                ...account,
                keywords: [],
                keywordCount: 0
                };
            }
            } catch (error) {
            console.error(`获取账号 ${account.id} 关键词失败:`, error);
            return {
                ...account,
                keywords: [],
                keywordCount: 0
            };
            }
        })
        );

        dashboardData.accounts = accountsWithKeywords;

        // 计算统计数据
        let totalKeywords = 0;
        let activeAccounts = 0;
        let enabledAccounts = 0;

        accountsWithKeywords.forEach(account => {
        const keywordCount = account.keywordCount || 0;
        const isEnabled = account.enabled === undefined ? true : account.enabled;

        if (isEnabled) {
            enabledAccounts++;
            totalKeywords += keywordCount;
            if (keywordCount > 0) {
            activeAccounts++;
            }
        }
        });

        dashboardData.totalKeywords = totalKeywords;

        // 加载订单数量
        await loadOrdersCount();

        // 更新仪表盘显示
        updateDashboardStats(accountsWithKeywords.length, totalKeywords, enabledAccounts);
        updateDashboardAccountsList(accountsWithKeywords);
    }
    } catch (error) {
    console.error('加载仪表盘数据失败:', error);
    showToast('加载仪表盘数据失败', 'danger');
    } finally {
    toggleLoading(false);
    }
}

// 加载订单数量
async function loadOrdersCount() {
    try {
        const token = localStorage.getItem('auth_token');
        const response = await fetch('/admin/data/orders', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        const data = await response.json();
        if (data.success) {
            const ordersCount = data.data ? data.data.length : 0;
            document.getElementById('totalOrders').textContent = ordersCount;
        } else {
            console.error('加载订单数量失败:', data.message);
            document.getElementById('totalOrders').textContent = '0';
        }
    } catch (error) {
        console.error('加载订单数量失败:', error);
        document.getElementById('totalOrders').textContent = '0';
    }
}

// 更新仪表盘统计数据
function updateDashboardStats(totalAccounts, totalKeywords, enabledAccounts) {
    document.getElementById('totalAccounts').textContent = totalAccounts;
    document.getElementById('totalKeywords').textContent = totalKeywords;
    document.getElementById('activeAccounts').textContent = enabledAccounts;
}

// 更新仪表盘账号列表
function updateDashboardAccountsList(accounts) {
    const tbody = document.getElementById('dashboardAccountsList');
    tbody.innerHTML = '';

    if (accounts.length === 0) {
    tbody.innerHTML = `
        <tr>
        <td colspan="4" class="text-center text-muted py-4">
            <i class="bi bi-inbox fs-1 d-block mb-2"></i>
            暂无账号数据
        </td>
        </tr>
    `;
    return;
    }

    accounts.forEach(account => {
    const keywordCount = account.keywordCount || 0;
    const isEnabled = account.enabled === undefined ? true : account.enabled;

    let status = '';
    if (!isEnabled) {
        status = '<span class="badge bg-danger">已禁用</span>';
    } else if (keywordCount > 0) {
        status = '<span class="badge bg-success">活跃</span>';
    } else {
        status = '<span class="badge bg-secondary">未配置</span>';
    }

    const row = document.createElement('tr');
    row.className = isEnabled ? '' : 'table-secondary';
    row.innerHTML = `
        <td>
        <strong class="text-primary ${!isEnabled ? 'text-muted' : ''}">${account.id}</strong>
        ${!isEnabled ? '<i class="bi bi-pause-circle-fill text-danger ms-1" title="已禁用"></i>' : ''}
        </td>
        <td>
        <span class="badge ${isEnabled ? 'bg-primary' : 'bg-secondary'}">${keywordCount} 个关键词</span>
        </td>
        <td>${status}</td>
        <td>
        <small class="text-muted">${new Date().toLocaleString()}</small>
        </td>
    `;
    tbody.appendChild(row);
    });
}

// 获取账号关键词数量（带缓存）- 包含普通关键词和商品关键词
async function getAccountKeywordCount(accountId) {
    const now = Date.now();

    // 检查缓存
    if (accountKeywordCache[accountId] && (now - cacheTimestamp) < CACHE_DURATION) {
    return accountKeywordCache[accountId];
    }

    try {
    const response = await fetch(`${apiBase}/keywords/${accountId}`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        const keywordsData = await response.json();
        // 现在API返回的是包含普通关键词和商品关键词的完整列表
        const count = keywordsData.length;

        // 更新缓存
        accountKeywordCache[accountId] = count;
        cacheTimestamp = now;

        return count;
    } else {
        return 0;
    }
    } catch (error) {
    console.error(`获取账号 ${accountId} 关键词失败:`, error);
    return 0;
    }
}

// 清除关键词缓存
function clearKeywordCache() {
    accountKeywordCache = {};
    cacheTimestamp = 0;
}

// ================================
// 【自动回复菜单】相关功能
// ================================

// 刷新账号列表（用于自动回复页面）
async function refreshAccountList() {
    try {
    toggleLoading(true);

    // 获取账号列表
    const response = await fetch(`${apiBase}/cookies/details`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        const accounts = await response.json();
        const select = document.getElementById('accountSelect');
        select.innerHTML = '<option value="">🔍 请选择一个账号开始配置...</option>';

        // 为每个账号获取关键词数量
        const accountsWithKeywords = await Promise.all(
        accounts.map(async (account) => {
            try {
            const keywordsResponse = await fetch(`${apiBase}/keywords/${account.id}`, {
                headers: {
                'Authorization': `Bearer ${authToken}`
                }
            });

            if (keywordsResponse.ok) {
                const keywordsData = await keywordsResponse.json();
                return {
                ...account,
                keywords: keywordsData,
                keywordCount: keywordsData.length
                };
            } else {
                return {
                ...account,
                keywordCount: 0
                };
            }
            } catch (error) {
            console.error(`获取账号 ${account.id} 关键词失败:`, error);
            return {
                ...account,
                keywordCount: 0
            };
            }
        })
        );

        // 渲染账号选项（显示所有账号，但标识禁用状态）
        if (accountsWithKeywords.length === 0) {
        select.innerHTML = '<option value="">❌ 暂无账号，请先添加账号</option>';
        return;
        }

        // 分组显示：先显示启用的账号，再显示禁用的账号
        const enabledAccounts = accountsWithKeywords.filter(account => {
        const enabled = account.enabled === undefined ? true : account.enabled;
        console.log(`账号 ${account.id} 过滤状态: enabled=${account.enabled}, 判断为启用=${enabled}`); // 调试信息
        return enabled;
        });
        const disabledAccounts = accountsWithKeywords.filter(account => {
        const enabled = account.enabled === undefined ? true : account.enabled;
        return !enabled;
        });

        // 渲染启用的账号
        enabledAccounts.forEach(account => {
        const option = document.createElement('option');
        option.value = account.id;

        // 根据关键词数量显示不同的图标和样式
        let icon = '📝';
        let status = '';
        if (account.keywordCount === 0) {
            icon = '⚪';
            status = ' (未配置)';
        } else if (account.keywordCount >= 5) {
            icon = '🟢';
            status = ` (${account.keywordCount} 个关键词)`;
        } else {
            icon = '🟡';
            status = ` (${account.keywordCount} 个关键词)`;
        }

        option.textContent = `${icon} ${account.id}${status}`;
        select.appendChild(option);
        });

        // 如果有禁用的账号，添加分隔线和禁用账号
        if (disabledAccounts.length > 0) {
        // 添加分隔线
        const separatorOption = document.createElement('option');
        separatorOption.disabled = true;
        separatorOption.textContent = `--- 禁用账号 (${disabledAccounts.length} 个) ---`;
        select.appendChild(separatorOption);

        // 渲染禁用的账号
        disabledAccounts.forEach(account => {
            const option = document.createElement('option');
            option.value = account.id;

            // 禁用账号使用特殊图标和样式
            let icon = '🔴';
            let status = '';
            if (account.keywordCount === 0) {
            status = ' (未配置) [已禁用]';
            } else {
            status = ` (${account.keywordCount} 个关键词) [已禁用]`;
            }

            option.textContent = `${icon} ${account.id}${status}`;
            option.style.color = '#6b7280';
            option.style.fontStyle = 'italic';
            select.appendChild(option);
        });
        }

        console.log('账号列表刷新完成，关键词统计:', accountsWithKeywords.map(a => ({id: a.id, keywords: a.keywordCount})));
    } else {
        showToast('获取账号列表失败', 'danger');
    }
    } catch (error) {
    console.error('刷新账号列表失败:', error);
    showToast('刷新账号列表失败', 'danger');
    } finally {
    toggleLoading(false);
    }
}

// 只刷新关键词列表（不重新加载商品列表等其他数据）
async function refreshKeywordsList() {
    if (!currentCookieId) {
        console.warn('没有选中的账号，无法刷新关键词列表');
        return;
    }

    try {
        const response = await fetch(`${apiBase}/keywords-with-item-id/${currentCookieId}`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            const data = await response.json();
            console.log('刷新关键词列表，从服务器获取的数据:', data);

            // 更新缓存数据
            keywordsData[currentCookieId] = data;

            // 只重新渲染关键词列表
            renderKeywordsList(data);

            // 清除关键词缓存
            clearKeywordCache();
        } else {
            console.error('刷新关键词列表失败:', response.status);
            showToast('刷新关键词列表失败', 'danger');
        }
    } catch (error) {
        console.error('刷新关键词列表失败:', error);
        showToast('刷新关键词列表失败', 'danger');
    }
}

// 加载账号关键词
async function loadAccountKeywords() {
    const accountId = document.getElementById('accountSelect').value;
    const keywordManagement = document.getElementById('keywordManagement');

    if (!accountId) {
    keywordManagement.style.display = 'none';
    return;
    }

    try {
    toggleLoading(true);
    currentCookieId = accountId;

    // 获取账号详情以检查状态
    const accountResponse = await fetch(`${apiBase}/cookies/details`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    let accountStatus = true; // 默认启用
    if (accountResponse.ok) {
        const accounts = await accountResponse.json();
        const currentAccount = accounts.find(acc => acc.id === accountId);
        accountStatus = currentAccount ? (currentAccount.enabled === undefined ? true : currentAccount.enabled) : true;
        console.log(`加载关键词时账号 ${accountId} 状态: enabled=${currentAccount?.enabled}, accountStatus=${accountStatus}`); // 调试信息
    }

    const response = await fetch(`${apiBase}/keywords-with-item-id/${accountId}`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        const data = await response.json();
        console.log('从服务器获取的关键词数据:', data); // 调试信息

        // 后端返回的是 [{keyword, reply, item_id, type, image_url}, ...] 格式，直接使用
        const formattedData = data;

        console.log('格式化后的关键词数据:', formattedData); // 调试信息
        keywordsData[accountId] = formattedData;
        renderKeywordsList(formattedData);

        // 加载商品列表
        await loadItemsList(accountId);

        // 更新账号徽章显示
        updateAccountBadge(accountId, accountStatus);

        keywordManagement.style.display = 'block';
    } else {
        showToast('加载关键词失败', 'danger');
    }
    } catch (error) {
    console.error('加载关键词失败:', error);
    showToast('加载关键词失败', 'danger');
    } finally {
    toggleLoading(false);
    }
}

// 更新账号徽章显示
function updateAccountBadge(accountId, isEnabled) {
    const badge = document.getElementById('currentAccountBadge');
    if (!badge) return;

    const statusIcon = isEnabled ? '🟢' : '🔴';
    const statusText = isEnabled ? '启用' : '禁用';
    const statusClass = isEnabled ? 'bg-success' : 'bg-warning';

    badge.innerHTML = `
    <span class="badge ${statusClass} me-2">
        ${statusIcon} ${accountId}
    </span>
    <small class="text-muted">
        状态: ${statusText}
        ${!isEnabled ? ' (配置的关键词不会参与自动回复)' : ''}
    </small>
    `;
}

// 显示添加关键词表单
function showAddKeywordForm() {
    const form = document.getElementById('addKeywordForm');
    form.style.display = form.style.display === 'none' ? 'block' : 'none';

    if (form.style.display === 'block') {
    document.getElementById('newKeyword').focus();
    }
}

// 加载商品列表
async function loadItemsList(accountId) {
    try {
    const response = await fetch(`${apiBase}/items/${accountId}`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        const data = await response.json();
        const items = data.items || [];

        // 更新商品选择下拉框
        const selectElement = document.getElementById('newItemIdSelect');
        if (selectElement) {
        // 清空现有选项（保留第一个默认选项）
        selectElement.innerHTML = '<option value="">选择商品或留空表示通用关键词</option>';

        // 添加商品选项
        items.forEach(item => {
            const option = document.createElement('option');
            option.value = item.item_id;
            option.textContent = `${item.item_id} - ${item.item_title}`;
            selectElement.appendChild(option);
        });
        }

        console.log(`加载了 ${items.length} 个商品到选择列表`);
    } else {
        console.warn('加载商品列表失败:', response.status);
    }
    } catch (error) {
    console.error('加载商品列表时发生错误:', error);
    }
}



// 添加或更新关键词
async function addKeyword() {
    const keyword = document.getElementById('newKeyword').value.trim();
    const reply = document.getElementById('newReply').value.trim();
    const itemId = document.getElementById('newItemIdSelect').value.trim();

    if (!keyword) {
    showToast('请填写关键词', 'warning');
    return;
    }

    if (!currentCookieId) {
    showToast('请先选择账号', 'warning');
    return;
    }

    // 检查是否为编辑模式
    const isEditMode = typeof window.editingIndex !== 'undefined';
    const actionText = isEditMode ? '更新' : '添加';

    try {
    toggleLoading(true);

    // 获取当前关键词列表
    let currentKeywords = [...(keywordsData[currentCookieId] || [])];

    // 如果是编辑模式，先移除原关键词
    if (isEditMode) {
        currentKeywords.splice(window.editingIndex, 1);
    }

    // 准备要保存的关键词列表（只包含文本类型的关键字）
    let textKeywords = currentKeywords.filter(item => (item.type || 'text') === 'text');

    // 如果是编辑模式，先移除原关键词
    if (isEditMode && typeof window.editingIndex !== 'undefined') {
        // 需要重新计算在文本关键字中的索引
        const originalKeyword = keywordsData[currentCookieId][window.editingIndex];
        const textIndex = textKeywords.findIndex(item =>
            item.keyword === originalKeyword.keyword &&
            (item.item_id || '') === (originalKeyword.item_id || '')
        );
        if (textIndex !== -1) {
            textKeywords.splice(textIndex, 1);
        }
    }

    // 检查关键词是否已存在（考虑商品ID，检查所有类型的关键词）
    const allKeywords = keywordsData[currentCookieId] || [];
    const existingKeyword = allKeywords.find(item =>
        item.keyword === keyword &&
        (item.item_id || '') === (itemId || '')
    );
    if (existingKeyword) {
        const itemIdText = itemId ? `（商品ID: ${itemId}）` : '（通用关键词）';
        const typeText = existingKeyword.type === 'image' ? '图片' : '文本';
        showToast(`关键词 "${keyword}" ${itemIdText} 已存在（${typeText}关键词），请使用其他关键词或商品ID`, 'warning');
        toggleLoading(false);
        return;
    }

    // 添加新关键词或更新的关键词
    const newKeyword = {
        keyword: keyword,
        reply: reply,
        item_id: itemId || ''
    };
    textKeywords.push(newKeyword);

    const response = await fetch(`${apiBase}/keywords-with-item-id/${currentCookieId}`, {
        method: 'POST',
        headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
        },
        body: JSON.stringify({
        keywords: textKeywords
        })
    });

    if (response.ok) {
        showToast(`✨ 关键词 "${keyword}" ${actionText}成功！`, 'success');

        // 清空输入框并重置样式
        const keywordInput = document.getElementById('newKeyword');
        const replyInput = document.getElementById('newReply');
        const selectElement = document.getElementById('newItemIdSelect');
        const addBtn = document.querySelector('.add-btn');

        keywordInput.value = '';
        replyInput.value = '';
        if (selectElement) {
        selectElement.value = '';
        }
        keywordInput.style.borderColor = '#e5e7eb';
        replyInput.style.borderColor = '#e5e7eb';
        addBtn.style.opacity = '0.7';
        addBtn.style.transform = 'scale(0.95)';

        // 如果是编辑模式，重置编辑状态
        if (isEditMode) {
        delete window.editingIndex;
        delete window.originalKeyword;

        // 恢复添加按钮
        addBtn.innerHTML = '<i class="bi bi-plus-lg"></i>添加';
        addBtn.style.background = 'linear-gradient(135deg, #10b981 0%, #059669 100%)';

        // 移除取消按钮
        const cancelBtn = document.getElementById('cancelEditBtn');
        if (cancelBtn) {
            cancelBtn.remove();
        }
        }

        // 聚焦到关键词输入框，方便连续添加
        setTimeout(() => {
        keywordInput.focus();
        }, 100);

        // 只刷新关键词列表，不重新加载整个界面
        await refreshKeywordsList();
    } else {
        try {
            const errorData = await response.json();
            const errorMessage = errorData.detail || '关键词添加失败';
            console.error('关键词添加失败:', errorMessage);

            // 检查是否是重复关键词的错误
            if (errorMessage.includes('关键词已存在') || errorMessage.includes('关键词重复') || errorMessage.includes('UNIQUE constraint')) {
                showToast(`❌ 关键词重复：${errorMessage}`, 'warning');
            } else {
                showToast(`❌ ${errorMessage}`, 'danger');
            }
        } catch (parseError) {
            // 如果无法解析JSON，使用原始文本
            const errorText = await response.text();
            console.error('关键词添加失败:', errorText);
            showToast('❌ 关键词添加失败', 'danger');
        }
    }
    } catch (error) {
    console.error('添加关键词失败:', error);
    showToast('添加关键词失败', 'danger');
    } finally {
    toggleLoading(false);
    }
}

// 渲染现代化关键词列表
function renderKeywordsList(keywords) {
    console.log('渲染关键词列表:', keywords); // 调试信息
    const container = document.getElementById('keywordsList');

    if (!container) {
    console.error('找不到关键词列表容器元素');
    return;
    }

    container.innerHTML = '';

    if (!keywords || keywords.length === 0) {
    console.log('关键词列表为空，显示空状态');
    container.innerHTML = `
        <div class="empty-state">
        <i class="bi bi-chat-dots"></i>
        <h3>还没有关键词</h3>
        <p>添加第一个关键词，让您的闲鱼店铺自动回复客户消息</p>
        <button class="quick-add-btn" onclick="focusKeywordInput()">
            <i class="bi bi-plus-lg me-2"></i>立即添加
        </button>
        </div>
    `;
    return;
    }

    console.log(`开始渲染 ${keywords.length} 个关键词`);

    keywords.forEach((item, index) => {
    console.log(`渲染关键词 ${index + 1}:`, item); // 调试信息

    const keywordItem = document.createElement('div');
    keywordItem.className = 'keyword-item';

    // 判断关键词类型
    const keywordType = item.type || 'text'; // 默认为文本类型
    const isImageType = keywordType === 'image';

    // 类型标识
    const typeBadge = isImageType ?
        '<span class="keyword-type-badge keyword-type-image"><i class="bi bi-image"></i> 图片</span>' :
        '<span class="keyword-type-badge keyword-type-text"><i class="bi bi-chat-text"></i> 文本</span>';

    // 商品ID显示
    const itemIdDisplay = item.item_id ?
        `<small class="text-muted d-block"><i class="bi bi-box"></i> 商品ID: ${item.item_id}</small>` :
        '<small class="text-muted d-block"><i class="bi bi-globe"></i> 通用关键词</small>';

    // 内容显示
    let contentDisplay = '';
    if (isImageType) {
        // 图片类型显示图片预览
        const imageUrl = item.reply || item.image_url || '';
        contentDisplay = imageUrl ?
            `<div class="d-flex align-items-center gap-3">
                <img src="${imageUrl}" alt="关键词图片" class="keyword-image-preview" onclick="showImageModal('${imageUrl}')">
                <div class="flex-grow-1">
                    <p class="reply-text mb-0">用户发送关键词时将回复此图片</p>
                    <small class="text-muted">点击图片查看大图</small>
                </div>
            </div>` :
            '<p class="reply-text text-muted">图片加载失败</p>';
    } else {
        // 文本类型显示文本内容
        contentDisplay = `<p class="reply-text">${item.reply || ''}</p>`;
    }

    keywordItem.innerHTML = `
        <div class="keyword-item-header">
        <div class="keyword-tag">
            <i class="bi bi-tag-fill"></i>
            ${item.keyword}
            ${typeBadge}
            ${itemIdDisplay}
        </div>
        <div class="keyword-actions">
            <button class="action-btn edit-btn ${isImageType ? 'edit-btn-disabled' : ''}" onclick="${isImageType ? 'editImageKeyword' : 'editKeyword'}(${index})" title="${isImageType ? '图片关键词不支持编辑' : '编辑'}">
            <i class="bi bi-pencil"></i>
            </button>
            <button class="action-btn delete-btn" onclick="deleteKeyword('${currentCookieId}', ${index})" title="删除">
            <i class="bi bi-trash"></i>
            </button>
        </div>
        </div>
        <div class="keyword-content">
        ${contentDisplay}
        </div>
    `;
    container.appendChild(keywordItem);
    });

    console.log('关键词列表渲染完成');
}

// 聚焦到关键词输入框
function focusKeywordInput() {
    document.getElementById('newKeyword').focus();
}

// 编辑关键词 - 改进版本
function editKeyword(index) {
    const keywords = keywordsData[currentCookieId] || [];
    const keyword = keywords[index];

    if (!keyword) {
    showToast('关键词不存在', 'warning');
    return;
    }

    // 将关键词信息填入输入框
    document.getElementById('newKeyword').value = keyword.keyword;
    document.getElementById('newReply').value = keyword.reply;

    // 设置商品ID选择框
    const selectElement = document.getElementById('newItemIdSelect');
    if (selectElement) {
    selectElement.value = keyword.item_id || '';
    }

    // 设置编辑模式标识
    window.editingIndex = index;
    window.originalKeyword = keyword.keyword;
    window.originalItemId = keyword.item_id || '';

    // 更新按钮文本和样式
    const addBtn = document.querySelector('.add-btn');
    addBtn.innerHTML = '<i class="bi bi-check-lg"></i>更新';
    addBtn.style.background = 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)';

    // 显示取消按钮
    showCancelEditButton();

    // 聚焦到关键词输入框并选中文本
    setTimeout(() => {
    const keywordInput = document.getElementById('newKeyword');
    keywordInput.focus();
    keywordInput.select();
    }, 100);

    showToast('📝 编辑模式：修改后点击"更新"按钮保存', 'info');
}

// 显示取消编辑按钮
function showCancelEditButton() {
    // 检查是否已存在取消按钮
    if (document.getElementById('cancelEditBtn')) {
    return;
    }

    const addBtn = document.querySelector('.add-btn');
    const cancelBtn = document.createElement('button');
    cancelBtn.id = 'cancelEditBtn';
    cancelBtn.className = 'btn btn-outline-secondary';
    cancelBtn.style.marginLeft = '0.5rem';
    cancelBtn.innerHTML = '<i class="bi bi-x-lg"></i>取消';
    cancelBtn.onclick = cancelEdit;

    addBtn.parentNode.appendChild(cancelBtn);
}

// 取消编辑
function cancelEdit() {
    // 清空输入框
    document.getElementById('newKeyword').value = '';
    document.getElementById('newReply').value = '';

    // 清空商品ID选择框
    const selectElement = document.getElementById('newItemIdSelect');
    if (selectElement) {
    selectElement.value = '';
    }

    // 重置编辑状态
    delete window.editingIndex;
    delete window.originalKeyword;
    delete window.originalItemId;

    // 恢复添加按钮
    const addBtn = document.querySelector('.add-btn');
    addBtn.innerHTML = '<i class="bi bi-plus-lg"></i>添加';
    addBtn.style.background = 'linear-gradient(135deg, #10b981 0%, #059669 100%)';

    // 移除取消按钮
    const cancelBtn = document.getElementById('cancelEditBtn');
    if (cancelBtn) {
    cancelBtn.remove();
    }

    showToast('已取消编辑', 'info');
}

// 删除关键词
async function deleteKeyword(cookieId, index) {
    if (!confirm('确定要删除这个关键词吗？')) {
    return;
    }

    try {
    toggleLoading(true);

    // 使用新的删除API
    const response = await fetch(`${apiBase}/keywords/${cookieId}/${index}`, {
        method: 'DELETE',
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        showToast('关键词删除成功', 'success');
        // 只刷新关键词列表，不重新加载整个界面
        await refreshKeywordsList();
    } else {
        const errorText = await response.text();
        console.error('关键词删除失败:', errorText);
        showToast('关键词删除失败', 'danger');
    }
    } catch (error) {
    console.error('删除关键词失败:', error);
    showToast('删除关键词删除失败', 'danger');
    } finally {
    toggleLoading(false);
    }
}

// 显示/隐藏加载动画
function toggleLoading(show) {
    document.getElementById('loading').classList.toggle('d-none', !show);
}

// ================================
// 通用工具函数
// ================================

// 显示提示消息
function showToast(message, type = 'success') {
    const toastContainer = document.querySelector('.toast-container');
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-${type} border-0`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');

    toast.innerHTML = `
    <div class="d-flex">
        <div class="toast-body">
        ${message}
        </div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
    </div>
    `;

    toastContainer.appendChild(toast);
    const bsToast = new bootstrap.Toast(toast, { delay: 3000 });
    bsToast.show();

    // 自动移除
    toast.addEventListener('hidden.bs.toast', () => {
    toast.remove();
    });
}

// 错误处理
async function handleApiError(err) {
    console.error(err);
    showToast(err.message || '操作失败', 'danger');
    toggleLoading(false);
}

// API请求包装
async function fetchJSON(url, opts = {}) {
    toggleLoading(true);
    try {
    // 添加认证头
    if (authToken) {
        opts.headers = opts.headers || {};
        opts.headers['Authorization'] = `Bearer ${authToken}`;
    }

    const res = await fetch(url, opts);
    if (res.status === 401) {
        // 未授权，跳转到登录页面
        localStorage.removeItem('auth_token');
        window.location.href = '/';
        return;
    }
    if (!res.ok) {
        let errorMessage = `HTTP ${res.status}`;
        try {
        const errorText = await res.text();
        if (errorText) {
            // 尝试解析JSON错误信息
            try {
            const errorJson = JSON.parse(errorText);
            errorMessage = errorJson.detail || errorJson.message || errorText;
            } catch {
            errorMessage = errorText;
            }
        }
        } catch {
        errorMessage = `HTTP ${res.status} ${res.statusText}`;
        }
        throw new Error(errorMessage);
    }
    const data = await res.json();
    toggleLoading(false);
    return data;
    } catch (err) {
    handleApiError(err);
    throw err;
    }
}

// ================================
// 【账号管理菜单】相关功能
// ================================

// 加载Cookie列表
async function loadCookies() {
    try {
    toggleLoading(true);
    const tbody = document.querySelector('#cookieTable tbody');
    tbody.innerHTML = '';

    const cookieDetails = await fetchJSON(apiBase + '/cookies/details');

    if (cookieDetails.length === 0) {
        tbody.innerHTML = `
        <tr>
            <td colspan="10" class="text-center py-4 text-muted empty-state">
            <i class="bi bi-inbox fs-1 d-block mb-3"></i>
            <h5>暂无账号</h5>
            <p class="mb-0">请添加新的闲鱼账号开始使用</p>
            </td>
        </tr>
        `;
        return;
    }

    // 为每个账号获取关键词数量和默认回复设置并渲染
    const accountsWithKeywords = await Promise.all(
        cookieDetails.map(async (cookie) => {
        try {
            // 获取关键词数量
            const keywordsResponse = await fetch(`${apiBase}/keywords/${cookie.id}`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
            });

            let keywordCount = 0;
            if (keywordsResponse.ok) {
            const keywordsData = await keywordsResponse.json();
            keywordCount = keywordsData.length;
            }

            // 获取默认回复设置
            const defaultReplyResponse = await fetch(`${apiBase}/default-replies/${cookie.id}`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
            });

            let defaultReply = { enabled: false, reply_content: '' };
            if (defaultReplyResponse.ok) {
            defaultReply = await defaultReplyResponse.json();
            }

            // 获取AI回复设置
            const aiReplyResponse = await fetch(`${apiBase}/ai-reply-settings/${cookie.id}`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
            });

            let aiReply = { ai_enabled: false, model_name: 'qwen-plus' };
            if (aiReplyResponse.ok) {
            aiReply = await aiReplyResponse.json();
            }

            return {
            ...cookie,
            keywordCount: keywordCount,
            defaultReply: defaultReply,
            aiReply: aiReply
            };
        } catch (error) {
            return {
            ...cookie,
            keywordCount: 0,
            defaultReply: { enabled: false, reply_content: '' },
            aiReply: { ai_enabled: false, model_name: 'qwen-plus' }
            };
        }
        })
    );

    accountsWithKeywords.forEach(cookie => {
        // 使用数据库中的实际状态，默认为启用
        const isEnabled = cookie.enabled === undefined ? true : cookie.enabled;

        console.log(`账号 ${cookie.id} 状态: enabled=${cookie.enabled}, isEnabled=${isEnabled}`); // 调试信息

        const tr = document.createElement('tr');
        tr.className = `account-row ${isEnabled ? 'enabled' : 'disabled'}`;
        // 默认回复状态标签
        const defaultReplyBadge = cookie.defaultReply.enabled ?
        '<span class="badge bg-success">启用</span>' :
        '<span class="badge bg-secondary">禁用</span>';

        // AI回复状态标签
        const aiReplyBadge = cookie.aiReply.ai_enabled ?
        '<span class="badge bg-primary">AI启用</span>' :
        '<span class="badge bg-secondary">AI禁用</span>';

        // 自动确认发货状态（默认开启）
        const autoConfirm = cookie.auto_confirm === undefined ? true : cookie.auto_confirm;

        tr.innerHTML = `
        <td class="align-middle">
            <div class="cookie-id">
            <strong class="text-primary">${cookie.id}</strong>
            </div>
        </td>
        <td class="align-middle">
            <div class="cookie-value" title="点击复制Cookie" style="font-family: monospace; font-size: 0.875rem; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
            ${cookie.value || '未设置'}
            </div>
        </td>
        <td class="align-middle">
            <span class="badge ${cookie.keywordCount > 0 ? 'bg-success' : 'bg-secondary'}">
            ${cookie.keywordCount} 个关键词
            </span>
        </td>
        <td class="align-middle">
            <div class="d-flex align-items-center gap-2">
            <label class="status-toggle" title="${isEnabled ? '点击禁用' : '点击启用'}">
                <input type="checkbox" ${isEnabled ? 'checked' : ''} onchange="toggleAccountStatus('${cookie.id}', this.checked)">
                <span class="status-slider"></span>
            </label>
            <span class="status-badge ${isEnabled ? 'enabled' : 'disabled'}" title="${isEnabled ? '账号已启用' : '账号已禁用'}">
                <i class="bi bi-${isEnabled ? 'check-circle-fill' : 'x-circle-fill'}"></i>
            </span>
            </div>
        </td>
        <td class="align-middle">
            ${defaultReplyBadge}
        </td>
        <td class="align-middle">
            ${aiReplyBadge}
        </td>
        <td class="align-middle">
            <div class="d-flex align-items-center gap-2">
            <label class="status-toggle" title="${autoConfirm ? '点击关闭自动确认发货' : '点击开启自动确认发货'}">
                <input type="checkbox" ${autoConfirm ? 'checked' : ''} onchange="toggleAutoConfirm('${cookie.id}', this.checked)">
                <span class="status-slider"></span>
            </label>
            <span class="status-badge ${autoConfirm ? 'enabled' : 'disabled'}" title="${autoConfirm ? '自动确认发货已开启' : '自动确认发货已关闭'}">
                <i class="bi bi-${autoConfirm ? 'truck' : 'truck-flatbed'}"></i>
            </span>
            </div>
        </td>
        <td class="align-middle">
            <div class="remark-cell" data-cookie-id="${cookie.id}">
                <span class="remark-display" onclick="editRemark('${cookie.id}', '${(cookie.remark || '').replace(/'/g, '&#39;')}')" title="点击编辑备注" style="cursor: pointer; color: #6c757d; font-size: 0.875rem;">
                    ${cookie.remark || '<i class="bi bi-plus-circle text-muted"></i> 添加备注'}
                </span>
            </div>
        </td>
        <td class="align-middle">
            <div class="pause-duration-cell" data-cookie-id="${cookie.id}">
                <span class="pause-duration-display" onclick="editPauseDuration('${cookie.id}', ${cookie.pause_duration || 10})" title="点击编辑暂停时间" style="cursor: pointer; color: #6c757d; font-size: 0.875rem;">
                    <i class="bi bi-clock me-1"></i>${cookie.pause_duration || 10}分钟
                </span>
            </div>
        </td>
        <td class="align-middle">
            <div class="btn-group" role="group">
            <button class="btn btn-sm btn-outline-primary" onclick="editCookieInline('${cookie.id}', '${cookie.value}')" title="修改Cookie" ${!isEnabled ? 'disabled' : ''}>
                <i class="bi bi-pencil"></i>
            </button>
            <button class="btn btn-sm btn-outline-success" onclick="goToAutoReply('${cookie.id}')" title="${isEnabled ? '设置自动回复' : '配置关键词 (账号已禁用)'}">
                <i class="bi bi-arrow-right-circle"></i>
            </button>
            <button class="btn btn-sm btn-outline-warning" onclick="configAIReply('${cookie.id}')" title="配置AI回复" ${!isEnabled ? 'disabled' : ''}>
                <i class="bi bi-robot"></i>
            </button>
            <button class="btn btn-sm btn-outline-info" onclick="copyCookie('${cookie.id}', '${cookie.value}')" title="复制Cookie">
                <i class="bi bi-clipboard"></i>
            </button>
            <button class="btn btn-sm btn-outline-danger" onclick="delCookie('${cookie.id}')" title="删除账号">
                <i class="bi bi-trash"></i>
            </button>
            </div>
        </td>
        `;
        tbody.appendChild(tr);
    });

    // 为Cookie值添加点击复制功能
    document.querySelectorAll('.cookie-value').forEach(element => {
        element.style.cursor = 'pointer';
        element.addEventListener('click', function() {
        const cookieValue = this.textContent;
        if (cookieValue && cookieValue !== '未设置') {
            navigator.clipboard.writeText(cookieValue).then(() => {
            showToast('Cookie已复制到剪贴板', 'success');
            }).catch(() => {
            showToast('复制失败，请手动复制', 'error');
            });
        }
        });
    });

    // 重新初始化工具提示
    initTooltips();

    } catch (err) {
    // 错误已在fetchJSON中处理
    } finally {
    toggleLoading(false);
    }
}

// 复制Cookie
function copyCookie(id, value) {
    if (!value || value === '未设置') {
    showToast('该账号暂无Cookie值', 'warning');
    return;
    }

    navigator.clipboard.writeText(value).then(() => {
    showToast(`账号 "${id}" 的Cookie已复制到剪贴板`, 'success');
    }).catch(() => {
    // 降级方案：创建临时文本框
    const textArea = document.createElement('textarea');
    textArea.value = value;
    document.body.appendChild(textArea);
    textArea.select();
    try {
        document.execCommand('copy');
        showToast(`账号 "${id}" 的Cookie已复制到剪贴板`, 'success');
    } catch (err) {
        showToast('复制失败，请手动复制', 'error');
    }
    document.body.removeChild(textArea);
    });
}

// 删除Cookie
async function delCookie(id) {
    if (!confirm(`确定要删除账号 "${id}" 吗？此操作不可恢复。`)) return;

    try {
    await fetchJSON(apiBase + `/cookies/${id}`, { method: 'DELETE' });
    showToast(`账号 "${id}" 已删除`, 'success');
    loadCookies();
    } catch (err) {
    // 错误已在fetchJSON中处理
    }
}

// 内联编辑Cookie
function editCookieInline(id, currentValue) {
    const row = event.target.closest('tr');
    const cookieValueCell = row.querySelector('.cookie-value');
    const originalContent = cookieValueCell.innerHTML;

    // 存储原始数据到全局变量，避免HTML注入问题
    window.editingCookieData = {
    id: id,
    originalContent: originalContent,
    originalValue: currentValue || ''
    };

    // 创建编辑界面容器
    const editContainer = document.createElement('div');
    editContainer.className = 'd-flex gap-2';

    // 创建输入框
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'form-control form-control-sm';
    input.id = `edit-${id}`;
    input.value = currentValue || '';
    input.placeholder = '输入新的Cookie值';

    // 创建保存按钮
    const saveBtn = document.createElement('button');
    saveBtn.className = 'btn btn-sm btn-success';
    saveBtn.title = '保存';
    saveBtn.innerHTML = '<i class="bi bi-check"></i>';
    saveBtn.onclick = () => saveCookieInline(id);

    // 创建取消按钮
    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'btn btn-sm btn-secondary';
    cancelBtn.title = '取消';
    cancelBtn.innerHTML = '<i class="bi bi-x"></i>';
    cancelBtn.onclick = () => cancelCookieEdit(id);

    // 组装编辑界面
    editContainer.appendChild(input);
    editContainer.appendChild(saveBtn);
    editContainer.appendChild(cancelBtn);

    // 替换原内容
    cookieValueCell.innerHTML = '';
    cookieValueCell.appendChild(editContainer);

    // 聚焦输入框
    input.focus();
    input.select();

    // 添加键盘事件监听
    input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        saveCookieInline(id);
    } else if (e.key === 'Escape') {
        e.preventDefault();
        cancelCookieEdit(id);
    }
    });

    // 禁用该行的其他按钮
    const actionButtons = row.querySelectorAll('.btn-group button');
    actionButtons.forEach(btn => btn.disabled = true);
}

// 保存内联编辑的Cookie
async function saveCookieInline(id) {
    const input = document.getElementById(`edit-${id}`);
    const newValue = input.value.trim();

    if (!newValue) {
    showToast('Cookie值不能为空', 'warning');
    return;
    }

    try {
    toggleLoading(true);

    await fetchJSON(apiBase + `/cookies/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
        id: id,
        value: newValue
        })
    });

    showToast(`账号 "${id}" Cookie已更新`, 'success');
    loadCookies(); // 重新加载列表

    } catch (err) {
    console.error('Cookie更新失败:', err);
    showToast(`Cookie更新失败: ${err.message || '未知错误'}`, 'danger');
    // 恢复原内容
    cancelCookieEdit(id);
    } finally {
    toggleLoading(false);
    }
}

// 取消Cookie编辑
function cancelCookieEdit(id) {
    if (!window.editingCookieData || window.editingCookieData.id !== id) {
    console.error('编辑数据不存在');
    return;
    }

    const row = document.querySelector(`#edit-${id}`).closest('tr');
    const cookieValueCell = row.querySelector('.cookie-value');

    // 恢复原内容
    cookieValueCell.innerHTML = window.editingCookieData.originalContent;

    // 恢复按钮状态
    const actionButtons = row.querySelectorAll('.btn-group button');
    actionButtons.forEach(btn => btn.disabled = false);

    // 清理全局数据
    delete window.editingCookieData;
}



// 切换账号启用/禁用状态
async function toggleAccountStatus(accountId, enabled) {
    try {
    toggleLoading(true);

    // 这里需要调用后端API来更新账号状态
    // 由于当前后端可能没有enabled字段，我们先在前端模拟
    // 实际项目中需要后端支持

    const response = await fetch(`${apiBase}/cookies/${accountId}/status`, {
        method: 'PUT',
        headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
        },
        body: JSON.stringify({ enabled: enabled })
    });

    if (response.ok) {
        showToast(`账号 "${accountId}" 已${enabled ? '启用' : '禁用'}`, 'success');

        // 清除相关缓存，确保数据一致性
        clearKeywordCache();

        // 更新界面显示
        updateAccountRowStatus(accountId, enabled);

        // 刷新自动回复页面的账号列表
        refreshAccountList();

        // 如果禁用的账号在自动回复页面被选中，更新显示
        const accountSelect = document.getElementById('accountSelect');
        if (accountSelect && accountSelect.value === accountId) {
        if (!enabled) {
            // 更新徽章显示禁用状态
            updateAccountBadge(accountId, false);
            showToast('账号已禁用，配置的关键词不会参与自动回复', 'warning');
        } else {
            // 更新徽章显示启用状态
            updateAccountBadge(accountId, true);
            showToast('账号已启用，配置的关键词将参与自动回复', 'success');
        }
        }

    } else {
        // 如果后端不支持，先在前端模拟
        console.warn('后端暂不支持账号状态切换，使用前端模拟');
        showToast(`账号 "${accountId}" 已${enabled ? '启用' : '禁用'} (前端模拟)`, enabled ? 'success' : 'warning');
        updateAccountRowStatus(accountId, enabled);
    }

    } catch (error) {
    console.error('切换账号状态失败:', error);

    // 后端不支持时的降级处理
    showToast(`账号 "${accountId}" 已${enabled ? '启用' : '禁用'} (本地模拟)`, enabled ? 'success' : 'warning');
    updateAccountRowStatus(accountId, enabled);

    // 恢复切换按钮状态
    const toggle = document.querySelector(`input[onchange*="${accountId}"]`);
    if (toggle) {
        toggle.checked = enabled;
    }
    } finally {
    toggleLoading(false);
    }
}

// 更新账号行的状态显示
function updateAccountRowStatus(accountId, enabled) {
    const toggle = document.querySelector(`input[onchange*="${accountId}"]`);
    if (!toggle) return;

    const row = toggle.closest('tr');
    const statusBadge = row.querySelector('.status-badge');
    const actionButtons = row.querySelectorAll('.btn-group .btn:not(.btn-outline-info):not(.btn-outline-danger)');

    // 更新行样式
    row.className = `account-row ${enabled ? 'enabled' : 'disabled'}`;

    // 更新状态徽章
    statusBadge.className = `status-badge ${enabled ? 'enabled' : 'disabled'}`;
    statusBadge.title = enabled ? '账号已启用' : '账号已禁用';
    statusBadge.innerHTML = `
    <i class="bi bi-${enabled ? 'check-circle-fill' : 'x-circle-fill'}"></i>
    `;

    // 更新按钮状态（只禁用编辑Cookie按钮，其他按钮保持可用）
    actionButtons.forEach(btn => {
    if (btn.onclick && btn.onclick.toString().includes('editCookieInline')) {
        btn.disabled = !enabled;
    }
    // 设置自动回复按钮始终可用，但更新提示文本
    if (btn.onclick && btn.onclick.toString().includes('goToAutoReply')) {
        btn.title = enabled ? '设置自动回复' : '配置关键词 (账号已禁用)';
    }
    });

    // 更新切换按钮的提示
    const label = toggle.closest('.status-toggle');
    label.title = enabled ? '点击禁用' : '点击启用';
}

// 切换自动确认发货状态
async function toggleAutoConfirm(accountId, enabled) {
    try {
    toggleLoading(true);

    const response = await fetch(`${apiBase}/cookies/${accountId}/auto-confirm`, {
        method: 'PUT',
        headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
        },
        body: JSON.stringify({ auto_confirm: enabled })
    });

    if (response.ok) {
        const result = await response.json();
        showToast(result.message, 'success');

        // 更新界面显示
        updateAutoConfirmRowStatus(accountId, enabled);
    } else {
        const error = await response.json();
        showToast(error.detail || '更新自动确认发货设置失败', 'error');

        // 恢复切换按钮状态
        const toggle = document.querySelector(`input[onchange*="toggleAutoConfirm('${accountId}'"]`);
        if (toggle) {
        toggle.checked = !enabled;
        }
    }

    } catch (error) {
    console.error('切换自动确认发货状态失败:', error);
    showToast('网络错误，请稍后重试', 'error');

    // 恢复切换按钮状态
    const toggle = document.querySelector(`input[onchange*="toggleAutoConfirm('${accountId}'"]`);
    if (toggle) {
        toggle.checked = !enabled;
    }
    } finally {
    toggleLoading(false);
    }
}

// 更新自动确认发货行状态
function updateAutoConfirmRowStatus(accountId, enabled) {
    const row = document.querySelector(`tr:has(input[onchange*="toggleAutoConfirm('${accountId}'"])`);
    if (!row) return;

    const statusBadge = row.querySelector('.status-badge:has(i.bi-truck, i.bi-truck-flatbed)');
    const toggle = row.querySelector(`input[onchange*="toggleAutoConfirm('${accountId}'"]`);

    if (statusBadge && toggle) {
    // 更新状态徽章
    statusBadge.className = `status-badge ${enabled ? 'enabled' : 'disabled'}`;
    statusBadge.title = enabled ? '自动确认发货已开启' : '自动确认发货已关闭';
    statusBadge.innerHTML = `
        <i class="bi bi-${enabled ? 'truck' : 'truck-flatbed'}"></i>
    `;

    // 更新切换按钮的提示
    const label = toggle.closest('.status-toggle');
    label.title = enabled ? '点击关闭自动确认发货' : '点击开启自动确认发货';
    }
}

// 跳转到自动回复页面并选择指定账号
function goToAutoReply(accountId) {
    // 切换到自动回复页面
    showSection('auto-reply');

    // 设置账号选择器的值
    setTimeout(() => {
    const accountSelect = document.getElementById('accountSelect');
    if (accountSelect) {
        accountSelect.value = accountId;
        // 触发change事件来加载关键词
        loadAccountKeywords();
    }
    }, 100);

    showToast(`已切换到自动回复页面，账号 "${accountId}" 已选中`, 'info');
}





// 登出功能
async function logout() {
    try {
    if (authToken) {
        await fetch('/logout', {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${authToken}`
        }
        });
    }
    localStorage.removeItem('auth_token');
    window.location.href = '/';
    } catch (err) {
    console.error('登出失败:', err);
    localStorage.removeItem('auth_token');
    window.location.href = '/';
    }
}

// 检查认证状态
async function checkAuth() {
    if (!authToken) {
    window.location.href = '/';
    return false;
    }

    try {
    const response = await fetch('/verify', {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });
    const result = await response.json();

    if (!result.authenticated) {
        localStorage.removeItem('auth_token');
        window.location.href = '/';
        return false;
    }

    // 检查是否为管理员，显示管理员菜单和功能
    if (result.is_admin === true) {
        const adminMenuSection = document.getElementById('adminMenuSection');
        if (adminMenuSection) {
        adminMenuSection.style.display = 'block';
        }

        // 显示备份管理功能
        const backupManagement = document.getElementById('backup-management');
        if (backupManagement) {
        backupManagement.style.display = 'block';
        }

        // 显示注册设置功能
        const registrationSettings = document.getElementById('registration-settings');
        if (registrationSettings) {
        registrationSettings.style.display = 'block';
        }
    }

    return true;
    } catch (err) {
    localStorage.removeItem('auth_token');
    window.location.href = '/';
    return false;
    }
}

// 初始化事件监听
document.addEventListener('DOMContentLoaded', async () => {
    // 首先检查认证状态
    const isAuthenticated = await checkAuth();
    if (!isAuthenticated) return;
    // 添加Cookie表单提交
    document.getElementById('addForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('cookieId').value.trim();
    const value = document.getElementById('cookieValue').value.trim();

    if (!id || !value) return;

    try {
        await fetchJSON(apiBase + '/cookies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, value })
        });

        document.getElementById('cookieId').value = '';
        document.getElementById('cookieValue').value = '';
        showToast(`账号 "${id}" 添加成功`);
        loadCookies();
    } catch (err) {
        // 错误已在fetchJSON中处理
    }
    });

    // 增强的键盘快捷键和用户体验
    document.getElementById('newKeyword')?.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        document.getElementById('newReply').focus();
    }
    });

    document.getElementById('newReply')?.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        addKeyword();
    }
    });

    // ESC键取消编辑
    document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && typeof window.editingIndex !== 'undefined') {
        e.preventDefault();
        cancelEdit();
    }
    });

    // 输入框实时验证和提示
    document.getElementById('newKeyword')?.addEventListener('input', function(e) {
    const value = e.target.value.trim();
    const addBtn = document.querySelector('.add-btn');
    const replyInput = document.getElementById('newReply');

    if (value.length > 0) {
        e.target.style.borderColor = '#10b981';
        // 只要关键词有内容就可以添加，不需要回复内容
        addBtn.style.opacity = '1';
        addBtn.style.transform = 'scale(1)';
    } else {
        e.target.style.borderColor = '#e5e7eb';
        addBtn.style.opacity = '0.7';
        addBtn.style.transform = 'scale(0.95)';
    }
    });

    document.getElementById('newReply')?.addEventListener('input', function(e) {
    const value = e.target.value.trim();
    const keywordInput = document.getElementById('newKeyword');

    // 回复内容可以为空，只需要关键词有内容即可
    if (value.length > 0) {
        e.target.style.borderColor = '#10b981';
    } else {
        e.target.style.borderColor = '#e5e7eb';
    }

    // 按钮状态只依赖关键词是否有内容
    const addBtn = document.querySelector('.add-btn');
    if (keywordInput.value.trim().length > 0) {
        addBtn.style.opacity = '1';
        addBtn.style.transform = 'scale(1)';
    } else {
        addBtn.style.opacity = '0.7';
        addBtn.style.transform = 'scale(0.95)';
    }
    });

    // 初始加载仪表盘
    loadDashboard();

    // 初始化图片关键词事件监听器
    initImageKeywordEventListeners();

    // 初始化卡券图片文件选择器
    initCardImageFileSelector();

    // 初始化编辑卡券图片文件选择器
    initEditCardImageFileSelector();

    // 初始化工具提示
    initTooltips();

    // 初始化商品搜索功能
    initItemsSearch();

    // 初始化商品搜索界面功能
    initItemSearch();

    // 点击侧边栏外部关闭移动端菜单
    document.addEventListener('click', function(e) {
    const sidebar = document.getElementById('sidebar');
    const toggle = document.querySelector('.mobile-toggle');

    if (window.innerWidth <= 768 &&
        !sidebar.contains(e.target) &&
        !toggle.contains(e.target) &&
        sidebar.classList.contains('show')) {
        sidebar.classList.remove('show');
    }
    });
});

// ==================== 默认回复管理功能 ====================

// 打开默认回复管理器
async function openDefaultReplyManager() {
    try {
    await loadDefaultReplies();
    const modal = new bootstrap.Modal(document.getElementById('defaultReplyModal'));
    modal.show();
    } catch (error) {
    console.error('打开默认回复管理器失败:', error);
    showToast('打开默认回复管理器失败', 'danger');
    }
}

// 加载默认回复列表
async function loadDefaultReplies() {
    try {
    // 获取所有账号
    const accountsResponse = await fetch(`${apiBase}/cookies`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (!accountsResponse.ok) {
        throw new Error('获取账号列表失败');
    }

    const accounts = await accountsResponse.json();

    // 获取所有默认回复设置
    const repliesResponse = await fetch(`${apiBase}/default-replies`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    let defaultReplies = {};
    if (repliesResponse.ok) {
        defaultReplies = await repliesResponse.json();
    }

    renderDefaultRepliesList(accounts, defaultReplies);
    } catch (error) {
    console.error('加载默认回复列表失败:', error);
    showToast('加载默认回复列表失败', 'danger');
    }
}

// 渲染默认回复列表
function renderDefaultRepliesList(accounts, defaultReplies) {
    const tbody = document.getElementById('defaultReplyTableBody');
    tbody.innerHTML = '';

    if (accounts.length === 0) {
    tbody.innerHTML = `
        <tr>
        <td colspan="5" class="text-center py-4 text-muted">
            <i class="bi bi-chat-text fs-1 d-block mb-3"></i>
            <h5>暂无账号数据</h5>
            <p class="mb-0">请先添加账号</p>
        </td>
        </tr>
    `;
    return;
    }

    accounts.forEach(accountId => {
    const replySettings = defaultReplies[accountId] || { enabled: false, reply_content: '', reply_once: false };
    const tr = document.createElement('tr');

    // 状态标签
    const statusBadge = replySettings.enabled ?
        '<span class="badge bg-success">启用</span>' :
        '<span class="badge bg-secondary">禁用</span>';

    // 只回复一次标签
    const replyOnceBadge = replySettings.reply_once ?
        '<span class="badge bg-warning">是</span>' :
        '<span class="badge bg-light text-dark">否</span>';

    // 回复内容预览
    let contentPreview = replySettings.reply_content || '未设置';
    if (contentPreview.length > 50) {
        contentPreview = contentPreview.substring(0, 50) + '...';
    }

    tr.innerHTML = `
        <td>
        <strong class="text-primary">${accountId}</strong>
        </td>
        <td>${statusBadge}</td>
        <td>${replyOnceBadge}</td>
        <td>
        <div class="text-truncate" style="max-width: 300px;" title="${replySettings.reply_content || ''}">
            ${contentPreview}
        </div>
        </td>
        <td>
        <div class="btn-group" role="group">
            <button class="btn btn-sm btn-outline-primary" onclick="editDefaultReply('${accountId}')" title="编辑">
            <i class="bi bi-pencil"></i>
            </button>
            <button class="btn btn-sm btn-outline-info" onclick="testDefaultReply('${accountId}')" title="测试">
            <i class="bi bi-play"></i>
            </button>
            ${replySettings.reply_once ? `
            <button class="btn btn-sm btn-outline-warning" onclick="clearDefaultReplyRecords('${accountId}')" title="清空记录">
            <i class="bi bi-arrow-clockwise"></i>
            </button>
            ` : ''}
        </div>
        </td>
    `;

    tbody.appendChild(tr);
    });
}

// 编辑默认回复
async function editDefaultReply(accountId) {
    try {
    // 获取当前设置
    const response = await fetch(`${apiBase}/default-replies/${accountId}`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    let settings = { enabled: false, reply_content: '', reply_once: false };
    if (response.ok) {
        settings = await response.json();
    }

    // 填充编辑表单
    document.getElementById('editAccountId').value = accountId;
    document.getElementById('editAccountIdDisplay').value = accountId;
    document.getElementById('editDefaultReplyEnabled').checked = settings.enabled;
    document.getElementById('editReplyContent').value = settings.reply_content || '';
    document.getElementById('editReplyOnce').checked = settings.reply_once || false;

    // 根据启用状态显示/隐藏内容输入框
    toggleReplyContentVisibility();

    // 显示编辑模态框
    const modal = new bootstrap.Modal(document.getElementById('editDefaultReplyModal'));
    modal.show();
    } catch (error) {
    console.error('获取默认回复设置失败:', error);
    showToast('获取默认回复设置失败', 'danger');
    }
}

// 切换回复内容输入框的显示/隐藏
function toggleReplyContentVisibility() {
    const enabled = document.getElementById('editDefaultReplyEnabled').checked;
    const contentGroup = document.getElementById('editReplyContentGroup');
    contentGroup.style.display = enabled ? 'block' : 'none';
}

// 保存默认回复设置
async function saveDefaultReply() {
    try {
    const accountId = document.getElementById('editAccountId').value;
    const enabled = document.getElementById('editDefaultReplyEnabled').checked;
    const replyContent = document.getElementById('editReplyContent').value;
    const replyOnce = document.getElementById('editReplyOnce').checked;

    if (enabled && !replyContent.trim()) {
        showToast('启用默认回复时必须设置回复内容', 'warning');
        return;
    }

    const data = {
        enabled: enabled,
        reply_content: enabled ? replyContent : null,
        reply_once: replyOnce
    };

    const response = await fetch(`${apiBase}/default-replies/${accountId}`, {
        method: 'PUT',
        headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    });

    if (response.ok) {
        showToast('默认回复设置保存成功', 'success');
        bootstrap.Modal.getInstance(document.getElementById('editDefaultReplyModal')).hide();
        loadDefaultReplies(); // 刷新列表
        loadCookies(); // 刷新账号列表以更新默认回复状态显示
    } else {
        const error = await response.text();
        showToast(`保存失败: ${error}`, 'danger');
    }
    } catch (error) {
    console.error('保存默认回复设置失败:', error);
    showToast('保存默认回复设置失败', 'danger');
    }
}

// 测试默认回复（占位函数）
function testDefaultReply(accountId) {
    showToast('测试功能开发中...', 'info');
}

// 清空默认回复记录
async function clearDefaultReplyRecords(accountId) {
    if (!confirm(`确定要清空账号 "${accountId}" 的默认回复记录吗？\n\n清空后，该账号将可以重新对之前回复过的对话进行默认回复。`)) {
        return;
    }

    try {
        const response = await fetch(`${apiBase}/default-replies/${accountId}/clear-records`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            }
        });

        if (response.ok) {
            showToast(`账号 "${accountId}" 的默认回复记录已清空`, 'success');
            loadDefaultReplies(); // 刷新列表
        } else {
            const error = await response.text();
            showToast(`清空失败: ${error}`, 'danger');
        }
    } catch (error) {
        console.error('清空默认回复记录失败:', error);
        showToast('清空默认回复记录失败', 'danger');
    }
}

// ==================== AI回复配置相关函数 ====================

// 配置AI回复
async function configAIReply(accountId) {
    try {
    // 获取当前AI回复设置
    const settings = await fetchJSON(`${apiBase}/ai-reply-settings/${accountId}`);

    // 填充表单
    document.getElementById('aiConfigAccountId').value = accountId;
    document.getElementById('aiConfigAccountIdDisplay').value = accountId;
    document.getElementById('aiReplyEnabled').checked = settings.ai_enabled;
    // 处理模型名称
    const modelSelect = document.getElementById('aiModelName');
    const customModelInput = document.getElementById('customModelName');
    const modelName = settings.model_name;
    // 检查是否是预设模型
    const presetModels = ['qwen-plus', 'qwen-turbo', 'qwen-max', 'gpt-3.5-turbo', 'gpt-4'];
    if (presetModels.includes(modelName)) {
        modelSelect.value = modelName;
        customModelInput.style.display = 'none';
        customModelInput.value = '';
    } else {
        // 自定义模型
        modelSelect.value = 'custom';
        customModelInput.style.display = 'block';
        customModelInput.value = modelName;
    }
    document.getElementById('aiBaseUrl').value = settings.base_url;
    document.getElementById('aiApiKey').value = settings.api_key;
    document.getElementById('maxDiscountPercent').value = settings.max_discount_percent;
    document.getElementById('maxDiscountAmount').value = settings.max_discount_amount;
    document.getElementById('maxBargainRounds').value = settings.max_bargain_rounds;
    document.getElementById('customPrompts').value = settings.custom_prompts;

    // 切换设置显示状态
    toggleAIReplySettings();

    // 显示模态框
    const modal = new bootstrap.Modal(document.getElementById('aiReplyConfigModal'));
    modal.show();

    } catch (error) {
    console.error('获取AI回复设置失败:', error);
    showToast('获取AI回复设置失败', 'danger');
    }
}

// 切换AI回复设置显示
function toggleAIReplySettings() {
    const enabled = document.getElementById('aiReplyEnabled').checked;
    const settingsDiv = document.getElementById('aiReplySettings');
    const bargainSettings = document.getElementById('bargainSettings');
    const promptSettings = document.getElementById('promptSettings');
    const testArea = document.getElementById('testArea');

    if (enabled) {
    settingsDiv.style.display = 'block';
    bargainSettings.style.display = 'block';
    promptSettings.style.display = 'block';
    testArea.style.display = 'block';
    } else {
    settingsDiv.style.display = 'none';
    bargainSettings.style.display = 'none';
    promptSettings.style.display = 'none';
    testArea.style.display = 'none';
    }
}

// 保存AI回复配置
async function saveAIReplyConfig() {
    try {
    const accountId = document.getElementById('aiConfigAccountId').value;
    const enabled = document.getElementById('aiReplyEnabled').checked;

    // 如果启用AI回复，验证必填字段
    if (enabled) {
        const apiKey = document.getElementById('aiApiKey').value.trim();
        if (!apiKey) {
        showToast('请输入API密钥', 'warning');
        return;
        }

        // 验证自定义提示词格式
        const customPrompts = document.getElementById('customPrompts').value.trim();
        if (customPrompts) {
        try {
            JSON.parse(customPrompts);
        } catch (e) {
            showToast('自定义提示词格式错误，请检查JSON格式', 'warning');
            return;
        }
        }
    }
// 获取模型名称
    let modelName = document.getElementById('aiModelName').value;
    if (modelName === 'custom') {
        const customModelName = document.getElementById('customModelName').value.trim();
        if (!customModelName) {
        showToast('请输入自定义模型名称', 'warning');
        return;
        }
        modelName = customModelName;
    }
    // 构建设置对象
    const settings = {
        ai_enabled: enabled,
        model_name: modelName,
        api_key: document.getElementById('aiApiKey').value,
        base_url: document.getElementById('aiBaseUrl').value,
        max_discount_percent: parseInt(document.getElementById('maxDiscountPercent').value),
        max_discount_amount: parseInt(document.getElementById('maxDiscountAmount').value),
        max_bargain_rounds: parseInt(document.getElementById('maxBargainRounds').value),
        custom_prompts: document.getElementById('customPrompts').value
    };

    // 保存设置
    const response = await fetch(`${apiBase}/ai-reply-settings/${accountId}`, {
        method: 'PUT',
        headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
        },
        body: JSON.stringify(settings)
    });

    if (response.ok) {
        showToast('AI回复配置保存成功', 'success');
        bootstrap.Modal.getInstance(document.getElementById('aiReplyConfigModal')).hide();
        loadCookies(); // 刷新账号列表以更新AI回复状态显示
    } else {
        const error = await response.text();
        showToast(`保存失败: ${error}`, 'danger');
    }

    } catch (error) {
    console.error('保存AI回复配置失败:', error);
    showToast('保存AI回复配置失败', 'danger');
    }
}

// 测试AI回复
async function testAIReply() {
    try {
    const accountId = document.getElementById('aiConfigAccountId').value;
    const testMessage = document.getElementById('testMessage').value.trim();
    const testItemPrice = document.getElementById('testItemPrice').value;

    if (!testMessage) {
        showToast('请输入测试消息', 'warning');
        return;
    }

    // 构建测试数据
    const testData = {
        message: testMessage,
        item_title: '测试商品',
        item_price: parseFloat(testItemPrice) || 100,
        item_desc: '这是一个用于测试AI回复功能的商品'
    };

    // 显示加载状态
    const testResult = document.getElementById('testResult');
    const testReplyContent = document.getElementById('testReplyContent');
    testResult.style.display = 'block';
    testReplyContent.innerHTML = '<i class="bi bi-hourglass-split"></i> 正在生成AI回复...';

    // 调用测试API
    const response = await fetch(`${apiBase}/ai-reply-test/${accountId}`, {
        method: 'POST',
        headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
        },
        body: JSON.stringify(testData)
    });

    if (response.ok) {
        const result = await response.json();
        testReplyContent.innerHTML = result.reply;
        showToast('AI回复测试成功', 'success');
    } else {
        const error = await response.text();
        testReplyContent.innerHTML = `<span class="text-danger">测试失败: ${error}</span>`;
        showToast(`测试失败: ${error}`, 'danger');
    }

    } catch (error) {
    console.error('测试AI回复失败:', error);
    const testReplyContent = document.getElementById('testReplyContent');
    testReplyContent.innerHTML = `<span class="text-danger">测试失败: ${error.message}</span>`;
    showToast('测试AI回复失败', 'danger');
    }
}

// 切换自定义模型输入框的显示/隐藏
function toggleCustomModelInput() {
    const modelSelect = document.getElementById('aiModelName');
    const customModelInput = document.getElementById('customModelName');
    if (modelSelect.value === 'custom') {
    customModelInput.style.display = 'block';
    customModelInput.focus();
    } else {
    customModelInput.style.display = 'none';
    customModelInput.value = '';
    }
}

// 监听默认回复启用状态变化
document.addEventListener('DOMContentLoaded', function() {
    const enabledCheckbox = document.getElementById('editDefaultReplyEnabled');
    if (enabledCheckbox) {
    enabledCheckbox.addEventListener('change', toggleReplyContentVisibility);
    }
});

// ================================
// 【外发配置菜单】相关功能
// ================================

// 外发配置类型配置
const outgoingConfigs = {
    smtp: {
        title: 'SMTP邮件配置',
        description: '配置SMTP服务器用于发送注册验证码等邮件通知',
        icon: 'bi-envelope-fill',
        color: 'primary',
        fields: [
            {
                id: 'smtp_server',
                label: 'SMTP服务器',
                type: 'text',
                placeholder: 'smtp.qq.com',
                required: true,
                help: '邮箱服务商的SMTP服务器地址，如：smtp.qq.com、smtp.gmail.com'
            },
            {
                id: 'smtp_port',
                label: 'SMTP端口',
                type: 'number',
                placeholder: '587',
                required: true,
                help: '通常为587（TLS）或465（SSL）'
            },
            {
                id: 'smtp_user',
                label: '发件邮箱',
                type: 'email',
                placeholder: 'your-email@qq.com',
                required: true,
                help: '用于发送邮件的邮箱地址'
            },
            {
                id: 'smtp_password',
                label: '邮箱密码/授权码',
                type: 'password',
                placeholder: '输入密码或授权码',
                required: true,
                help: '邮箱密码或应用专用密码（QQ邮箱需要授权码）'
            },
            {
                id: 'smtp_from',
                label: '发件人显示名（可选）',
                type: 'text',
                placeholder: '闲鱼自动回复系统',
                required: false,
                help: '邮件发件人显示的名称，留空则使用邮箱地址'
            },
            {
                id: 'smtp_use_tls',
                label: '启用TLS',
                type: 'select',
                options: [
                    { value: 'true', text: '是' },
                    { value: 'false', text: '否' }
                ],
                required: true,
                help: '是否启用TLS加密（推荐开启）'
            },
            {
                id: 'smtp_use_ssl',
                label: '启用SSL',
                type: 'select',
                options: [
                    { value: 'true', text: '是' },
                    { value: 'false', text: '否' }
                ],
                required: true,
                help: '是否启用SSL加密（与TLS二选一）'
            }
        ]
    }
};

// ================================
// 【通知渠道菜单】相关功能
// ================================

// 通知渠道类型配置
const channelTypeConfigs = {
    qq: {
    title: 'QQ通知',
    description: '需要添加QQ号 <code>3668943488</code> 为好友才能正常接收消息通知',
    icon: 'bi-chat-dots-fill',
    color: 'primary',
    fields: [
        {
        id: 'qq_number',
        label: '接收QQ号码',
        type: 'text',
        placeholder: '输入QQ号码',
        required: true,
        help: '用于接收通知消息的QQ号码'
        }
    ]
    },
    dingtalk: {
    title: '钉钉通知',
    description: '请设置钉钉机器人Webhook URL，支持自定义机器人和群机器人',
    icon: 'bi-bell-fill',
    color: 'info',
    fields: [
        {
        id: 'webhook_url',
        label: '钉钉机器人Webhook URL',
        type: 'url',
        placeholder: 'https://oapi.dingtalk.com/robot/send?access_token=...',
        required: true,
        help: '钉钉机器人的Webhook地址'
        },
        {
        id: 'secret',
        label: '加签密钥（可选）',
        type: 'text',
        placeholder: '输入加签密钥',
        required: false,
        help: '如果机器人开启了加签验证，请填写密钥'
        }
    ]
    },
    email: {
    title: '邮件通知',
    description: '通过SMTP服务器发送邮件通知，支持各种邮箱服务商',
    icon: 'bi-envelope-fill',
    color: 'success',
    fields: [
        {
        id: 'smtp_server',
        label: 'SMTP服务器',
        type: 'text',
        placeholder: 'smtp.gmail.com',
        required: true,
        help: '邮箱服务商的SMTP服务器地址'
        },
        {
        id: 'smtp_port',
        label: 'SMTP端口',
        type: 'number',
        placeholder: '587',
        required: true,
        help: '通常为587（TLS）或465（SSL）'
        },
        {
        id: 'email_user',
        label: '发送邮箱',
        type: 'email',
        placeholder: 'your-email@gmail.com',
        required: true,
        help: '用于发送通知的邮箱地址'
        },
        {
        id: 'email_password',
        label: '邮箱密码/授权码',
        type: 'password',
        placeholder: '输入密码或授权码',
        required: true,
        help: '邮箱密码或应用专用密码'
        },
        {
        id: 'recipient_email',
        label: '接收邮箱',
        type: 'email',
        placeholder: 'recipient@example.com',
        required: true,
        help: '用于接收通知的邮箱地址'
        }
    ]
    },
    webhook: {
    title: 'Webhook通知',
    description: '通过HTTP POST请求发送通知到自定义的Webhook地址',
    icon: 'bi-link-45deg',
    color: 'warning',
    fields: [
        {
        id: 'webhook_url',
        label: 'Webhook URL',
        type: 'url',
        placeholder: 'https://your-server.com/webhook',
        required: true,
        help: '接收通知的Webhook地址'
        },
        {
        id: 'http_method',
        label: 'HTTP方法',
        type: 'select',
        options: [
            { value: 'POST', text: 'POST' },
            { value: 'PUT', text: 'PUT' }
        ],
        required: true,
        help: '发送请求使用的HTTP方法'
        },
        {
        id: 'headers',
        label: '自定义请求头（可选）',
        type: 'textarea',
        placeholder: '{"Authorization": "Bearer token", "Content-Type": "application/json"}',
        required: false,
        help: 'JSON格式的自定义请求头'
        }
    ]
    },
    wechat: {
    title: '微信通知',
    description: '通过企业微信机器人发送通知消息',
    icon: 'bi-wechat',
    color: 'success',
    fields: [
        {
        id: 'webhook_url',
        label: '企业微信机器人Webhook URL',
        type: 'url',
        placeholder: 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...',
        required: true,
        help: '企业微信群机器人的Webhook地址'
        }
    ]
    },
    telegram: {
    title: 'Telegram通知',
    description: '通过Telegram机器人发送通知消息',
    icon: 'bi-telegram',
    color: 'primary',
    fields: [
        {
        id: 'bot_token',
        label: 'Bot Token',
        type: 'text',
        placeholder: '123456789:ABCdefGHIjklMNOpqrsTUVwxyz',
        required: true,
        help: '从@BotFather获取的机器人Token'
        },
        {
        id: 'chat_id',
        label: 'Chat ID',
        type: 'text',
        placeholder: '123456789 或 @channel_name',
        required: true,
        help: '接收消息的用户ID或频道名'
        }
    ]
    }
};

// 显示添加渠道模态框
function showAddChannelModal(type) {
    const config = channelTypeConfigs[type];
    if (!config) {
    showToast('不支持的通知渠道类型', 'danger');
    return;
    }

    // 设置模态框标题和描述
    document.getElementById('addChannelModalTitle').textContent = `添加${config.title}`;
    document.getElementById('channelTypeDescription').innerHTML = config.description;
    document.getElementById('channelType').value = type;

    // 生成配置字段
    const fieldsContainer = document.getElementById('channelConfigFields');
    fieldsContainer.innerHTML = '';

    config.fields.forEach(field => {
    const fieldHtml = generateFieldHtml(field, '');
    fieldsContainer.insertAdjacentHTML('beforeend', fieldHtml);
    });

    // 显示模态框
    const modal = new bootstrap.Modal(document.getElementById('addChannelModal'));
    modal.show();
}

// 生成表单字段HTML
function generateFieldHtml(field, prefix) {
    const fieldId = prefix + field.id;
    let inputHtml = '';

    switch (field.type) {
    case 'select':
        inputHtml = `<select class="form-select" id="${fieldId}" ${field.required ? 'required' : ''}>`;
        if (field.options) {
        field.options.forEach(option => {
            inputHtml += `<option value="${option.value}">${option.text}</option>`;
        });
        }
        inputHtml += '</select>';
        break;
    case 'textarea':
        inputHtml = `<textarea class="form-control" id="${fieldId}" placeholder="${field.placeholder}" rows="3" ${field.required ? 'required' : ''}></textarea>`;
        break;
    default:
        inputHtml = `<input type="${field.type}" class="form-control" id="${fieldId}" placeholder="${field.placeholder}" ${field.required ? 'required' : ''}>`;
    }

    return `
    <div class="mb-3">
        <label for="${fieldId}" class="form-label">
        ${field.label} ${field.required ? '<span class="text-danger">*</span>' : ''}
        </label>
        ${inputHtml}
        ${field.help ? `<small class="form-text text-muted">${field.help}</small>` : ''}
    </div>
    `;
}

// 保存通知渠道
async function saveNotificationChannel() {
    const type = document.getElementById('channelType').value;
    const name = document.getElementById('channelName').value;
    const enabled = document.getElementById('channelEnabled').checked;

    if (!name.trim()) {
    showToast('请输入渠道名称', 'warning');
    return;
    }

    const config = channelTypeConfigs[type];
    if (!config) {
    showToast('无效的渠道类型', 'danger');
    return;
    }

    // 收集配置数据
    const configData = {};
    let hasError = false;

    config.fields.forEach(field => {
    const element = document.getElementById(field.id);
    const value = element.value.trim();

    if (field.required && !value) {
        showToast(`请填写${field.label}`, 'warning');
        hasError = true;
        return;
    }

    if (value) {
        configData[field.id] = value;
    }
    });

    if (hasError) return;

    try {
    const response = await fetch(`${apiBase}/notification-channels`, {
        method: 'POST',
        headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
        },
        body: JSON.stringify({
        name: name,
        type: type,
        config: JSON.stringify(configData),
        enabled: enabled
        })
    });

    if (response.ok) {
        showToast('通知渠道添加成功', 'success');
        const modal = bootstrap.Modal.getInstance(document.getElementById('addChannelModal'));
        modal.hide();
        loadNotificationChannels();
    } else {
        const error = await response.text();
        showToast(`添加失败: ${error}`, 'danger');
    }
    } catch (error) {
    console.error('添加通知渠道失败:', error);
    showToast('添加通知渠道失败', 'danger');
    }
}

// 加载通知渠道列表
async function loadNotificationChannels() {
    try {
    const response = await fetch(`${apiBase}/notification-channels`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (!response.ok) {
        throw new Error('获取通知渠道失败');
    }

    const channels = await response.json();
    renderNotificationChannels(channels);
    } catch (error) {
    console.error('加载通知渠道失败:', error);
    showToast('加载通知渠道失败', 'danger');
    }
}

// 渲染通知渠道列表
function renderNotificationChannels(channels) {
    const tbody = document.getElementById('channelsTableBody');
    tbody.innerHTML = '';

    if (channels.length === 0) {
    tbody.innerHTML = `
        <tr>
        <td colspan="6" class="text-center py-4 text-muted">
            <i class="bi bi-bell fs-1 d-block mb-3"></i>
            <h5>暂无通知渠道</h5>
            <p class="mb-0">点击上方按钮添加通知渠道</p>
        </td>
        </tr>
    `;
    return;
    }

    channels.forEach(channel => {
    const tr = document.createElement('tr');

    const statusBadge = channel.enabled ?
        '<span class="badge bg-success">启用</span>' :
        '<span class="badge bg-secondary">禁用</span>';

    // 获取渠道类型配置（处理类型映射）
    let channelType = channel.type;
    if (channelType === 'ding_talk') {
        channelType = 'dingtalk';  // 兼容旧的类型名
    }
    const typeConfig = channelTypeConfigs[channelType];
    const typeDisplay = typeConfig ? typeConfig.title : channel.type;
    const typeColor = typeConfig ? typeConfig.color : 'secondary';

    // 解析并显示配置信息
    let configDisplay = '';
    try {
        const configData = JSON.parse(channel.config || '{}');
        const configEntries = Object.entries(configData);

        if (configEntries.length > 0) {
        configDisplay = configEntries.map(([key, value]) => {
            // 隐藏敏感信息
            if (key.includes('password') || key.includes('token') || key.includes('secret')) {
            return `${key}: ****`;
            }
            // 截断过长的值
            const displayValue = value.length > 30 ? value.substring(0, 30) + '...' : value;
            return `${key}: ${displayValue}`;
        }).join('<br>');
        } else {
        configDisplay = channel.config || '无配置';
        }
    } catch (e) {
        // 兼容旧格式
        configDisplay = channel.config || '无配置';
        if (configDisplay.length > 30) {
        configDisplay = configDisplay.substring(0, 30) + '...';
        }
    }

    tr.innerHTML = `
        <td><strong class="text-primary">${channel.id}</strong></td>
        <td>
        <div class="d-flex align-items-center">
            <i class="bi ${typeConfig ? typeConfig.icon : 'bi-bell'} me-2 text-${typeColor}"></i>
            ${channel.name}
        </div>
        </td>
        <td><span class="badge bg-${typeColor}">${typeDisplay}</span></td>
        <td><small class="text-muted">${configDisplay}</small></td>
        <td>${statusBadge}</td>
        <td>
        <div class="btn-group" role="group">
            <button class="btn btn-sm btn-outline-primary" onclick="editNotificationChannel(${channel.id})" title="编辑">
            <i class="bi bi-pencil"></i>
            </button>
            <button class="btn btn-sm btn-outline-danger" onclick="deleteNotificationChannel(${channel.id})" title="删除">
            <i class="bi bi-trash"></i>
            </button>
        </div>
        </td>
    `;

    tbody.appendChild(tr);
    });
}



// 删除通知渠道
async function deleteNotificationChannel(channelId) {
    if (!confirm('确定要删除这个通知渠道吗？')) {
    return;
    }

    try {
    const response = await fetch(`${apiBase}/notification-channels/${channelId}`, {
        method: 'DELETE',
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        showToast('通知渠道删除成功', 'success');
        loadNotificationChannels();
    } else {
        const error = await response.text();
        showToast(`删除失败: ${error}`, 'danger');
    }
    } catch (error) {
    console.error('删除通知渠道失败:', error);
    showToast('删除通知渠道失败', 'danger');
    }
}

// 编辑通知渠道
async function editNotificationChannel(channelId) {
    try {
    // 获取渠道详情
    const response = await fetch(`${apiBase}/notification-channels`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (!response.ok) {
        throw new Error('获取通知渠道失败');
    }

    const channels = await response.json();
    const channel = channels.find(c => c.id === channelId);

    if (!channel) {
        showToast('通知渠道不存在', 'danger');
        return;
    }

    // 处理类型映射
    let channelType = channel.type;
    if (channelType === 'ding_talk') {
        channelType = 'dingtalk';  // 兼容旧的类型名
    }

    const config = channelTypeConfigs[channelType];
    if (!config) {
        showToast('不支持的渠道类型', 'danger');
        return;
    }

    // 填充基本信息
    document.getElementById('editChannelId').value = channel.id;
    document.getElementById('editChannelType').value = channelType;  // 使用映射后的类型
    document.getElementById('editChannelName').value = channel.name;
    document.getElementById('editChannelEnabled').checked = channel.enabled;

    // 解析配置数据
    let configData = {};
    try {
        configData = JSON.parse(channel.config || '{}');
    } catch (e) {
        // 兼容旧格式（直接字符串）
        if (channel.type === 'qq') {
        configData = { qq_number: channel.config };
        } else if (channel.type === 'dingtalk' || channel.type === 'ding_talk') {
        configData = { webhook_url: channel.config };
        } else {
        configData = { config: channel.config };
        }
    }

    // 生成编辑字段
    const fieldsContainer = document.getElementById('editChannelConfigFields');
    fieldsContainer.innerHTML = '';

    config.fields.forEach(field => {
        const fieldHtml = generateFieldHtml(field, 'edit_');
        fieldsContainer.insertAdjacentHTML('beforeend', fieldHtml);

        // 填充现有值
        const element = document.getElementById('edit_' + field.id);
        if (element && configData[field.id]) {
        element.value = configData[field.id];
        }
    });

    // 显示编辑模态框
    const modal = new bootstrap.Modal(document.getElementById('editChannelModal'));
    modal.show();
    } catch (error) {
    console.error('编辑通知渠道失败:', error);
    showToast('编辑通知渠道失败', 'danger');
    }
}

// 更新通知渠道
async function updateNotificationChannel() {
    const channelId = document.getElementById('editChannelId').value;
    const type = document.getElementById('editChannelType').value;
    const name = document.getElementById('editChannelName').value;
    const enabled = document.getElementById('editChannelEnabled').checked;

    if (!name.trim()) {
    showToast('请输入渠道名称', 'warning');
    return;
    }

    const config = channelTypeConfigs[type];
    if (!config) {
    showToast('无效的渠道类型', 'danger');
    return;
    }

    // 收集配置数据
    const configData = {};
    let hasError = false;

    config.fields.forEach(field => {
    const element = document.getElementById('edit_' + field.id);
    const value = element.value.trim();

    if (field.required && !value) {
        showToast(`请填写${field.label}`, 'warning');
        hasError = true;
        return;
    }

    if (value) {
        configData[field.id] = value;
    }
    });

    if (hasError) return;

    try {
    const response = await fetch(`${apiBase}/notification-channels/${channelId}`, {
        method: 'PUT',
        headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
        },
        body: JSON.stringify({
        name: name,
        config: JSON.stringify(configData),
        enabled: enabled
        })
    });

    if (response.ok) {
        showToast('通知渠道更新成功', 'success');
        const modal = bootstrap.Modal.getInstance(document.getElementById('editChannelModal'));
        modal.hide();
        loadNotificationChannels();
    } else {
        const error = await response.text();
        showToast(`更新失败: ${error}`, 'danger');
    }
    } catch (error) {
    console.error('更新通知渠道失败:', error);
    showToast('更新通知渠道失败', 'danger');
    }
}

// ================================
// 【消息通知菜单】相关功能
// ================================

// 加载消息通知配置
async function loadMessageNotifications() {
    try {
    // 获取所有账号
    const accountsResponse = await fetch(`${apiBase}/cookies`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (!accountsResponse.ok) {
        throw new Error('获取账号列表失败');
    }

    const accounts = await accountsResponse.json();

    // 获取所有通知配置
    const notificationsResponse = await fetch(`${apiBase}/message-notifications`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    let notifications = {};
    if (notificationsResponse.ok) {
        notifications = await notificationsResponse.json();
    }

    renderMessageNotifications(accounts, notifications);
    } catch (error) {
    console.error('加载消息通知配置失败:', error);
    showToast('加载消息通知配置失败', 'danger');
    }
}

// 渲染消息通知配置
function renderMessageNotifications(accounts, notifications) {
    const tbody = document.getElementById('notificationsTableBody');
    tbody.innerHTML = '';

    if (accounts.length === 0) {
    tbody.innerHTML = `
        <tr>
        <td colspan="4" class="text-center py-4 text-muted">
            <i class="bi bi-chat-dots fs-1 d-block mb-3"></i>
            <h5>暂无账号数据</h5>
            <p class="mb-0">请先添加账号</p>
        </td>
        </tr>
    `;
    return;
    }

    accounts.forEach(accountId => {
    const accountNotifications = notifications[accountId] || [];
    const tr = document.createElement('tr');

    let channelsList = '';
    if (accountNotifications.length > 0) {
        channelsList = accountNotifications.map(n =>
        `<span class="badge bg-${n.enabled ? 'success' : 'secondary'} me-1">${n.channel_name}</span>`
        ).join('');
    } else {
        channelsList = '<span class="text-muted">未配置</span>';
    }

    const status = accountNotifications.some(n => n.enabled) ?
        '<span class="badge bg-success">启用</span>' :
        '<span class="badge bg-secondary">禁用</span>';

    tr.innerHTML = `
        <td><strong class="text-primary">${accountId}</strong></td>
        <td>${channelsList}</td>
        <td>${status}</td>
        <td>
        <div class="btn-group" role="group">
            <button class="btn btn-sm btn-outline-primary" onclick="configAccountNotification('${accountId}')" title="配置">
            <i class="bi bi-gear"></i> 配置
            </button>
            ${accountNotifications.length > 0 ? `
            <button class="btn btn-sm btn-outline-danger" onclick="deleteAccountNotification('${accountId}')" title="删除配置">
            <i class="bi bi-trash"></i>
            </button>
            ` : ''}
        </div>
        </td>
    `;

    tbody.appendChild(tr);
    });
}

// 配置账号通知
async function configAccountNotification(accountId) {
    try {
    // 获取所有通知渠道
    const channelsResponse = await fetch(`${apiBase}/notification-channels`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (!channelsResponse.ok) {
        throw new Error('获取通知渠道失败');
    }

    const channels = await channelsResponse.json();

    if (channels.length === 0) {
        showToast('请先添加通知渠道', 'warning');
        return;
    }

    // 获取当前账号的通知配置
    const notificationResponse = await fetch(`${apiBase}/message-notifications/${accountId}`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    let currentNotifications = [];
    if (notificationResponse.ok) {
        currentNotifications = await notificationResponse.json();
    }

    // 填充表单
    document.getElementById('configAccountId').value = accountId;
    document.getElementById('displayAccountId').value = accountId;

    // 填充通知渠道选项
    const channelSelect = document.getElementById('notificationChannel');
    channelSelect.innerHTML = '<option value="">请选择通知渠道</option>';

    // 获取当前配置的第一个通知渠道（如果存在）
    const currentNotification = currentNotifications.length > 0 ? currentNotifications[0] : null;

    channels.forEach(channel => {
        if (channel.enabled) {
        const option = document.createElement('option');
        option.value = channel.id;
        option.textContent = `${channel.name} (${channel.config})`;
        if (currentNotification && currentNotification.channel_id === channel.id) {
            option.selected = true;
        }
        channelSelect.appendChild(option);
        }
    });

    // 设置启用状态
    document.getElementById('notificationEnabled').checked =
        currentNotification ? currentNotification.enabled : true;

    // 显示配置模态框
    const modal = new bootstrap.Modal(document.getElementById('configNotificationModal'));
    modal.show();
    } catch (error) {
    console.error('配置账号通知失败:', error);
    showToast('配置账号通知失败', 'danger');
    }
}

// 删除账号通知配置
async function deleteAccountNotification(accountId) {
    if (!confirm(`确定要删除账号 ${accountId} 的通知配置吗？`)) {
    return;
    }

    try {
    const response = await fetch(`${apiBase}/message-notifications/account/${accountId}`, {
        method: 'DELETE',
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        showToast('通知配置删除成功', 'success');
        loadMessageNotifications();
    } else {
        const error = await response.text();
        showToast(`删除失败: ${error}`, 'danger');
    }
    } catch (error) {
    console.error('删除通知配置失败:', error);
    showToast('删除通知配置失败', 'danger');
    }
}

// 保存账号通知配置
async function saveAccountNotification() {
    const accountId = document.getElementById('configAccountId').value;
    const channelId = document.getElementById('notificationChannel').value;
    const enabled = document.getElementById('notificationEnabled').checked;

    if (!channelId) {
    showToast('请选择通知渠道', 'warning');
    return;
    }

    try {
    const response = await fetch(`${apiBase}/message-notifications/${accountId}`, {
        method: 'POST',
        headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
        },
        body: JSON.stringify({
        channel_id: parseInt(channelId),
        enabled: enabled
        })
    });

    if (response.ok) {
        showToast('通知配置保存成功', 'success');
        const modal = bootstrap.Modal.getInstance(document.getElementById('configNotificationModal'));
        modal.hide();
        loadMessageNotifications();
    } else {
        const error = await response.text();
        showToast(`保存失败: ${error}`, 'danger');
    }
    } catch (error) {
    console.error('保存通知配置失败:', error);
    showToast('保存通知配置失败', 'danger');
    }
}

// ================================
// 【卡券管理菜单】相关功能
// ================================

// 加载卡券列表
async function loadCards() {
    try {
    const response = await fetch(`${apiBase}/cards`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        const cards = await response.json();
        renderCardsList(cards);
        updateCardsStats(cards);
    } else {
        showToast('加载卡券列表失败', 'danger');
    }
    } catch (error) {
    console.error('加载卡券列表失败:', error);
    showToast('加载卡券列表失败', 'danger');
    }
}

// 渲染卡券列表
function renderCardsList(cards) {
    const tbody = document.getElementById('cardsTableBody');

    if (cards.length === 0) {
    tbody.innerHTML = `
        <tr>
        <td colspan="8" class="text-center py-4 text-muted">
            <i class="bi bi-credit-card fs-1 d-block mb-3"></i>
            <h5>暂无卡券数据</h5>
            <p class="mb-0">点击"添加卡券"开始创建您的第一个卡券</p>
        </td>
        </tr>
    `;
    return;
    }

    tbody.innerHTML = '';

    cards.forEach(card => {
    const tr = document.createElement('tr');

    // 类型标签
    let typeBadge = '';
    switch(card.type) {
        case 'api':
        typeBadge = '<span class="badge bg-info">API接口</span>';
        break;
        case 'text':
        typeBadge = '<span class="badge bg-success">固定文字</span>';
        break;
        case 'data':
        typeBadge = '<span class="badge bg-warning">批量数据</span>';
        break;
        case 'image':
        typeBadge = '<span class="badge bg-primary">图片</span>';
        break;
    }

    // 状态标签
    const statusBadge = card.enabled ?
        '<span class="badge bg-success">启用</span>' :
        '<span class="badge bg-secondary">禁用</span>';

    // 数据量显示
    let dataCount = '-';
    if (card.type === 'data' && card.data_content) {
        const lines = card.data_content.split('\n').filter(line => line.trim());
        dataCount = lines.length;
    } else if (card.type === 'api') {
        dataCount = '∞';
    } else if (card.type === 'text') {
        dataCount = '1';
    } else if (card.type === 'image') {
        dataCount = '1';
    }

    // 延时时间显示
    const delayDisplay = card.delay_seconds > 0 ?
        `${card.delay_seconds}秒` :
        '<span class="text-muted">立即</span>';

    // 规格信息显示
    let specDisplay = '<span class="text-muted">普通卡券</span>';
    if (card.is_multi_spec && card.spec_name && card.spec_value) {
        specDisplay = `<span class="badge bg-primary">${card.spec_name}: ${card.spec_value}</span>`;
    }

    tr.innerHTML = `
        <td>
        <div class="fw-bold">${card.name}</div>
        ${card.description ? `<small class="text-muted">${card.description}</small>` : ''}
        </td>
        <td>${typeBadge}</td>
        <td>${specDisplay}</td>
        <td>${dataCount}</td>
        <td>${delayDisplay}</td>
        <td>${statusBadge}</td>
        <td>
        <small class="text-muted">${new Date(card.created_at).toLocaleString('zh-CN')}</small>
        </td>
        <td>
        <div class="btn-group" role="group">
            <button class="btn btn-sm btn-outline-primary" onclick="editCard(${card.id})" title="编辑">
            <i class="bi bi-pencil"></i>
            </button>
            <button class="btn btn-sm btn-outline-info" onclick="testCard(${card.id})" title="测试">
            <i class="bi bi-play"></i>
            </button>
            <button class="btn btn-sm btn-outline-danger" onclick="deleteCard(${card.id})" title="删除">
            <i class="bi bi-trash"></i>
            </button>
        </div>
        </td>
    `;

    tbody.appendChild(tr);
    });
}

// 更新卡券统计
function updateCardsStats(cards) {
    const totalCards = cards.length;
    const apiCards = cards.filter(card => card.type === 'api').length;
    const textCards = cards.filter(card => card.type === 'text').length;
    const dataCards = cards.filter(card => card.type === 'data').length;

    document.getElementById('totalCards').textContent = totalCards;
    document.getElementById('apiCards').textContent = apiCards;
    document.getElementById('textCards').textContent = textCards;
    document.getElementById('dataCards').textContent = dataCards;
}

// 显示添加卡券模态框
function showAddCardModal() {
    document.getElementById('addCardForm').reset();
    toggleCardTypeFields();
    const modal = new bootstrap.Modal(document.getElementById('addCardModal'));
    modal.show();
}

// 切换卡券类型字段显示
function toggleCardTypeFields() {
    const cardType = document.getElementById('cardType').value;

    document.getElementById('apiFields').style.display = cardType === 'api' ? 'block' : 'none';
    document.getElementById('textFields').style.display = cardType === 'text' ? 'block' : 'none';
    document.getElementById('dataFields').style.display = cardType === 'data' ? 'block' : 'none';
    document.getElementById('imageFields').style.display = cardType === 'image' ? 'block' : 'none';

    // 如果是API类型，初始化API方法监听
    if (cardType === 'api') {
        toggleApiParamsHelp();
        // 添加API方法变化监听
        const apiMethodSelect = document.getElementById('apiMethod');
        if (apiMethodSelect) {
            apiMethodSelect.removeEventListener('change', toggleApiParamsHelp);
            apiMethodSelect.addEventListener('change', toggleApiParamsHelp);
        }
    }
}

// 切换API参数提示显示
function toggleApiParamsHelp() {
    const apiMethod = document.getElementById('apiMethod').value;
    const postParamsHelp = document.getElementById('postParamsHelp');

    if (postParamsHelp) {
        postParamsHelp.style.display = apiMethod === 'POST' ? 'block' : 'none';

        // 如果显示参数提示，添加点击事件
        if (apiMethod === 'POST') {
            initParamClickHandlers('apiParams', 'postParamsHelp');
        }
    }
}

// 初始化参数点击处理器
function initParamClickHandlers(textareaId, containerId) {
    const container = document.getElementById(containerId);
    const textarea = document.getElementById(textareaId);

    if (!container || !textarea) return;

    // 移除现有的点击事件监听器
    const paramNames = container.querySelectorAll('.param-name');
    paramNames.forEach(paramName => {
        paramName.removeEventListener('click', handleParamClick);
    });

    // 添加新的点击事件监听器
    paramNames.forEach(paramName => {
        paramName.addEventListener('click', function() {
            handleParamClick(this, textarea);
        });
    });
}

// 处理参数点击事件
function handleParamClick(paramElement, textarea) {
    const paramName = paramElement.textContent.trim();
    const paramValue = `{${paramName}}`;

    try {
        // 获取当前textarea的值
        let currentValue = textarea.value.trim();

        // 如果当前值为空或不是有效的JSON，创建新的JSON对象
        if (!currentValue || currentValue === '{}') {
            const newJson = {};
            newJson[paramName] = paramValue;
            textarea.value = JSON.stringify(newJson, null, 2);
        } else {
            // 尝试解析现有的JSON
            let jsonObj;
            try {
                jsonObj = JSON.parse(currentValue);
            } catch (e) {
                // 如果解析失败，创建新的JSON对象
                jsonObj = {};
            }

            // 添加新参数
            jsonObj[paramName] = paramValue;

            // 更新textarea
            textarea.value = JSON.stringify(jsonObj, null, 2);
        }

        // 触发change事件
        textarea.dispatchEvent(new Event('change'));

        // 显示成功提示
        showToast(`已添加参数: ${paramName}`, 'success');

    } catch (error) {
        console.error('添加参数时出错:', error);
        showToast('添加参数失败', 'danger');
    }
}

// 切换多规格字段显示
function toggleMultiSpecFields() {
    const isMultiSpec = document.getElementById('isMultiSpec').checked;
    document.getElementById('multiSpecFields').style.display = isMultiSpec ? 'block' : 'none';
}

// 初始化卡券图片文件选择器
function initCardImageFileSelector() {
    const fileInput = document.getElementById('cardImageFile');
    if (fileInput) {
        fileInput.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                // 验证文件类型
                if (!file.type.startsWith('image/')) {
                    showToast('❌ 请选择图片文件，当前文件类型：' + file.type, 'warning');
                    e.target.value = '';
                    hideCardImagePreview();
                    return;
                }

                // 验证文件大小（5MB）
                if (file.size > 5 * 1024 * 1024) {
                    showToast('❌ 图片文件大小不能超过 5MB，当前文件大小：' + (file.size / 1024 / 1024).toFixed(1) + 'MB', 'warning');
                    e.target.value = '';
                    hideCardImagePreview();
                    return;
                }

                // 验证图片尺寸
                validateCardImageDimensions(file, e.target);
            } else {
                hideCardImagePreview();
            }
        });
    }
}

// 验证卡券图片尺寸
function validateCardImageDimensions(file, inputElement) {
    const img = new Image();
    const url = URL.createObjectURL(file);

    img.onload = function() {
        const width = this.naturalWidth;
        const height = this.naturalHeight;

        // 释放对象URL
        URL.revokeObjectURL(url);

        // 检查图片尺寸
        const maxDimension = 4096;
        const maxPixels = 8 * 1024 * 1024; // 8M像素
        const totalPixels = width * height;

        if (width > maxDimension || height > maxDimension) {
            showToast(`❌ 图片尺寸过大：${width}x${height}，最大允许：${maxDimension}x${maxDimension}像素`, 'warning');
            inputElement.value = '';
            hideCardImagePreview();
            return;
        }

        if (totalPixels > maxPixels) {
            showToast(`❌ 图片像素总数过大：${(totalPixels / 1024 / 1024).toFixed(1)}M像素，最大允许：8M像素`, 'warning');
            inputElement.value = '';
            hideCardImagePreview();
            return;
        }

        // 尺寸检查通过，显示预览和提示信息
        showCardImagePreview(file);

        // 如果图片较大，提示会被压缩
        if (width > 2048 || height > 2048) {
            showToast(`ℹ️ 图片尺寸较大（${width}x${height}），上传时将自动压缩以优化性能`, 'info');
        } else {
            showToast(`✅ 图片尺寸合适（${width}x${height}），可以上传`, 'success');
        }
    };

    img.onerror = function() {
        URL.revokeObjectURL(url);
        showToast('❌ 无法读取图片文件，请选择有效的图片', 'warning');
        inputElement.value = '';
        hideCardImagePreview();
    };

    img.src = url;
}

// 显示卡券图片预览
function showCardImagePreview(file) {
    const reader = new FileReader();
    reader.onload = function(e) {
        const previewContainer = document.getElementById('cardImagePreview');
        const previewImg = document.getElementById('cardPreviewImg');

        previewImg.src = e.target.result;
        previewContainer.style.display = 'block';
    };
    reader.readAsDataURL(file);
}

// 隐藏卡券图片预览
function hideCardImagePreview() {
    const previewContainer = document.getElementById('cardImagePreview');
    if (previewContainer) {
        previewContainer.style.display = 'none';
    }
}

// 初始化编辑卡券图片文件选择器
function initEditCardImageFileSelector() {
    const fileInput = document.getElementById('editCardImageFile');
    if (fileInput) {
        fileInput.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                // 验证文件类型
                if (!file.type.startsWith('image/')) {
                    showToast('❌ 请选择图片文件，当前文件类型：' + file.type, 'warning');
                    e.target.value = '';
                    hideEditCardImagePreview();
                    return;
                }

                // 验证文件大小（5MB）
                if (file.size > 5 * 1024 * 1024) {
                    showToast('❌ 图片文件大小不能超过 5MB，当前文件大小：' + (file.size / 1024 / 1024).toFixed(1) + 'MB', 'warning');
                    e.target.value = '';
                    hideEditCardImagePreview();
                    return;
                }

                // 验证图片尺寸
                validateEditCardImageDimensions(file, e.target);
            } else {
                hideEditCardImagePreview();
            }
        });
    }
}

// 验证编辑卡券图片尺寸
function validateEditCardImageDimensions(file, inputElement) {
    const img = new Image();
    const url = URL.createObjectURL(file);

    img.onload = function() {
        const width = this.naturalWidth;
        const height = this.naturalHeight;

        URL.revokeObjectURL(url);

        // 检查尺寸限制
        if (width > 4096 || height > 4096) {
            showToast(`❌ 图片尺寸过大（${width}x${height}），最大支持 4096x4096 像素`, 'warning');
            inputElement.value = '';
            hideEditCardImagePreview();
            return;
        }

        // 显示图片预览
        showEditCardImagePreview(file);

        // 如果图片较大，提示会被压缩
        if (width > 2048 || height > 2048) {
            showToast(`ℹ️ 图片尺寸较大（${width}x${height}），上传时将自动压缩以优化性能`, 'info');
        } else {
            showToast(`✅ 图片尺寸合适（${width}x${height}），可以上传`, 'success');
        }
    };

    img.onerror = function() {
        URL.revokeObjectURL(url);
        showToast('❌ 无法读取图片文件，请选择有效的图片', 'warning');
        inputElement.value = '';
        hideEditCardImagePreview();
    };

    img.src = url;
}

// 显示编辑卡券图片预览
function showEditCardImagePreview(file) {
    const reader = new FileReader();
    reader.onload = function(e) {
        const previewImg = document.getElementById('editCardPreviewImg');
        const previewContainer = document.getElementById('editCardImagePreview');

        if (previewImg && previewContainer) {
            previewImg.src = e.target.result;
            previewContainer.style.display = 'block';
        }
    };
    reader.readAsDataURL(file);
}

// 隐藏编辑卡券图片预览
function hideEditCardImagePreview() {
    const previewContainer = document.getElementById('editCardImagePreview');
    if (previewContainer) {
        previewContainer.style.display = 'none';
    }
}

// 切换编辑多规格字段显示
function toggleEditMultiSpecFields() {
    const checkbox = document.getElementById('editIsMultiSpec');
    const fieldsDiv = document.getElementById('editMultiSpecFields');

    if (!checkbox) {
    console.error('编辑多规格开关元素未找到');
    return;
    }

    if (!fieldsDiv) {
    console.error('编辑多规格字段容器未找到');
    return;
    }

    const isMultiSpec = checkbox.checked;
    const displayStyle = isMultiSpec ? 'block' : 'none';

    console.log('toggleEditMultiSpecFields - 多规格状态:', isMultiSpec);
    console.log('toggleEditMultiSpecFields - 设置显示样式:', displayStyle);

    fieldsDiv.style.display = displayStyle;

    // 验证设置是否生效
    console.log('toggleEditMultiSpecFields - 实际显示样式:', fieldsDiv.style.display);
}

// 清空添加卡券表单
function clearAddCardForm() {
    try {
    // 安全地清空表单字段
    const setElementValue = (id, value) => {
        const element = document.getElementById(id);
        if (element) {
        if (element.type === 'checkbox') {
            element.checked = value;
        } else {
            element.value = value;
        }
        } else {
        console.warn(`Element with id '${id}' not found`);
        }
    };

    const setElementDisplay = (id, display) => {
        const element = document.getElementById(id);
        if (element) {
        element.style.display = display;
        } else {
        console.warn(`Element with id '${id}' not found`);
        }
    };

    // 清空基本字段
    setElementValue('cardName', '');
    setElementValue('cardType', 'text');
    setElementValue('cardDescription', '');
    setElementValue('cardDelaySeconds', '0');
    setElementValue('isMultiSpec', false);
    setElementValue('specName', '');
    setElementValue('specValue', '');

    // 隐藏多规格字段
    setElementDisplay('multiSpecFields', 'none');

    // 清空类型相关字段
    setElementValue('textContent', '');
    setElementValue('dataContent', '');
    setElementValue('apiUrl', '');
    setElementValue('apiMethod', 'GET');
    setElementValue('apiHeaders', '');
    setElementValue('apiParams', '');
    setElementValue('apiTimeout', '10');

    // 重置字段显示
    toggleCardTypeFields();
    } catch (error) {
    console.error('清空表单时出错:', error);
    }
}

// 保存卡券
async function saveCard() {
    try {
    const cardType = document.getElementById('cardType').value;
    const cardName = document.getElementById('cardName').value;

    if (!cardType || !cardName) {
        showToast('请填写必填字段', 'warning');
        return;
    }

    // 检查多规格设置
    const isMultiSpec = document.getElementById('isMultiSpec').checked;
    const specName = document.getElementById('specName').value;
    const specValue = document.getElementById('specValue').value;

    // 验证多规格字段
    if (isMultiSpec && (!specName || !specValue)) {
        showToast('多规格卡券必须填写规格名称和规格值', 'warning');
        return;
    }

    const cardData = {
        name: cardName,
        type: cardType,
        description: document.getElementById('cardDescription').value,
        delay_seconds: parseInt(document.getElementById('cardDelaySeconds').value) || 0,
        enabled: true,
        is_multi_spec: isMultiSpec,
        spec_name: isMultiSpec ? specName : null,
        spec_value: isMultiSpec ? specValue : null
    };

    // 根据类型添加特定配置
    switch(cardType) {
        case 'api':
        // 验证和解析JSON字段
        let headers = '{}';
        let params = '{}';

        try {
            const headersInput = document.getElementById('apiHeaders').value.trim();
            if (headersInput) {
            JSON.parse(headersInput); // 验证JSON格式
            headers = headersInput;
            }
        } catch (e) {
            showToast('请求头格式错误，请输入有效的JSON', 'warning');
            return;
        }

        try {
            const paramsInput = document.getElementById('apiParams').value.trim();
            if (paramsInput) {
            JSON.parse(paramsInput); // 验证JSON格式
            params = paramsInput;
            }
        } catch (e) {
            showToast('请求参数格式错误，请输入有效的JSON', 'warning');
            return;
        }

        cardData.api_config = {
            url: document.getElementById('apiUrl').value,
            method: document.getElementById('apiMethod').value,
            timeout: parseInt(document.getElementById('apiTimeout').value),
            headers: headers,
            params: params
        };
        break;
        case 'text':
        cardData.text_content = document.getElementById('textContent').value;
        break;
        case 'data':
        cardData.data_content = document.getElementById('dataContent').value;
        break;
        case 'image':
        // 处理图片上传
        const imageFile = document.getElementById('cardImageFile').files[0];
        if (!imageFile) {
            showToast('请选择图片文件', 'warning');
            return;
        }

        // 上传图片
        const formData = new FormData();
        formData.append('image', imageFile);

        const uploadResponse = await fetch(`${apiBase}/upload-image`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`
            },
            body: formData
        });

        if (!uploadResponse.ok) {
            const errorData = await uploadResponse.json();
            showToast(`图片上传失败: ${errorData.detail || '未知错误'}`, 'danger');
            return;
        }

        const uploadResult = await uploadResponse.json();
        cardData.image_url = uploadResult.image_url;
        break;
    }

    const response = await fetch(`${apiBase}/cards`, {
        method: 'POST',
        headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
        },
        body: JSON.stringify(cardData)
    });

    if (response.ok) {
        showToast('卡券保存成功', 'success');
        bootstrap.Modal.getInstance(document.getElementById('addCardModal')).hide();
        // 清空表单
        clearAddCardForm();
        loadCards();
    } else {
        let errorMessage = '保存失败';
        try {
        const errorData = await response.json();
        errorMessage = errorData.error || errorData.detail || errorMessage;
        } catch (e) {
        // 如果不是JSON格式，尝试获取文本
        try {
            const errorText = await response.text();
            errorMessage = errorText || errorMessage;
        } catch (e2) {
            errorMessage = `HTTP ${response.status}: ${response.statusText}`;
        }
        }
        showToast(`保存失败: ${errorMessage}`, 'danger');
    }
    } catch (error) {
    console.error('保存卡券失败:', error);
    showToast(`网络错误: ${error.message}`, 'danger');
    }
}
// ================================
// 【自动发货菜单】相关功能
// ================================

// 加载发货规则列表
async function loadDeliveryRules() {
    try {
    const response = await fetch(`${apiBase}/delivery-rules`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        const rules = await response.json();
        renderDeliveryRulesList(rules);
        updateDeliveryStats(rules);

        // 同时加载卡券列表用于下拉选择
        loadCardsForSelect();
    } else {
        showToast('加载发货规则失败', 'danger');
    }
    } catch (error) {
    console.error('加载发货规则失败:', error);
    showToast('加载发货规则失败', 'danger');
    }
}

// 渲染发货规则列表
function renderDeliveryRulesList(rules) {
    const tbody = document.getElementById('deliveryRulesTableBody');

    if (rules.length === 0) {
    tbody.innerHTML = `
        <tr>
        <td colspan="7" class="text-center py-4 text-muted">
            <i class="bi bi-truck fs-1 d-block mb-3"></i>
            <h5>暂无发货规则</h5>
            <p class="mb-0">点击"添加规则"开始配置自动发货规则</p>
        </td>
        </tr>
    `;
    return;
    }

    tbody.innerHTML = '';

    rules.forEach(rule => {
    const tr = document.createElement('tr');

    // 状态标签
    const statusBadge = rule.enabled ?
        '<span class="badge bg-success">启用</span>' :
        '<span class="badge bg-secondary">禁用</span>';

    // 卡券类型标签
    let cardTypeBadge = '<span class="badge bg-secondary">未知</span>';
    if (rule.card_type) {
        switch(rule.card_type) {
        case 'api':
            cardTypeBadge = '<span class="badge bg-info">API接口</span>';
            break;
        case 'text':
            cardTypeBadge = '<span class="badge bg-success">固定文字</span>';
            break;
        case 'data':
            cardTypeBadge = '<span class="badge bg-warning">批量数据</span>';
            break;
        case 'image':
            cardTypeBadge = '<span class="badge bg-primary">图片</span>';
            break;
        }
    }

    tr.innerHTML = `
        <td>
        <div class="fw-bold">${rule.keyword}</div>
        ${rule.description ? `<small class="text-muted">${rule.description}</small>` : ''}
        </td>
        <td>
        <div>
            <span class="badge bg-primary">${rule.card_name || '未知卡券'}</span>
            ${rule.is_multi_spec && rule.spec_name && rule.spec_value ?
            `<br><small class="text-muted mt-1 d-block"><i class="bi bi-tags"></i> ${rule.spec_name}: ${rule.spec_value}</small>` :
            ''}
        </div>
        </td>
        <td>${cardTypeBadge}</td>
        <td>
        <span class="badge bg-info">${rule.delivery_count || 1}</span>
        </td>
        <td>${statusBadge}</td>
        <td>
        <span class="badge bg-warning">${rule.delivery_times || 0}</span>
        </td>
        <td>
        <div class="btn-group" role="group">
            <button class="btn btn-sm btn-outline-primary" onclick="editDeliveryRule(${rule.id})" title="编辑">
            <i class="bi bi-pencil"></i>
            </button>
            <button class="btn btn-sm btn-outline-info" onclick="testDeliveryRule(${rule.id})" title="测试">
            <i class="bi bi-play"></i>
            </button>
            <button class="btn btn-sm btn-outline-danger" onclick="deleteDeliveryRule(${rule.id})" title="删除">
            <i class="bi bi-trash"></i>
            </button>
        </div>
        </td>
    `;

    tbody.appendChild(tr);
    });
}

// 更新发货统计
function updateDeliveryStats(rules) {
    const totalRules = rules.length;
    const activeRules = rules.filter(rule => rule.enabled).length;
    const todayDeliveries = 0; // 需要从后端获取今日发货统计
    const totalDeliveries = rules.reduce((sum, rule) => sum + (rule.delivery_times || 0), 0);

    document.getElementById('totalRules').textContent = totalRules;
    document.getElementById('activeRules').textContent = activeRules;
    document.getElementById('todayDeliveries').textContent = todayDeliveries;
    document.getElementById('totalDeliveries').textContent = totalDeliveries;
}

// 显示添加发货规则模态框
function showAddDeliveryRuleModal() {
    document.getElementById('addDeliveryRuleForm').reset();
    loadCardsForSelect(); // 加载卡券选项
    const modal = new bootstrap.Modal(document.getElementById('addDeliveryRuleModal'));
    modal.show();
}

// 加载卡券列表用于下拉选择
async function loadCardsForSelect() {
    try {
    const response = await fetch(`${apiBase}/cards`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        const cards = await response.json();
        const select = document.getElementById('selectedCard');

        // 清空现有选项
        select.innerHTML = '<option value="">请选择卡券</option>';

        cards.forEach(card => {
        if (card.enabled) { // 只显示启用的卡券
            const option = document.createElement('option');
            option.value = card.id;

            // 构建显示文本
            let displayText = card.name;

            // 添加类型信息
            let typeText;
            switch(card.type) {
                case 'api':
                    typeText = 'API';
                    break;
                case 'text':
                    typeText = '固定文字';
                    break;
                case 'data':
                    typeText = '批量数据';
                    break;
                case 'image':
                    typeText = '图片';
                    break;
                default:
                    typeText = '未知类型';
            }
            displayText += ` (${typeText})`;

            // 添加规格信息
            if (card.is_multi_spec && card.spec_name && card.spec_value) {
            displayText += ` [${card.spec_name}:${card.spec_value}]`;
            }

            option.textContent = displayText;
            select.appendChild(option);
        }
        });
    }
    } catch (error) {
    console.error('加载卡券选项失败:', error);
    }
}

// 保存发货规则
async function saveDeliveryRule() {
    try {
    const keyword = document.getElementById('productKeyword').value;
    const cardId = document.getElementById('selectedCard').value;
    const deliveryCount = document.getElementById('deliveryCount').value;
    const enabled = document.getElementById('ruleEnabled').checked;
    const description = document.getElementById('ruleDescription').value;

    if (!keyword || !cardId) {
        showToast('请填写必填字段', 'warning');
        return;
    }

    const ruleData = {
        keyword: keyword,
        card_id: parseInt(cardId),
        delivery_count: parseInt(deliveryCount),
        enabled: enabled,
        description: description
    };

    const response = await fetch(`${apiBase}/delivery-rules`, {
        method: 'POST',
        headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
        },
        body: JSON.stringify(ruleData)
    });

    if (response.ok) {
        showToast('发货规则保存成功', 'success');
        bootstrap.Modal.getInstance(document.getElementById('addDeliveryRuleModal')).hide();
        loadDeliveryRules();
    } else {
        const error = await response.text();
        showToast(`保存失败: ${error}`, 'danger');
    }
    } catch (error) {
    console.error('保存发货规则失败:', error);
    showToast('保存发货规则失败', 'danger');
    }
}

// 编辑卡券
async function editCard(cardId) {
    try {
    // 获取卡券详情
    const response = await fetch(`${apiBase}/cards/${cardId}`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        const card = await response.json();

        // 填充编辑表单
        document.getElementById('editCardId').value = card.id;
        document.getElementById('editCardName').value = card.name;
        document.getElementById('editCardType').value = card.type;
        document.getElementById('editCardDescription').value = card.description || '';
        document.getElementById('editCardDelaySeconds').value = card.delay_seconds || 0;
        document.getElementById('editCardEnabled').checked = card.enabled;

        // 填充多规格字段
        const isMultiSpec = card.is_multi_spec || false;
        document.getElementById('editIsMultiSpec').checked = isMultiSpec;
        document.getElementById('editSpecName').value = card.spec_name || '';
        document.getElementById('editSpecValue').value = card.spec_value || '';

        // 添加调试日志
        console.log('编辑卡券 - 多规格状态:', isMultiSpec);
        console.log('编辑卡券 - 规格名称:', card.spec_name);
        console.log('编辑卡券 - 规格值:', card.spec_value);

        // 根据类型填充特定字段
        if (card.type === 'api' && card.api_config) {
        document.getElementById('editApiUrl').value = card.api_config.url || '';
        document.getElementById('editApiMethod').value = card.api_config.method || 'GET';
        document.getElementById('editApiTimeout').value = card.api_config.timeout || 10;
        document.getElementById('editApiHeaders').value = card.api_config.headers || '{}';
        document.getElementById('editApiParams').value = card.api_config.params || '{}';
        } else if (card.type === 'text') {
        document.getElementById('editTextContent').value = card.text_content || '';
        } else if (card.type === 'data') {
        document.getElementById('editDataContent').value = card.data_content || '';
        } else if (card.type === 'image') {
        // 处理图片类型
        const currentImagePreview = document.getElementById('editCurrentImagePreview');
        const currentImg = document.getElementById('editCurrentImg');
        const noImageText = document.getElementById('editNoImageText');

        if (card.image_url) {
            // 显示当前图片
            currentImg.src = card.image_url;
            currentImagePreview.style.display = 'block';
            noImageText.style.display = 'none';
        } else {
            // 没有图片
            currentImagePreview.style.display = 'none';
            noImageText.style.display = 'block';
        }

        // 清空文件选择器和预览
        document.getElementById('editCardImageFile').value = '';
        document.getElementById('editCardImagePreview').style.display = 'none';
        }

        // 显示对应的字段
        toggleEditCardTypeFields();

        // 使用延迟调用确保DOM更新完成后再显示多规格字段
        setTimeout(() => {
        console.log('延迟调用 toggleEditMultiSpecFields');
        toggleEditMultiSpecFields();

        // 验证多规格字段是否正确显示
        const multiSpecElement = document.getElementById('editMultiSpecFields');
        const isChecked = document.getElementById('editIsMultiSpec').checked;
        console.log('多规格元素存在:', !!multiSpecElement);
        console.log('多规格开关状态:', isChecked);
        console.log('多规格字段显示状态:', multiSpecElement ? multiSpecElement.style.display : 'element not found');
        }, 100);

        // 显示模态框
        const modal = new bootstrap.Modal(document.getElementById('editCardModal'));
        modal.show();
    } else {
        showToast('获取卡券详情失败', 'danger');
    }
    } catch (error) {
    console.error('获取卡券详情失败:', error);
    showToast('获取卡券详情失败', 'danger');
    }
}

// 切换编辑卡券类型字段显示
function toggleEditCardTypeFields() {
    const cardType = document.getElementById('editCardType').value;

    document.getElementById('editApiFields').style.display = cardType === 'api' ? 'block' : 'none';
    document.getElementById('editTextFields').style.display = cardType === 'text' ? 'block' : 'none';
    document.getElementById('editDataFields').style.display = cardType === 'data' ? 'block' : 'none';
    document.getElementById('editImageFields').style.display = cardType === 'image' ? 'block' : 'none';

    // 如果是API类型，初始化API方法监听
    if (cardType === 'api') {
        toggleEditApiParamsHelp();
        // 添加API方法变化监听
        const editApiMethodSelect = document.getElementById('editApiMethod');
        if (editApiMethodSelect) {
            editApiMethodSelect.removeEventListener('change', toggleEditApiParamsHelp);
            editApiMethodSelect.addEventListener('change', toggleEditApiParamsHelp);
        }
    }
}

// 切换编辑API参数提示显示
function toggleEditApiParamsHelp() {
    const apiMethod = document.getElementById('editApiMethod').value;
    const editPostParamsHelp = document.getElementById('editPostParamsHelp');

    if (editPostParamsHelp) {
        editPostParamsHelp.style.display = apiMethod === 'POST' ? 'block' : 'none';

        // 如果显示参数提示，添加点击事件
        if (apiMethod === 'POST') {
            initParamClickHandlers('editApiParams', 'editPostParamsHelp');
        }
    }
}

// 更新卡券
async function updateCard() {
    try {
    const cardId = document.getElementById('editCardId').value;
    const cardType = document.getElementById('editCardType').value;
    const cardName = document.getElementById('editCardName').value;

    if (!cardType || !cardName) {
        showToast('请填写必填字段', 'warning');
        return;
    }

    // 检查多规格设置
    const isMultiSpec = document.getElementById('editIsMultiSpec').checked;
    const specName = document.getElementById('editSpecName').value;
    const specValue = document.getElementById('editSpecValue').value;

    // 验证多规格字段
    if (isMultiSpec && (!specName || !specValue)) {
        showToast('多规格卡券必须填写规格名称和规格值', 'warning');
        return;
    }

    const cardData = {
        name: cardName,
        type: cardType,
        description: document.getElementById('editCardDescription').value,
        delay_seconds: parseInt(document.getElementById('editCardDelaySeconds').value) || 0,
        enabled: document.getElementById('editCardEnabled').checked,
        is_multi_spec: isMultiSpec,
        spec_name: isMultiSpec ? specName : null,
        spec_value: isMultiSpec ? specValue : null
    };

    // 根据类型添加特定配置
    switch(cardType) {
        case 'api':
        // 验证和解析JSON字段
        let headers = '{}';
        let params = '{}';

        try {
            const headersInput = document.getElementById('editApiHeaders').value.trim();
            if (headersInput) {
            JSON.parse(headersInput);
            headers = headersInput;
            }
        } catch (e) {
            showToast('请求头格式错误，请输入有效的JSON', 'warning');
            return;
        }

        try {
            const paramsInput = document.getElementById('editApiParams').value.trim();
            if (paramsInput) {
            JSON.parse(paramsInput);
            params = paramsInput;
            }
        } catch (e) {
            showToast('请求参数格式错误，请输入有效的JSON', 'warning');
            return;
        }

        cardData.api_config = {
            url: document.getElementById('editApiUrl').value,
            method: document.getElementById('editApiMethod').value,
            timeout: parseInt(document.getElementById('editApiTimeout').value),
            headers: headers,
            params: params
        };
        break;
        case 'text':
        cardData.text_content = document.getElementById('editTextContent').value;
        break;
        case 'data':
        cardData.data_content = document.getElementById('editDataContent').value;
        break;
        case 'image':
        // 处理图片类型 - 如果有新图片则上传，否则保持原有图片
        const imageFile = document.getElementById('editCardImageFile').files[0];
        if (imageFile) {
            // 有新图片，需要上传
            await updateCardWithImage(cardId, cardData, imageFile);
            return; // 提前返回，因为上传图片是异步的
        }
        // 没有新图片，保持原有配置，继续正常更新流程
        break;
    }

    const response = await fetch(`${apiBase}/cards/${cardId}`, {
        method: 'PUT',
        headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
        },
        body: JSON.stringify(cardData)
    });

    if (response.ok) {
        showToast('卡券更新成功', 'success');
        bootstrap.Modal.getInstance(document.getElementById('editCardModal')).hide();
        loadCards();
    } else {
        const error = await response.text();
        showToast(`更新失败: ${error}`, 'danger');
    }
    } catch (error) {
    console.error('更新卡券失败:', error);
    showToast('更新卡券失败', 'danger');
    }
}

// 更新带图片的卡券
async function updateCardWithImage(cardId, cardData, imageFile) {
    try {
        // 创建FormData对象
        const formData = new FormData();

        // 添加图片文件
        formData.append('image', imageFile);

        // 添加卡券数据
        Object.keys(cardData).forEach(key => {
            if (cardData[key] !== null && cardData[key] !== undefined) {
                if (typeof cardData[key] === 'object') {
                    formData.append(key, JSON.stringify(cardData[key]));
                } else {
                    formData.append(key, cardData[key]);
                }
            }
        });

        const response = await fetch(`${apiBase}/cards/${cardId}/image`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${authToken}`
                // 不设置Content-Type，让浏览器自动设置multipart/form-data
            },
            body: formData
        });

        if (response.ok) {
            showToast('卡券更新成功', 'success');
            bootstrap.Modal.getInstance(document.getElementById('editCardModal')).hide();
            loadCards();
        } else {
            const error = await response.text();
            showToast(`更新失败: ${error}`, 'danger');
        }
    } catch (error) {
        console.error('更新带图片的卡券失败:', error);
        showToast('更新卡券失败', 'danger');
    }
}



// 测试卡券（占位函数）
function testCard(cardId) {
    showToast('测试功能开发中...', 'info');
}

// 删除卡券
async function deleteCard(cardId) {
    if (confirm('确定要删除这个卡券吗？删除后无法恢复！')) {
    try {
        const response = await fetch(`${apiBase}/cards/${cardId}`, {
        method: 'DELETE',
        headers: {
            'Authorization': `Bearer ${authToken}`
        }
        });

        if (response.ok) {
        showToast('卡券删除成功', 'success');
        loadCards();
        } else {
        const error = await response.text();
        showToast(`删除失败: ${error}`, 'danger');
        }
    } catch (error) {
        console.error('删除卡券失败:', error);
        showToast('删除卡券失败', 'danger');
    }
    }
}

// 编辑发货规则
async function editDeliveryRule(ruleId) {
    try {
    // 获取发货规则详情
    const response = await fetch(`${apiBase}/delivery-rules/${ruleId}`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        const rule = await response.json();

        // 填充编辑表单
        document.getElementById('editRuleId').value = rule.id;
        document.getElementById('editProductKeyword').value = rule.keyword;
        document.getElementById('editDeliveryCount').value = rule.delivery_count || 1;
        document.getElementById('editRuleEnabled').checked = rule.enabled;
        document.getElementById('editRuleDescription').value = rule.description || '';

        // 加载卡券选项并设置当前选中的卡券
        await loadCardsForEditSelect();
        document.getElementById('editSelectedCard').value = rule.card_id;

        // 显示模态框
        const modal = new bootstrap.Modal(document.getElementById('editDeliveryRuleModal'));
        modal.show();
    } else {
        showToast('获取发货规则详情失败', 'danger');
    }
    } catch (error) {
    console.error('获取发货规则详情失败:', error);
    showToast('获取发货规则详情失败', 'danger');
    }
}

// 加载卡券列表用于编辑时的下拉选择
async function loadCardsForEditSelect() {
    try {
    const response = await fetch(`${apiBase}/cards`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        const cards = await response.json();
        const select = document.getElementById('editSelectedCard');

        // 清空现有选项
        select.innerHTML = '<option value="">请选择卡券</option>';

        cards.forEach(card => {
        if (card.enabled) { // 只显示启用的卡券
            const option = document.createElement('option');
            option.value = card.id;

            // 构建显示文本
            let displayText = card.name;

            // 添加类型信息
            let typeText;
            switch(card.type) {
                case 'api':
                    typeText = 'API';
                    break;
                case 'text':
                    typeText = '固定文字';
                    break;
                case 'data':
                    typeText = '批量数据';
                    break;
                case 'image':
                    typeText = '图片';
                    break;
                default:
                    typeText = '未知类型';
            }
            displayText += ` (${typeText})`;

            // 添加规格信息
            if (card.is_multi_spec && card.spec_name && card.spec_value) {
            displayText += ` [${card.spec_name}:${card.spec_value}]`;
            }

            option.textContent = displayText;
            select.appendChild(option);
        }
        });
    }
    } catch (error) {
    console.error('加载卡券选项失败:', error);
    }
}

// 更新发货规则
async function updateDeliveryRule() {
    try {
    const ruleId = document.getElementById('editRuleId').value;
    const keyword = document.getElementById('editProductKeyword').value;
    const cardId = document.getElementById('editSelectedCard').value;
    const deliveryCount = document.getElementById('editDeliveryCount').value;
    const enabled = document.getElementById('editRuleEnabled').checked;
    const description = document.getElementById('editRuleDescription').value;

    if (!keyword || !cardId) {
        showToast('请填写必填字段', 'warning');
        return;
    }

    const ruleData = {
        keyword: keyword,
        card_id: parseInt(cardId),
        delivery_count: parseInt(deliveryCount),
        enabled: enabled,
        description: description
    };

    const response = await fetch(`${apiBase}/delivery-rules/${ruleId}`, {
        method: 'PUT',
        headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
        },
        body: JSON.stringify(ruleData)
    });

    if (response.ok) {
        showToast('发货规则更新成功', 'success');
        bootstrap.Modal.getInstance(document.getElementById('editDeliveryRuleModal')).hide();
        loadDeliveryRules();
    } else {
        const error = await response.text();
        showToast(`更新失败: ${error}`, 'danger');
    }
    } catch (error) {
    console.error('更新发货规则失败:', error);
    showToast('更新发货规则失败', 'danger');
    }
}

// 测试发货规则（占位函数）
function testDeliveryRule(ruleId) {
    showToast('测试功能开发中...', 'info');
}

// 删除发货规则
async function deleteDeliveryRule(ruleId) {
    if (confirm('确定要删除这个发货规则吗？删除后无法恢复！')) {
    try {
        const response = await fetch(`${apiBase}/delivery-rules/${ruleId}`, {
        method: 'DELETE',
        headers: {
            'Authorization': `Bearer ${authToken}`
        }
        });

        if (response.ok) {
        showToast('发货规则删除成功', 'success');
        loadDeliveryRules();
        } else {
        const error = await response.text();
        showToast(`删除失败: ${error}`, 'danger');
        }
    } catch (error) {
        console.error('删除发货规则失败:', error);
        showToast('删除发货规则失败', 'danger');
    }
    }
}



// ==================== 系统设置功能 ====================

// 主题颜色映射
const themeColors = {
    blue: '#4f46e5',
    green: '#10b981',
    purple: '#8b5cf6',
    red: '#ef4444',
    orange: '#f59e0b'
};

// 加载用户设置
async function loadUserSettings() {
    try {
    const response = await fetch(`${apiBase}/user-settings`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        const settings = await response.json();

        // 设置主题颜色
        if (settings.theme_color && settings.theme_color.value) {
        document.getElementById('themeColor').value = settings.theme_color.value;
        applyThemeColor(settings.theme_color.value);
        }
    }
    } catch (error) {
    console.error('加载用户设置失败:', error);
    }
}

// 应用主题颜色
function applyThemeColor(colorName) {
    const color = themeColors[colorName];
    if (color) {
    document.documentElement.style.setProperty('--primary-color', color);

    // 计算hover颜色（稍微深一点）
    const hoverColor = adjustBrightness(color, -20);
    document.documentElement.style.setProperty('--primary-hover', hoverColor);

    // 计算浅色版本（用于某些UI元素）
    const lightColor = adjustBrightness(color, 10);
    document.documentElement.style.setProperty('--primary-light', lightColor);
    }
}

// 调整颜色亮度
function adjustBrightness(hex, percent) {
    const num = parseInt(hex.replace("#", ""), 16);
    const amt = Math.round(2.55 * percent);
    const R = (num >> 16) + amt;
    const G = (num >> 8 & 0x00FF) + amt;
    const B = (num & 0x0000FF) + amt;
    return "#" + (0x1000000 + (R < 255 ? R < 1 ? 0 : R : 255) * 0x10000 +
    (G < 255 ? G < 1 ? 0 : G : 255) * 0x100 +
    (B < 255 ? B < 1 ? 0 : B : 255)).toString(16).slice(1);
}

// 主题表单提交处理
document.addEventListener('DOMContentLoaded', function() {
    const themeForm = document.getElementById('themeForm');
    if (themeForm) {
    themeForm.addEventListener('submit', async function(e) {
        e.preventDefault();

        const selectedColor = document.getElementById('themeColor').value;

        try {
        const response = await fetch(`${apiBase}/user-settings/theme_color`, {
            method: 'PUT',
            headers: {
            'Authorization': `Bearer ${authToken}`,
            'Content-Type': 'application/json'
            },
            body: JSON.stringify({
            value: selectedColor,
            description: '主题颜色'
            })
        });

        if (response.ok) {
            applyThemeColor(selectedColor);
            showToast('主题颜色应用成功', 'success');
        } else {
            const error = await response.text();
            showToast(`主题设置失败: ${error}`, 'danger');
        }
        } catch (error) {
        console.error('主题设置失败:', error);
        showToast('主题设置失败', 'danger');
        }
    });
    }

    // 密码表单提交处理
    const passwordForm = document.getElementById('passwordForm');
    if (passwordForm) {
    passwordForm.addEventListener('submit', async function(e) {
        e.preventDefault();

        const currentPassword = document.getElementById('currentPassword').value;
        const newPassword = document.getElementById('newPassword').value;
        const confirmPassword = document.getElementById('confirmPassword').value;

        if (newPassword !== confirmPassword) {
        showToast('新密码和确认密码不匹配', 'warning');
        return;
        }

        if (newPassword.length < 6) {
        showToast('新密码长度至少6位', 'warning');
        return;
        }

        try {
        const response = await fetch(`${apiBase}/change-admin-password`, {
            method: 'POST',
            headers: {
            'Authorization': `Bearer ${authToken}`,
            'Content-Type': 'application/json'
            },
            body: JSON.stringify({
            current_password: currentPassword,
            new_password: newPassword
            })
        });

        if (response.ok) {
            const result = await response.json();
            if (result.success) {
            showToast('密码更新成功，请重新登录', 'success');
            passwordForm.reset();
            // 3秒后跳转到登录页面
            setTimeout(() => {
                localStorage.removeItem('auth_token');
                window.location.href = '/login.html';
            }, 3000);
            } else {
            showToast(`密码更新失败: ${result.message}`, 'danger');
            }
        } else {
            const error = await response.text();
            showToast(`密码更新失败: ${error}`, 'danger');
        }
        } catch (error) {
        console.error('密码更新失败:', error);
        showToast('密码更新失败', 'danger');
        }
    });
    }

    // 页面加载时加载用户设置
    loadUserSettings();
});

// ==================== 备份管理功能 ====================

// 下载数据库备份
async function downloadDatabaseBackup() {
    try {
    showToast('正在准备数据库备份，请稍候...', 'info');

    const response = await fetch(`${apiBase}/admin/backup/download`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        // 获取文件名
        const contentDisposition = response.headers.get('content-disposition');
        let filename = 'xianyu_backup.db';
        if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename="(.+)"/);
        if (filenameMatch) {
            filename = filenameMatch[1];
        }
        }

        // 下载文件
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

        showToast('数据库备份下载成功', 'success');
    } else {
        const error = await response.text();
        showToast(`下载失败: ${error}`, 'danger');
    }
    } catch (error) {
    console.error('下载数据库备份失败:', error);
    showToast('下载数据库备份失败', 'danger');
    }
}

// 上传数据库备份
async function uploadDatabaseBackup() {
    const fileInput = document.getElementById('databaseFile');
    const file = fileInput.files[0];

    if (!file) {
    showToast('请选择数据库文件', 'warning');
    return;
    }

    if (!file.name.endsWith('.db')) {
    showToast('只支持.db格式的数据库文件', 'warning');
    return;
    }

    // 文件大小检查（限制100MB）
    if (file.size > 100 * 1024 * 1024) {
    showToast('数据库文件大小不能超过100MB', 'warning');
    return;
    }

    if (!confirm('恢复数据库将完全替换当前所有数据，包括所有用户、Cookie、卡券等信息。\n\n此操作不可撤销！\n\n确定要继续吗？')) {
    return;
    }

    try {
    showToast('正在上传并恢复数据库，请稍候...', 'info');

    const formData = new FormData();
    formData.append('backup_file', file);

    const response = await fetch(`${apiBase}/admin/backup/upload`, {
        method: 'POST',
        headers: {
        'Authorization': `Bearer ${authToken}`
        },
        body: formData
    });

    if (response.ok) {
        const result = await response.json();
        showToast(`数据库恢复成功！包含 ${result.user_count} 个用户`, 'success');

        // 清空文件选择
        fileInput.value = '';

        // 提示用户刷新页面
        setTimeout(() => {
        if (confirm('数据库已恢复，建议刷新页面以加载新数据。是否立即刷新？')) {
            window.location.reload();
        }
        }, 2000);

    } else {
        const error = await response.json();
        showToast(`恢复失败: ${error.detail}`, 'danger');
    }
    } catch (error) {
    console.error('上传数据库备份失败:', error);
    showToast('上传数据库备份失败', 'danger');
    }
}

// 导出备份（JSON格式，兼容旧版本）
async function exportBackup() {
    try {
    showToast('正在导出备份，请稍候...', 'info');

    const response = await fetch(`${apiBase}/backup/export`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        const backupData = await response.json();

        // 生成文件名
        const now = new Date();
        const timestamp = now.getFullYear() +
                        String(now.getMonth() + 1).padStart(2, '0') +
                        String(now.getDate()).padStart(2, '0') + '_' +
                        String(now.getHours()).padStart(2, '0') +
                        String(now.getMinutes()).padStart(2, '0') +
                        String(now.getSeconds()).padStart(2, '0');
        const filename = `xianyu_backup_${timestamp}.json`;

        // 创建下载链接
        const blob = new Blob([JSON.stringify(backupData, null, 2)], { type: 'application/json' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

        showToast('备份导出成功', 'success');
    } else {
        const error = await response.text();
        showToast(`导出失败: ${error}`, 'danger');
    }
    } catch (error) {
    console.error('导出备份失败:', error);
    showToast('导出备份失败', 'danger');
    }
}

// 导入备份
async function importBackup() {
    const fileInput = document.getElementById('backupFile');
    const file = fileInput.files[0];

    if (!file) {
    showToast('请选择备份文件', 'warning');
    return;
    }

    if (!file.name.endsWith('.json')) {
    showToast('只支持JSON格式的备份文件', 'warning');
    return;
    }

    if (!confirm('导入备份将覆盖当前所有数据，确定要继续吗？')) {
    return;
    }

    try {
    showToast('正在导入备份，请稍候...', 'info');

    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${apiBase}/backup/import`, {
        method: 'POST',
        headers: {
        'Authorization': `Bearer ${authToken}`
        },
        body: formData
    });

    if (response.ok) {
        showToast('备份导入成功！正在刷新数据...', 'success');

        // 清空文件选择
        fileInput.value = '';

        // 清除前端缓存
        clearKeywordCache();

        // 延迟一下再刷新数据，确保后端缓存已更新
        setTimeout(async () => {
        try {
            // 如果当前在关键字管理页面，重新加载数据
            if (currentCookieId) {
            await loadAccountKeywords();
            }

            // 刷新仪表盘数据
            if (document.getElementById('dashboard-section').classList.contains('active')) {
            await loadDashboard();
            }

            // 刷新账号列表
            if (document.getElementById('accounts-section').classList.contains('active')) {
            await loadCookies();
            }

            showToast('数据刷新完成！', 'success');
        } catch (error) {
            console.error('刷新数据失败:', error);
            showToast('备份导入成功，但数据刷新失败，请手动刷新页面', 'warning');
        }
        }, 1000);
    } else {
        const error = await response.text();
        showToast(`导入失败: ${error}`, 'danger');
    }
    } catch (error) {
    console.error('导入备份失败:', error);
    showToast('导入备份失败', 'danger');
    }
}

// 刷新系统缓存
async function reloadSystemCache() {
    try {
    showToast('正在刷新系统缓存...', 'info');

    const response = await fetch(`${apiBase}/system/reload-cache`, {
        method: 'POST',
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        const result = await response.json();
        showToast('系统缓存刷新成功！关键字等数据已更新', 'success');

        // 清除前端缓存
        clearKeywordCache();

        // 如果当前在关键字管理页面，重新加载数据
        if (currentCookieId) {
        setTimeout(() => {
            loadAccountKeywords();
        }, 500);
        }
    } else {
        const error = await response.text();
        showToast(`刷新缓存失败: ${error}`, 'danger');
    }
    } catch (error) {
    console.error('刷新系统缓存失败:', error);
    showToast('刷新系统缓存失败', 'danger');
    }
}

// ================================
// 【商品管理菜单】相关功能
// ================================

// 切换商品多规格状态
async function toggleItemMultiSpec(cookieId, itemId, isMultiSpec) {
    try {
    const response = await fetch(`${apiBase}/items/${encodeURIComponent(cookieId)}/${encodeURIComponent(itemId)}/multi-spec`, {
        method: 'PUT',
        headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
        },
        body: JSON.stringify({
        is_multi_spec: isMultiSpec
        })
    });

    if (response.ok) {
        showToast(`${isMultiSpec ? '开启' : '关闭'}多规格成功`, 'success');
        // 刷新商品列表
        await refreshItemsData();
    } else {
        const errorData = await response.json();
        throw new Error(errorData.error || '操作失败');
    }
    } catch (error) {
    console.error('切换多规格状态失败:', error);
    showToast(`切换多规格状态失败: ${error.message}`, 'danger');
    }
}

// 切换商品多数量发货状态
async function toggleItemMultiQuantityDelivery(cookieId, itemId, multiQuantityDelivery) {
    try {
    const response = await fetch(`${apiBase}/items/${encodeURIComponent(cookieId)}/${encodeURIComponent(itemId)}/multi-quantity-delivery`, {
        method: 'PUT',
        headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
        },
        body: JSON.stringify({
        multi_quantity_delivery: multiQuantityDelivery
        })
    });

    if (response.ok) {
        showToast(`${multiQuantityDelivery ? '开启' : '关闭'}多数量发货成功`, 'success');
        // 刷新商品列表
        await refreshItemsData();
    } else {
        const errorData = await response.json();
        throw new Error(errorData.error || '操作失败');
    }
    } catch (error) {
    console.error('切换多数量发货状态失败:', error);
    showToast(`切换多数量发货状态失败: ${error.message}`, 'danger');
    }
}

// 加载商品列表
async function loadItems() {
    try {
    // 先加载Cookie列表用于筛选
    await loadCookieFilter('itemCookieFilter');

    // 加载商品列表
    await refreshItemsData();
    } catch (error) {
    console.error('加载商品列表失败:', error);
    showToast('加载商品列表失败', 'danger');
    }
}

// 只刷新商品数据，不重新加载筛选器
async function refreshItemsData() {
    try {
    const selectedCookie = document.getElementById('itemCookieFilter').value;
    if (selectedCookie) {
        await loadItemsByCookie();
    } else {
        await loadAllItems();
    }
    } catch (error) {
    console.error('刷新商品数据失败:', error);
    showToast('刷新商品数据失败', 'danger');
    }
}

// 加载Cookie筛选选项
async function loadCookieFilter(id) {
    try {
    const response = await fetch(`${apiBase}/cookies/details`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        const accounts = await response.json();
        const select = document.getElementById(id);

        // 保存当前选择的值
        const currentValue = select.value;

        // 清空现有选项（保留"所有账号"）
        select.innerHTML = '<option value="">所有账号</option>';

        if (accounts.length === 0) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = '❌ 暂无账号';
        option.disabled = true;
        select.appendChild(option);
        return;
        }

        // 分组显示：先显示启用的账号，再显示禁用的账号
        const enabledAccounts = accounts.filter(account => {
        const enabled = account.enabled === undefined ? true : account.enabled;
        return enabled;
        });
        const disabledAccounts = accounts.filter(account => {
        const enabled = account.enabled === undefined ? true : account.enabled;
        return !enabled;
        });

        // 添加启用的账号
        enabledAccounts.forEach(account => {
        const option = document.createElement('option');
        option.value = account.id;
        option.textContent = `🟢 ${account.id}`;
        select.appendChild(option);
        });

        // 添加禁用的账号
        if (disabledAccounts.length > 0) {
        // 添加分隔线
        if (enabledAccounts.length > 0) {
            const separator = document.createElement('option');
            separator.value = '';
            separator.textContent = '────────────────';
            separator.disabled = true;
            select.appendChild(separator);
        }

        disabledAccounts.forEach(account => {
            const option = document.createElement('option');
            option.value = account.id;
            option.textContent = `🔴 ${account.id} (已禁用)`;
            select.appendChild(option);
        });
        }

        // 恢复之前选择的值
        if (currentValue) {
        select.value = currentValue;
        }
    }
    } catch (error) {
    console.error('加载Cookie列表失败:', error);
    showToast('加载账号列表失败', 'danger');
    }
}

// 加载所有商品
async function loadAllItems() {
    try {
    const response = await fetch(`${apiBase}/items`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        const data = await response.json();
        displayItems(data.items);
    } else {
        throw new Error('获取商品列表失败');
    }
    } catch (error) {
    console.error('加载商品列表失败:', error);
    showToast('加载商品列表失败', 'danger');
    }
}

// 按Cookie加载商品
async function loadItemsByCookie() {
    const cookieId = document.getElementById('itemCookieFilter').value;

    if (!cookieId) {
    await loadAllItems();
    return;
    }

    try {
    const response = await fetch(`${apiBase}/items/cookie/${encodeURIComponent(cookieId)}`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        const data = await response.json();
        displayItems(data.items);
    } else {
        throw new Error('获取商品列表失败');
    }
    } catch (error) {
    console.error('加载商品列表失败:', error);
    showToast('加载商品列表失败', 'danger');
    }
}

// 显示商品列表
function displayItems(items) {
    // 存储所有商品数据
    allItemsData = items || [];

    // 应用搜索过滤
    applyItemsFilter();

    // 显示当前页数据
    displayCurrentPageItems();

    // 更新分页控件
    updateItemsPagination();
}

// 应用搜索过滤
function applyItemsFilter() {
    const searchKeyword = currentSearchKeyword.toLowerCase().trim();

    if (!searchKeyword) {
        filteredItemsData = [...allItemsData];
    } else {
        filteredItemsData = allItemsData.filter(item => {
            const title = (item.item_title || '').toLowerCase();
            const detail = getItemDetailText(item.item_detail || '').toLowerCase();
            return title.includes(searchKeyword) || detail.includes(searchKeyword);
        });
    }

    // 重置到第一页
    currentItemsPage = 1;

    // 计算总页数
    totalItemsPages = Math.ceil(filteredItemsData.length / itemsPerPage);

    // 更新搜索统计
    updateItemsSearchStats();
}

// 获取商品详情的纯文本内容
function getItemDetailText(itemDetail) {
    if (!itemDetail) return '';

    try {
        // 尝试解析JSON
        const detail = JSON.parse(itemDetail);
        if (detail.content) {
            return detail.content;
        }
        return itemDetail;
    } catch (e) {
        // 如果不是JSON格式，直接返回原文本
        return itemDetail;
    }
}

// 显示当前页的商品数据
function displayCurrentPageItems() {
    const tbody = document.getElementById('itemsTableBody');

    if (!filteredItemsData || filteredItemsData.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted">暂无商品数据</td></tr>';
        resetItemsSelection();
        return;
    }

    // 计算当前页的数据范围
    const startIndex = (currentItemsPage - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;
    const currentPageItems = filteredItemsData.slice(startIndex, endIndex);

    const itemsHtml = currentPageItems.map(item => {
        // 处理商品标题显示
        let itemTitleDisplay = item.item_title || '未设置';
        if (itemTitleDisplay.length > 30) {
            itemTitleDisplay = itemTitleDisplay.substring(0, 30) + '...';
        }

        // 处理商品详情显示
        let itemDetailDisplay = '未设置';
        if (item.item_detail) {
            const detailText = getItemDetailText(item.item_detail);
            itemDetailDisplay = detailText.substring(0, 50) + (detailText.length > 50 ? '...' : '');
        }

        // 多规格状态显示
        const isMultiSpec = item.is_multi_spec;
        const multiSpecDisplay = isMultiSpec ?
            '<span class="badge bg-success">多规格</span>' :
            '<span class="badge bg-secondary">普通</span>';

        // 多数量发货状态显示
        const isMultiQuantityDelivery = item.multi_quantity_delivery;
        const multiQuantityDeliveryDisplay = isMultiQuantityDelivery ?
            '<span class="badge bg-success">已开启</span>' :
            '<span class="badge bg-secondary">已关闭</span>';

        return `
            <tr>
            <td>
                <input type="checkbox" name="itemCheckbox"
                        data-cookie-id="${escapeHtml(item.cookie_id)}"
                        data-item-id="${escapeHtml(item.item_id)}"
                        onchange="updateSelectAllState()">
            </td>
            <td>${escapeHtml(item.cookie_id)}</td>
            <td>${escapeHtml(item.item_id)}</td>
            <td title="${escapeHtml(item.item_title || '未设置')}">${escapeHtml(itemTitleDisplay)}</td>
            <td title="${escapeHtml(getItemDetailText(item.item_detail || ''))}">${escapeHtml(itemDetailDisplay)}</td>
            <td>${escapeHtml(item.item_price || '未设置')}</td>
            <td>${multiSpecDisplay}</td>
            <td>${multiQuantityDeliveryDisplay}</td>
            <td>${formatDateTime(item.updated_at)}</td>
            <td>
                <div class="btn-group" role="group">
                <button class="btn btn-sm btn-outline-primary" onclick="editItem('${escapeHtml(item.cookie_id)}', '${escapeHtml(item.item_id)}')" title="编辑详情">
                    <i class="bi bi-pencil"></i>
                </button>
                <button class="btn btn-sm btn-outline-danger" onclick="deleteItem('${escapeHtml(item.cookie_id)}', '${escapeHtml(item.item_id)}', '${escapeHtml(item.item_title || item.item_id)}')" title="删除">
                    <i class="bi bi-trash"></i>
                </button>
                <button class="btn btn-sm ${isMultiSpec ? 'btn-warning' : 'btn-success'}" onclick="toggleItemMultiSpec('${escapeHtml(item.cookie_id)}', '${escapeHtml(item.item_id)}', ${!isMultiSpec})" title="${isMultiSpec ? '关闭多规格' : '开启多规格'}">
                    <i class="bi ${isMultiSpec ? 'bi-toggle-on' : 'bi-toggle-off'}"></i>
                </button>
                <button class="btn btn-sm ${isMultiQuantityDelivery ? 'btn-warning' : 'btn-success'}" onclick="toggleItemMultiQuantityDelivery('${escapeHtml(item.cookie_id)}', '${escapeHtml(item.item_id)}', ${!isMultiQuantityDelivery})" title="${isMultiQuantityDelivery ? '关闭多数量发货' : '开启多数量发货'}">
                    <i class="bi ${isMultiQuantityDelivery ? 'bi-box-arrow-down' : 'bi-box-arrow-up'}"></i>
                </button>
                </div>
            </td>
            </tr>
        `;
    }).join('');

    // 更新表格内容
    tbody.innerHTML = itemsHtml;

    // 重置选择状态
    resetItemsSelection();
}

// 重置商品选择状态
function resetItemsSelection() {
    const selectAllCheckbox = document.getElementById('selectAllItems');
    if (selectAllCheckbox) {
        selectAllCheckbox.checked = false;
        selectAllCheckbox.indeterminate = false;
    }
    updateBatchDeleteButton();
}

// 商品搜索过滤函数
function filterItems() {
    const searchInput = document.getElementById('itemSearchInput');
    currentSearchKeyword = searchInput ? searchInput.value : '';

    // 应用过滤
    applyItemsFilter();

    // 显示当前页数据
    displayCurrentPageItems();

    // 更新分页控件
    updateItemsPagination();
}

// 更新搜索统计信息
function updateItemsSearchStats() {
    const statsElement = document.getElementById('itemSearchStats');
    const statsTextElement = document.getElementById('itemSearchStatsText');

    if (!statsElement || !statsTextElement) return;

    if (currentSearchKeyword) {
        statsTextElement.textContent = `搜索"${currentSearchKeyword}"，找到 ${filteredItemsData.length} 个商品`;
        statsElement.style.display = 'block';
    } else {
        statsElement.style.display = 'none';
    }
}

// 更新分页控件
function updateItemsPagination() {
    const paginationElement = document.getElementById('itemsPagination');
    const pageInfoElement = document.getElementById('itemsPageInfo');
    const totalPagesElement = document.getElementById('itemsTotalPages');
    const pageInputElement = document.getElementById('itemsPageInput');

    if (!paginationElement) return;

    // 分页控件总是显示
    paginationElement.style.display = 'block';

    // 更新页面信息
    const startIndex = (currentItemsPage - 1) * itemsPerPage + 1;
    const endIndex = Math.min(currentItemsPage * itemsPerPage, filteredItemsData.length);

    if (pageInfoElement) {
        pageInfoElement.textContent = `显示第 ${startIndex}-${endIndex} 条，共 ${filteredItemsData.length} 条记录`;
    }

    if (totalPagesElement) {
        totalPagesElement.textContent = totalItemsPages;
    }

    if (pageInputElement) {
        pageInputElement.value = currentItemsPage;
        pageInputElement.max = totalItemsPages;
    }

    // 更新分页按钮状态
    updateItemsPaginationButtons();
}

// 更新分页按钮状态
function updateItemsPaginationButtons() {
    const firstPageBtn = document.getElementById('itemsFirstPage');
    const prevPageBtn = document.getElementById('itemsPrevPage');
    const nextPageBtn = document.getElementById('itemsNextPage');
    const lastPageBtn = document.getElementById('itemsLastPage');

    if (firstPageBtn) firstPageBtn.disabled = currentItemsPage <= 1;
    if (prevPageBtn) prevPageBtn.disabled = currentItemsPage <= 1;
    if (nextPageBtn) nextPageBtn.disabled = currentItemsPage >= totalItemsPages;
    if (lastPageBtn) lastPageBtn.disabled = currentItemsPage >= totalItemsPages;
}

// 跳转到指定页面
function goToItemsPage(page) {
    if (page < 1 || page > totalItemsPages) return;

    currentItemsPage = page;
    displayCurrentPageItems();
    updateItemsPagination();
}

// 处理页面输入框的回车事件
function handleItemsPageInput(event) {
    if (event.key === 'Enter') {
        const pageInput = event.target;
        const page = parseInt(pageInput.value);

        if (page >= 1 && page <= totalItemsPages) {
            goToItemsPage(page);
        } else {
            pageInput.value = currentItemsPage;
        }
    }
}

// 改变每页显示数量
function changeItemsPageSize() {
    const pageSizeSelect = document.getElementById('itemsPageSize');
    if (!pageSizeSelect) return;

    itemsPerPage = parseInt(pageSizeSelect.value);

    // 重新计算总页数
    totalItemsPages = Math.ceil(filteredItemsData.length / itemsPerPage);

    // 调整当前页码，确保不超出范围
    if (currentItemsPage > totalItemsPages) {
        currentItemsPage = Math.max(1, totalItemsPages);
    }

    // 重新显示数据
    displayCurrentPageItems();
    updateItemsPagination();
}

// 初始化商品搜索功能
function initItemsSearch() {
    // 初始化分页大小
    const pageSizeSelect = document.getElementById('itemsPageSize');
    if (pageSizeSelect) {
        itemsPerPage = parseInt(pageSizeSelect.value) || 20;
        pageSizeSelect.addEventListener('change', changeItemsPageSize);
    }

    // 初始化搜索输入框事件监听器
    const searchInput = document.getElementById('itemSearchInput');
    if (searchInput) {
        // 使用防抖来避免频繁搜索
        let searchTimeout;
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                filterItems();
            }, 300); // 300ms 防抖延迟
        });
    }

    // 初始化页面输入框事件监听器
    const pageInput = document.getElementById('itemsPageInput');
    if (pageInput) {
        pageInput.addEventListener('keydown', handleItemsPageInput);
    }
}

// 刷新商品列表
async function refreshItems() {
    await refreshItemsData();
    showToast('商品列表已刷新', 'success');
}

// 获取商品信息
async function getAllItemsFromAccount() {
    const cookieSelect = document.getElementById('itemCookieFilter');
    const selectedCookieId = cookieSelect.value;
    const pageNumber = parseInt(document.getElementById('pageNumber').value) || 1;

    if (!selectedCookieId) {
    showToast('请先选择一个账号', 'warning');
    return;
    }

    if (pageNumber < 1) {
    showToast('页码必须大于0', 'warning');
    return;
    }

    // 显示加载状态
    const button = event.target;
    const originalText = button.innerHTML;
    button.innerHTML = '<i class="bi bi-hourglass-split me-1"></i>获取中...';
    button.disabled = true;

    try {
    const response = await fetch(`${apiBase}/items/get-by-page`, {
        method: 'POST',
        headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
        },
        body: JSON.stringify({
        cookie_id: selectedCookieId,
        page_number: pageNumber,
        page_size: 20
        })
    });

    if (response.ok) {
        const data = await response.json();
        if (data.success) {
        showToast(`成功获取第${pageNumber}页 ${data.current_count} 个商品，请查看控制台日志`, 'success');
        // 刷新商品列表（保持筛选器选择）
        await refreshItemsData();
        } else {
        showToast(data.message || '获取商品信息失败', 'danger');
        }
    } else {
        throw new Error(`HTTP ${response.status}`);
    }
    } catch (error) {
    console.error('获取商品信息失败:', error);
    showToast('获取商品信息失败', 'danger');
    } finally {
    // 恢复按钮状态
    button.innerHTML = originalText;
    button.disabled = false;
    }
}

// 获取所有页商品信息
async function getAllItemsFromAccountAll() {
    const cookieSelect = document.getElementById('itemCookieFilter');
    const selectedCookieId = cookieSelect.value;

    if (!selectedCookieId) {
    showToast('请先选择一个账号', 'warning');
    return;
    }

    // 显示加载状态
    const button = event.target;
    const originalText = button.innerHTML;
    button.innerHTML = '<i class="bi bi-hourglass-split me-1"></i>获取中...';
    button.disabled = true;

    try {
    const response = await fetch(`${apiBase}/items/get-all-from-account`, {
        method: 'POST',
        headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
        },
        body: JSON.stringify({
        cookie_id: selectedCookieId
        })
    });

    if (response.ok) {
        const data = await response.json();
        if (data.success) {
        const message = data.total_pages ?
            `成功获取 ${data.total_count} 个商品（共${data.total_pages}页），请查看控制台日志` :
            `成功获取商品信息，请查看控制台日志`;
        showToast(message, 'success');
        // 刷新商品列表（保持筛选器选择）
        await refreshItemsData();
        } else {
        showToast(data.message || '获取商品信息失败', 'danger');
        }
    } else {
        throw new Error(`HTTP ${response.status}`);
    }
    } catch (error) {
    console.error('获取商品信息失败:', error);
    showToast('获取商品信息失败', 'danger');
    } finally {
    // 恢复按钮状态
    button.innerHTML = originalText;
    button.disabled = false;
    }
}



// 编辑商品详情
async function editItem(cookieId, itemId) {
    try {
    const response = await fetch(`${apiBase}/items/${encodeURIComponent(cookieId)}/${encodeURIComponent(itemId)}`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        const data = await response.json();
        const item = data.item;

        // 填充表单
        document.getElementById('editItemCookieId').value = item.cookie_id;
        document.getElementById('editItemId').value = item.item_id;
        document.getElementById('editItemCookieIdDisplay').value = item.cookie_id;
        document.getElementById('editItemIdDisplay').value = item.item_id;
        document.getElementById('editItemDetail').value = item.item_detail || '';

        // 显示模态框
        const modal = new bootstrap.Modal(document.getElementById('editItemModal'));
        modal.show();
    } else {
        throw new Error('获取商品详情失败');
    }
    } catch (error) {
    console.error('获取商品详情失败:', error);
    showToast('获取商品详情失败', 'danger');
    }
}

// 保存商品详情
async function saveItemDetail() {
    const cookieId = document.getElementById('editItemCookieId').value;
    const itemId = document.getElementById('editItemId').value;
    const itemDetail = document.getElementById('editItemDetail').value.trim();

    if (!itemDetail) {
    showToast('请输入商品详情', 'warning');
    return;
    }

    try {
    const response = await fetch(`${apiBase}/items/${encodeURIComponent(cookieId)}/${encodeURIComponent(itemId)}`, {
        method: 'PUT',
        headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
        },
        body: JSON.stringify({
        item_detail: itemDetail
        })
    });

    if (response.ok) {
        showToast('商品详情更新成功', 'success');

        // 关闭模态框
        const modal = bootstrap.Modal.getInstance(document.getElementById('editItemModal'));
        modal.hide();

        // 刷新列表（保持筛选器选择）
        await refreshItemsData();
    } else {
        const error = await response.text();
        showToast(`更新失败: ${error}`, 'danger');
    }
    } catch (error) {
    console.error('更新商品详情失败:', error);
    showToast('更新商品详情失败', 'danger');
    }
}

// 删除商品信息
async function deleteItem(cookieId, itemId, itemTitle) {
    try {
    // 确认删除
    const confirmed = confirm(`确定要删除商品信息吗？\n\n商品ID: ${itemId}\n商品标题: ${itemTitle || '未设置'}\n\n此操作不可撤销！`);
    if (!confirmed) {
        return;
    }

    const response = await fetch(`${apiBase}/items/${encodeURIComponent(cookieId)}/${encodeURIComponent(itemId)}`, {
        method: 'DELETE',
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        showToast('商品信息删除成功', 'success');
        // 刷新列表（保持筛选器选择）
        await refreshItemsData();
    } else {
        const error = await response.text();
        showToast(`删除失败: ${error}`, 'danger');
    }
    } catch (error) {
    console.error('删除商品信息失败:', error);
    showToast('删除商品信息失败', 'danger');
    }
}

// 批量删除商品信息
async function batchDeleteItems() {
    try {
    // 获取所有选中的复选框
    const checkboxes = document.querySelectorAll('input[name="itemCheckbox"]:checked');
    if (checkboxes.length === 0) {
        showToast('请选择要删除的商品', 'warning');
        return;
    }

    // 确认删除
    const confirmed = confirm(`确定要删除选中的 ${checkboxes.length} 个商品信息吗？\n\n此操作不可撤销！`);
    if (!confirmed) {
        return;
    }

    // 构造删除列表
    const itemsToDelete = Array.from(checkboxes).map(checkbox => {
        const row = checkbox.closest('tr');
        return {
        cookie_id: checkbox.dataset.cookieId,
        item_id: checkbox.dataset.itemId
        };
    });

    const response = await fetch(`${apiBase}/items/batch`, {
        method: 'DELETE',
        headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
        },
        body: JSON.stringify({ items: itemsToDelete })
    });

    if (response.ok) {
        const result = await response.json();
        showToast(`批量删除完成: 成功 ${result.success_count} 个，失败 ${result.failed_count} 个`, 'success');
        // 刷新列表（保持筛选器选择）
        await refreshItemsData();
    } else {
        const error = await response.text();
        showToast(`批量删除失败: ${error}`, 'danger');
    }
    } catch (error) {
    console.error('批量删除商品信息失败:', error);
    showToast('批量删除商品信息失败', 'danger');
    }
}

// 全选/取消全选
function toggleSelectAll(selectAllCheckbox) {
    const checkboxes = document.querySelectorAll('input[name="itemCheckbox"]');
    checkboxes.forEach(checkbox => {
    checkbox.checked = selectAllCheckbox.checked;
    });
    updateBatchDeleteButton();
}

// 更新全选状态
function updateSelectAllState() {
    const checkboxes = document.querySelectorAll('input[name="itemCheckbox"]');
    const checkedCheckboxes = document.querySelectorAll('input[name="itemCheckbox"]:checked');
    const selectAllCheckbox = document.getElementById('selectAllItems');

    if (checkboxes.length === 0) {
    selectAllCheckbox.checked = false;
    selectAllCheckbox.indeterminate = false;
    } else if (checkedCheckboxes.length === checkboxes.length) {
    selectAllCheckbox.checked = true;
    selectAllCheckbox.indeterminate = false;
    } else if (checkedCheckboxes.length > 0) {
    selectAllCheckbox.checked = false;
    selectAllCheckbox.indeterminate = true;
    } else {
    selectAllCheckbox.checked = false;
    selectAllCheckbox.indeterminate = false;
    }

    updateBatchDeleteButton();
}

// 更新批量删除按钮状态
function updateBatchDeleteButton() {
    const checkedCheckboxes = document.querySelectorAll('input[name="itemCheckbox"]:checked');
    const batchDeleteBtn = document.getElementById('batchDeleteBtn');

    if (checkedCheckboxes.length > 0) {
    batchDeleteBtn.disabled = false;
    batchDeleteBtn.innerHTML = `<i class="bi bi-trash"></i> 批量删除 (${checkedCheckboxes.length})`;
    } else {
    batchDeleteBtn.disabled = true;
    batchDeleteBtn.innerHTML = '<i class="bi bi-trash"></i> 批量删除';
    }
}

// 格式化日期时间
function formatDateTime(dateString) {
    if (!dateString) return '未知';
    const date = new Date(dateString);
    return date.toLocaleString('zh-CN');
}

// HTML转义函数
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ================================
// 【商品回复管理菜单】相关功能
// ================================

// 加载商品回复列表
async function loadItemsReplay() {
    try {
    // 先加载Cookie列表用于筛选
    await loadCookieFilter('itemReplayCookieFilter');
    await loadCookieFilterPlus('editReplyCookieIdSelect');
    // 加载商品列表
    await refreshItemsReplayData();
    } catch (error) {
    console.error('加载商品列表失败:', error);
    showToast('加载商品列表失败', 'danger');
    }
}

// 只刷新商品回复数据，不重新加载筛选器
async function refreshItemsReplayData() {
    try {
    const selectedCookie = document.getElementById('itemCookieFilter').value;
    if (selectedCookie) {
        await loadItemsReplayByCookie();
    } else {
        await loadAllItemReplays();
    }
    } catch (error) {
    console.error('刷新商品数据失败:', error);
    showToast('刷新商品数据失败', 'danger');
    }
}

// 加载Cookie筛选选项添加弹框中使用
async function loadCookieFilterPlus(id) {
    try {
    const response = await fetch(`${apiBase}/cookies/details`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        const accounts = await response.json();
        const select = document.getElementById(id);

        // 保存当前选择的值
        const currentValue = select.value;

        // 清空现有选项（保留"所有账号"）
        select.innerHTML = '<option value="">选择账号</option>';

        if (accounts.length === 0) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = '❌ 暂无账号';
        option.disabled = true;
        select.appendChild(option);
        return;
        }

        // 分组显示：先显示启用的账号，再显示禁用的账号
        const enabledAccounts = accounts.filter(account => {
        const enabled = account.enabled === undefined ? true : account.enabled;
        return enabled;
        });
        const disabledAccounts = accounts.filter(account => {
        const enabled = account.enabled === undefined ? true : account.enabled;
        return !enabled;
        });

        // 添加启用的账号
        enabledAccounts.forEach(account => {
        const option = document.createElement('option');
        option.value = account.id;
        option.textContent = `🟢 ${account.id}`;
        select.appendChild(option);
        });

        // 添加禁用的账号
        if (disabledAccounts.length > 0) {
        // 添加分隔线
        if (enabledAccounts.length > 0) {
            const separator = document.createElement('option');
            separator.value = '';
            separator.textContent = '────────────────';
            separator.disabled = true;
            select.appendChild(separator);
        }

        disabledAccounts.forEach(account => {
            const option = document.createElement('option');
            option.value = account.id;
            option.textContent = `🔴 ${account.id} (已禁用)`;
            select.appendChild(option);
        });
        }

        // 恢复之前选择的值
        if (currentValue) {
        select.value = currentValue;
        }
    }
    } catch (error) {
    console.error('加载Cookie列表失败:', error);
    showToast('加载账号列表失败', 'danger');
    }
}

// 刷新商品回复列表
async function refreshItemReplayS() {
    await refreshItemsReplayData();
    showToast('商品列表已刷新', 'success');
}

// 加载所有商品回复
async function loadAllItemReplays() {
    try {
    const response = await fetch(`${apiBase}/itemReplays`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        const data = await response.json();
        displayItemReplays(data.items);
    } else {
        throw new Error('获取商品列表失败');
    }
    } catch (error) {
    console.error('加载商品列表失败:', error);
    showToast('加载商品列表失败', 'danger');
    }
}

// 按Cookie加载商品回复
async function loadItemsReplayByCookie() {
    const cookieId = document.getElementById('itemReplayCookieFilter').value;
    if (!cookieId) {
    await loadAllItemReplays();
    return;
    }

    try {
    const response = await fetch(`${apiBase}/itemReplays/cookie/${encodeURIComponent(cookieId)}`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        const data = await response.json();
        displayItemReplays(data.items);
    } else {
        throw new Error('获取商品列表失败');
    }
    } catch (error) {
    console.error('加载商品列表失败:', error);
    showToast('加载商品列表失败', 'danger');
    }
}

// 显示商品回复列表
function displayItemReplays(items) {
    const tbody = document.getElementById('itemReplaysTableBody');

    if (!items || items.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">暂无商品数据</td></tr>';
    // 重置选择状态
    const selectAllCheckbox = document.getElementById('selectAllItems');
    if (selectAllCheckbox) {
        selectAllCheckbox.checked = false;
        selectAllCheckbox.indeterminate = false;
    }
    updateBatchDeleteButton();
    return;
    }

    const itemsHtml = items.map(item => {
    // 处理商品标题显示
    let itemTitleDisplay = item.item_title || '未设置';
    if (itemTitleDisplay.length > 30) {
        itemTitleDisplay = itemTitleDisplay.substring(0, 30) + '...';
    }

    // 处理商品详情显示
    let itemDetailDisplay = '未设置';
    if (item.item_detail) {
        try {
        // 尝试解析JSON并提取有用信息
        const detail = JSON.parse(item.item_detail);
        if (detail.content) {
            itemDetailDisplay = detail.content.substring(0, 50) + (detail.content.length > 50 ? '...' : '');
        } else {
            // 如果是纯文本或其他格式，直接显示前50个字符
            itemDetailDisplay = item.item_detail.substring(0, 50) + (item.item_detail.length > 50 ? '...' : '');
        }
        } catch (e) {
        // 如果不是JSON格式，直接显示前50个字符
        itemDetailDisplay = item.item_detail.substring(0, 50) + (item.item_detail.length > 50 ? '...' : '');
        }
    }

    return `
        <tr>
         <td>
            <input type="checkbox" name="itemCheckbox"
                    data-cookie-id="${escapeHtml(item.cookie_id)}"
                    data-item-id="${escapeHtml(item.item_id)}"
                    onchange="updateSelectAllState()">
        </td>
        <td>${escapeHtml(item.cookie_id)}</td>
        <td>${escapeHtml(item.item_id)}</td>
        <td title="${escapeHtml(item.item_title || '未设置')}">${escapeHtml(itemTitleDisplay)}</td>
        <td title="${escapeHtml(item.item_detail || '未设置')}">${escapeHtml(itemDetailDisplay)}</td>
        <td title="${escapeHtml(item.reply_content || '未设置')}">${escapeHtml(item.reply_content)}</td>
        <td>${formatDateTime(item.updated_at)}</td>
        <td>
            <div class="btn-group" role="group">
            <button class="btn btn-sm btn-outline-primary" onclick="editItemReply('${escapeHtml(item.cookie_id)}', '${escapeHtml(item.item_id)}')" title="编辑详情">
                <i class="bi bi-pencil"></i>
            </button>
            <button class="btn btn-sm btn-outline-danger" onclick="deleteItemReply('${escapeHtml(item.cookie_id)}', '${escapeHtml(item.item_id)}', '${escapeHtml(item.item_title || item.item_id)}')" title="删除">
                <i class="bi bi-trash"></i>
            </button>
            </div>
        </td>
        </tr>
    `;
    }).join('');

    // 更新表格内容
    tbody.innerHTML = itemsHtml;

    // 重置选择状态
    const selectAllCheckbox = document.getElementById('selectAllItems');
    if (selectAllCheckbox) {
    selectAllCheckbox.checked = false;
    selectAllCheckbox.indeterminate = false;
    }
    updateBatchDeleteButton();
}

// 显示添加弹框
async function showItemReplayEdit(){
    // 显示模态框
    const modal = new bootstrap.Modal(document.getElementById('editItemReplyModal'));
    document.getElementById('editReplyCookieIdSelect').value = '';
    document.getElementById('editReplyItemIdSelect').value = '';
    document.getElementById('editReplyItemIdSelect').disabled = true
    document.getElementById('editItemReplyContent').value = '';
    document.getElementById('itemReplayTitle').textContent = '添加商品回复';
    modal.show();
}

// 当账号变化时加载对应商品
async function onCookieChangeForReply() {
  const cookieId = document.getElementById('editReplyCookieIdSelect').value;
  const itemSelect = document.getElementById('editReplyItemIdSelect');

  itemSelect.innerHTML = '<option value="">选择商品</option>';
  if (!cookieId) {
    itemSelect.disabled = true;  // 禁用选择框
    return;
  } else {
    itemSelect.disabled = false; // 启用选择框
  }

  const response = await fetch(`${apiBase}/items/cookie/${encodeURIComponent(cookieId)}`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });
    try {
       if (response.ok) {
            const data = await response.json();
            data.items.forEach(item => {
                  const opt = document.createElement('option');
                  opt.value = item.item_id;
                  opt.textContent = `${item.item_id} - ${item.item_title || '无标题'}`;
                  itemSelect.appendChild(opt);
                });
        } else {
            throw new Error('获取商品列表失败');
        }
    }catch (error) {
        console.error('加载商品列表失败:', error);
        showToast('加载商品列表失败', 'danger');
    }
}

// 编辑商品回复
async function editItemReply(cookieId, itemId) {
  try {
    const response = await fetch(`${apiBase}/item-reply/${encodeURIComponent(cookieId)}/${encodeURIComponent(itemId)}`, {
      headers: {
        'Authorization': `Bearer ${authToken}`
      }
    });
    if (response.ok) {
      const data = await response.json();
      document.getElementById('itemReplayTitle').textContent = '编辑商品回复';
      // 填充表单
      document.getElementById('editReplyCookieIdSelect').value = data.cookie_id;
      let res = await onCookieChangeForReply()
      document.getElementById('editReplyItemIdSelect').value = data.item_id;
      document.getElementById('editItemReplyContent').value = data.reply_content || '';

    } else if (response.status === 404) {
      // 如果没有记录，则填充空白内容（用于添加）
//      document.getElementById('editReplyCookieIdSelect').value = data.cookie_id;
//      document.getElementById('editReplyItemIdSelect').value = data.item_id;
//      document.getElementById('editItemReplyContent').value = data.reply_content || '';
    } else {
      throw new Error('获取商品回复失败');
    }

    // 显示模态框
    const modal = new bootstrap.Modal(document.getElementById('editItemReplyModal'));
    modal.show();

  } catch (error) {
    console.error('获取商品回复失败:', error);
    showToast('获取商品回复失败', 'danger');
  }
}

// 保存商品回复
async function saveItemReply() {
  const cookieId = document.getElementById('editReplyCookieIdSelect').value;
  const itemId = document.getElementById('editReplyItemIdSelect').value;
  const replyContent = document.getElementById('editItemReplyContent').value.trim();

  console.log(cookieId)
  console.log(itemId)
  console.log(replyContent)
  if (!cookieId) {
    showToast('请选择账号', 'warning');
    return;
  }

  if (!itemId) {
    showToast('请选择商品', 'warning');
    return;
  }

  if (!replyContent) {
    showToast('请输入商品回复内容', 'warning');
    return;
  }

  try {
    const response = await fetch(`${apiBase}/item-reply/${encodeURIComponent(cookieId)}/${encodeURIComponent(itemId)}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
      },
      body: JSON.stringify({
        reply_content: replyContent
      })
    });

    if (response.ok) {
      showToast('商品回复保存成功', 'success');

      // 关闭模态框
      const modal = bootstrap.Modal.getInstance(document.getElementById('editItemReplyModal'));
      modal.hide();

      // 可选：刷新数据
      await refreshItemsReplayData?.();
    } else {
      const error = await response.text();
      showToast(`保存失败: ${error}`, 'danger');
    }
  } catch (error) {
    console.error('保存商品回复失败:', error);
    showToast('保存商品回复失败', 'danger');
  }
}

// 删除商品回复
async function deleteItemReply(cookieId, itemId, itemTitle) {
  try {
    const confirmed = confirm(`确定要删除该商品的自动回复吗？\n\n商品ID: ${itemId}\n商品标题: ${itemTitle || '未设置'}\n\n此操作不可撤销！`);
    if (!confirmed) return;

    const response = await fetch(`${apiBase}/item-reply/${encodeURIComponent(cookieId)}/${encodeURIComponent(itemId)}`, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${authToken}`
      }
    });

    if (response.ok) {
      showToast('商品回复删除成功', 'success');
      await loadItemsReplayByCookie?.(); // 如果你有刷新商品列表的函数
    } else {
      const error = await response.text();
      showToast(`删除失败: ${error}`, 'danger');
    }
  } catch (error) {
    console.error('删除商品回复失败:', error);
    showToast('删除商品回复失败', 'danger');
  }
}

// 批量删除商品回复
async function batchDeleteItemReplies() {
  try {
    const checkboxes = document.querySelectorAll('input[name="itemCheckbox"]:checked');
    if (checkboxes.length === 0) {
      showToast('请选择要删除回复的商品', 'warning');
      return;
    }

    const confirmed = confirm(`确定要删除选中商品的自动回复吗？\n共 ${checkboxes.length} 个商品\n\n此操作不可撤销！`);
    if (!confirmed) return;

    const itemsToDelete = Array.from(checkboxes).map(checkbox => ({
      cookie_id: checkbox.dataset.cookieId,
      item_id: checkbox.dataset.itemId
    }));

    const response = await fetch(`${apiBase}/item-reply/batch`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
      },
      body: JSON.stringify({ items: itemsToDelete })
    });

    if (response.ok) {
      const result = await response.json();
      showToast(`批量删除回复完成: 成功 ${result.success_count} 个，失败 ${result.failed_count} 个`, 'success');
      await loadItemsReplayByCookie?.();
    } else {
      const error = await response.text();
      showToast(`批量删除失败: ${error}`, 'danger');
    }
  } catch (error) {
    console.error('批量删除商品回复失败:', error);
    showToast('批量删除商品回复失败', 'danger');
  }
}

// ================================
// 【日志管理菜单】相关功能
// ================================

window.autoRefreshInterval = null;
window.allLogs = [];
window.filteredLogs = [];

// 刷新日志
async function refreshLogs() {
    try {
        const logLinesElement = document.getElementById('logLines');
        if (!logLinesElement) {
            console.warn('logLines 元素不存在');
            showToast('页面元素缺失，请刷新页面', 'warning');
            return;
        }

        const lines = logLinesElement.value;

        const response = await fetch(`${apiBase}/logs?lines=${lines}`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            const data = await response.json();
            window.allLogs = data.logs || [];
            window.filteredLogs = window.allLogs; // 不再过滤，直接显示所有日志
            displayLogs();
            updateLogStats();
            showToast('日志已刷新', 'success');
        } else {
            throw new Error(`HTTP ${response.status}`);
        }
    } catch (error) {
        console.error('刷新日志失败:', error);
        showToast(`刷新日志失败: ${error.message}`, 'danger');
    }
}



// 显示日志
function displayLogs() {
    const container = document.getElementById('logContainer');

    // 检查容器是否存在
    if (!container) {
        // 只在特定页面显示警告，避免在其他页面产生无用的警告
        const currentPath = window.location.pathname;
        if (currentPath.includes('log') || currentPath.includes('admin')) {
            console.warn('logContainer 元素不存在，无法显示日志');
        }
        return;
    }

    if (!window.filteredLogs || window.filteredLogs.length === 0) {
    container.innerHTML = `
        <div class="text-center p-4 text-muted">
        <i class="bi bi-file-text fs-1"></i>
        <p class="mt-2">暂无日志数据</p>
        </div>
    `;
    return;
    }

    const logsHtml = window.filteredLogs.map(log => {
    const timestamp = formatLogTimestamp(log.timestamp);
    const levelClass = log.level || 'INFO';

    return `
        <div class="log-entry ${levelClass}">
        <span class="log-timestamp">${timestamp}</span>
        <span class="log-level">[${log.level}]</span>
        <span class="log-source">${log.source}:</span>
        <span class="log-message">${escapeHtml(log.message)}</span>
        </div>
    `;
    }).join('');

    container.innerHTML = logsHtml;

    // 滚动到底部
    container.scrollTop = container.scrollHeight;
}

// 格式化日志时间戳
function formatLogTimestamp(timestamp) {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    fractionalSecondDigits: 3
    });
}

// 更新日志统计信息
function updateLogStats() {
    const logCountElement = document.getElementById('logCount');
    const lastUpdateElement = document.getElementById('lastUpdate');

    if (logCountElement) {
        const count = window.filteredLogs ? window.filteredLogs.length : 0;
        logCountElement.textContent = `${count} 条日志`;
    }

    if (lastUpdateElement) {
        lastUpdateElement.textContent = new Date().toLocaleTimeString('zh-CN');
    }
}

// 清空日志显示
function clearLogsDisplay() {
    window.allLogs = [];
    window.filteredLogs = [];
    document.getElementById('logContainer').innerHTML = `
    <div class="text-center p-4 text-muted">
        <i class="bi bi-file-text fs-1"></i>
        <p class="mt-2">日志显示已清空</p>
    </div>
    `;
    updateLogStats();
    showToast('日志显示已清空', 'info');
}

// 切换自动刷新
function toggleAutoRefresh() {
    const button = document.querySelector('#autoRefreshText');
    const icon = button.previousElementSibling;

    if (window.autoRefreshInterval) {
    // 停止自动刷新
    clearInterval(window.autoRefreshInterval);
    window.autoRefreshInterval = null;
    button.textContent = '开启自动刷新';
    icon.className = 'bi bi-play-circle me-1';
    showToast('自动刷新已停止', 'info');
    } else {
    // 开启自动刷新
    window.autoRefreshInterval = setInterval(refreshLogs, 5000); // 每5秒刷新一次
    button.textContent = '停止自动刷新';
    icon.className = 'bi bi-pause-circle me-1';
    showToast('自动刷新已开启（每5秒）', 'success');

    // 立即刷新一次
    refreshLogs();
    }
}

// 清空服务器日志
async function clearLogsServer() {
    if (!confirm('确定要清空服务器端的所有日志吗？此操作不可恢复！')) {
    return;
    }

    try {
    const response = await fetch(`${apiBase}/logs/clear`, {
        method: 'POST',
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        const data = await response.json();
        if (data.success) {
        window.allLogs = [];
        window.filteredLogs = [];
        displayLogs();
        updateLogStats();
        showToast('服务器日志已清空', 'success');
        } else {
        showToast(data.message || '清空失败', 'danger');
        }
    } else {
        throw new Error(`HTTP ${response.status}`);
    }
    } catch (error) {
    console.error('清空服务器日志失败:', error);
    showToast('清空服务器日志失败', 'danger');
    }
}

// 显示日志统计信息
async function showLogStats() {
    try {
    const response = await fetch(`${apiBase}/logs/stats`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        const data = await response.json();
        if (data.success) {
        const stats = data.stats;

        let statsHtml = `
            <div class="row">
            <div class="col-md-6">
                <h6>总体统计</h6>
                <ul class="list-unstyled">
                <li>总日志数: <strong>${stats.total_logs}</strong></li>
                <li>最大容量: <strong>${stats.max_capacity}</strong></li>
                <li>使用率: <strong>${((stats.total_logs / stats.max_capacity) * 100).toFixed(1)}%</strong></li>
                </ul>
            </div>
            <div class="col-md-6">
                <h6>级别分布</h6>
                <ul class="list-unstyled">
        `;

        for (const [level, count] of Object.entries(stats.level_counts || {})) {
            const percentage = ((count / stats.total_logs) * 100).toFixed(1);
            statsHtml += `<li>${level}: <strong>${count}</strong> (${percentage}%)</li>`;
        }

        statsHtml += `
                </ul>
            </div>
            </div>
            <div class="row mt-3">
            <div class="col-12">
                <h6>来源分布</h6>
                <div class="row">
        `;

        const sources = Object.entries(stats.source_counts || {});
        sources.forEach(([source, count], index) => {
            if (index % 2 === 0) statsHtml += '<div class="col-md-6"><ul class="list-unstyled">';
            const percentage = ((count / stats.total_logs) * 100).toFixed(1);
            statsHtml += `<li>${source}: <strong>${count}</strong> (${percentage}%)</li>`;
            if (index % 2 === 1 || index === sources.length - 1) statsHtml += '</ul></div>';
        });

        statsHtml += `
                </div>
            </div>
            </div>
        `;

        // 显示模态框
        const modalHtml = `
            <div class="modal fade" id="logStatsModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">日志统计信息</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    ${statsHtml}
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                </div>
                </div>
            </div>
            </div>
        `;

        // 移除旧的模态框
        const oldModal = document.getElementById('logStatsModal');
        if (oldModal) oldModal.remove();

        // 添加新的模态框
        document.body.insertAdjacentHTML('beforeend', modalHtml);

        // 显示模态框
        const modal = new bootstrap.Modal(document.getElementById('logStatsModal'));
        modal.show();

        } else {
        showToast(data.message || '获取统计信息失败', 'danger');
        }
    } else {
        throw new Error(`HTTP ${response.status}`);
    }
    } catch (error) {
    console.error('获取日志统计失败:', error);
    showToast('获取日志统计失败', 'danger');
    }
}

// ==================== 导入导出功能 ====================

// 导出关键词
async function exportKeywords() {
    if (!currentCookieId) {
    showToast('请先选择账号', 'warning');
    return;
    }

    try {
    const response = await fetch(`${apiBase}/keywords-export/${currentCookieId}`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        // 创建下载链接
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;

        // 根据当前账号是否有数据来设置文件名和提示
        const currentKeywords = keywordsData[currentCookieId] || [];
        const hasData = currentKeywords.length > 0;

        if (hasData) {
        a.download = `keywords_${currentCookieId}_${new Date().getTime()}.xlsx`;
        showToast('关键词导出成功！', 'success');
        } else {
        a.download = `keywords_template_${currentCookieId}_${new Date().getTime()}.xlsx`;
        showToast('导入模板导出成功！模板中包含示例数据供参考', 'success');
        }

        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    } else {
        const error = await response.json();
        showToast(`导出失败: ${error.detail}`, 'error');
    }
    } catch (error) {
    console.error('导出关键词失败:', error);
    showToast('导出关键词失败', 'error');
    }
}

// 显示导入模态框
function showImportModal() {
    if (!currentCookieId) {
    showToast('请先选择账号', 'warning');
    return;
    }

    const modal = new bootstrap.Modal(document.getElementById('importKeywordsModal'));
    modal.show();
}

// 导入关键词
async function importKeywords() {
    if (!currentCookieId) {
    showToast('请先选择账号', 'warning');
    return;
    }

    const fileInput = document.getElementById('importFileInput');
    const file = fileInput.files[0];

    if (!file) {
    showToast('请选择要导入的Excel文件', 'warning');
    return;
    }

    try {
    // 显示进度条
    const progressDiv = document.getElementById('importProgress');
    const progressBar = progressDiv.querySelector('.progress-bar');
    progressDiv.style.display = 'block';
    progressBar.style.width = '30%';

    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${apiBase}/keywords-import/${currentCookieId}`, {
        method: 'POST',
        headers: {
        'Authorization': `Bearer ${authToken}`
        },
        body: formData
    });

    progressBar.style.width = '70%';

    if (response.ok) {
        const result = await response.json();
        progressBar.style.width = '100%';

        setTimeout(() => {
        progressDiv.style.display = 'none';
        progressBar.style.width = '0%';

        // 关闭模态框
        const modal = bootstrap.Modal.getInstance(document.getElementById('importKeywordsModal'));
        modal.hide();

        // 清空文件输入
        fileInput.value = '';

        // 重新加载关键词列表
        loadAccountKeywords(currentCookieId);

        showToast(`导入成功！新增: ${result.added}, 更新: ${result.updated}`, 'success');
        }, 500);
    } else {
        const error = await response.json();
        progressDiv.style.display = 'none';
        progressBar.style.width = '0%';
        showToast(`导入失败: ${error.detail}`, 'error');
    }
    } catch (error) {
    console.error('导入关键词失败:', error);
    document.getElementById('importProgress').style.display = 'none';
    document.querySelector('#importProgress .progress-bar').style.width = '0%';
    showToast('导入关键词失败', 'error');
    }
}

// ========================= 账号添加相关函数 =========================

// 切换手动输入表单显示/隐藏
function toggleManualInput() {
    const manualForm = document.getElementById('manualInputForm');
    if (manualForm.style.display === 'none') {
    manualForm.style.display = 'block';
    // 清空表单
    document.getElementById('addForm').reset();
    } else {
    manualForm.style.display = 'none';
    }
}

// ========================= 扫码登录相关函数 =========================

let qrCodeCheckInterval = null;
let qrCodeSessionId = null;

// 显示扫码登录模态框
function showQRCodeLogin() {
    const modal = new bootstrap.Modal(document.getElementById('qrCodeLoginModal'));
    modal.show();

    // 模态框显示后生成二维码
    modal._element.addEventListener('shown.bs.modal', function () {
    generateQRCode();
    });

    // 模态框关闭时清理定时器
    modal._element.addEventListener('hidden.bs.modal', function () {
    clearQRCodeCheck();
    });
}

// 刷新二维码（兼容旧函数名）
async function refreshQRCode() {
    await generateQRCode();
}

// 生成二维码
async function generateQRCode() {
    try {
    showQRCodeLoading();

    const response = await fetch(`${apiBase}/qr-login/generate`, {
        method: 'POST',
        headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
        }
    });

    if (response.ok) {
        const data = await response.json();
        if (data.success) {
        qrCodeSessionId = data.session_id;
        showQRCodeImage(data.qr_code_url);
        startQRCodeCheck();
        } else {
        showQRCodeError(data.message || '生成二维码失败');
        }
    } else {
        showQRCodeError('生成二维码失败');
    }
    } catch (error) {
    console.error('生成二维码失败:', error);
    showQRCodeError('网络错误，请重试');
    }
}

// 显示二维码加载状态
function showQRCodeLoading() {
    document.getElementById('qrCodeContainer').style.display = 'block';
    document.getElementById('qrCodeImage').style.display = 'none';
    document.getElementById('statusText').textContent = '正在生成二维码，请耐心等待...';
    document.getElementById('statusSpinner').style.display = 'none';

    // 隐藏验证容器
    const verificationContainer = document.getElementById('verificationContainer');
    if (verificationContainer) {
    verificationContainer.style.display = 'none';
    }
}

// 显示二维码图片
function showQRCodeImage(qrCodeUrl) {
    document.getElementById('qrCodeContainer').style.display = 'none';
    document.getElementById('qrCodeImage').style.display = 'block';
    document.getElementById('qrCodeImg').src = qrCodeUrl;
    document.getElementById('statusText').textContent = '等待扫码...';
    document.getElementById('statusSpinner').style.display = 'none';
}

// 显示二维码错误
function showQRCodeError(message) {
    document.getElementById('qrCodeContainer').innerHTML = `
    <div class="text-danger">
        <i class="bi bi-exclamation-triangle fs-1 mb-3"></i>
        <p>${message}</p>
    </div>
    `;
    document.getElementById('qrCodeImage').style.display = 'none';
    document.getElementById('statusText').textContent = '生成失败';
    document.getElementById('statusSpinner').style.display = 'none';
}

// 开始检查二维码状态
function startQRCodeCheck() {
    if (qrCodeCheckInterval) {
    clearInterval(qrCodeCheckInterval);
    }

    document.getElementById('statusSpinner').style.display = 'inline-block';
    document.getElementById('statusText').textContent = '等待扫码...';

    qrCodeCheckInterval = setInterval(checkQRCodeStatus, 2000); // 每2秒检查一次
}

// 检查二维码状态
async function checkQRCodeStatus() {
    if (!qrCodeSessionId) return;

    try {
    const response = await fetch(`${apiBase}/qr-login/check/${qrCodeSessionId}`, {
        headers: {
        'Authorization': `Bearer ${authToken}`
        }
    });

    if (response.ok) {
        const data = await response.json();

        switch (data.status) {
        case 'waiting':
            document.getElementById('statusText').textContent = '等待扫码...';
            break;
        case 'scanned':
            document.getElementById('statusText').textContent = '已扫码，请在手机上确认...';
            break;
        case 'success':
            document.getElementById('statusText').textContent = '登录成功！';
            document.getElementById('statusSpinner').style.display = 'none';
            clearQRCodeCheck();
            handleQRCodeSuccess(data);
            break;
        case 'expired':
            document.getElementById('statusText').textContent = '二维码已过期';
            document.getElementById('statusSpinner').style.display = 'none';
            clearQRCodeCheck();
            showQRCodeError('二维码已过期，请刷新重试');
            break;
        case 'cancelled':
            document.getElementById('statusText').textContent = '用户取消登录';
            document.getElementById('statusSpinner').style.display = 'none';
            clearQRCodeCheck();
            break;
        case 'verification_required':
            document.getElementById('statusText').textContent = '需要手机验证';
            document.getElementById('statusSpinner').style.display = 'none';
            clearQRCodeCheck();
            showVerificationRequired(data);
            break;
        }
    }
    } catch (error) {
    console.error('检查二维码状态失败:', error);
    }
}

// 显示需要验证的提示
function showVerificationRequired(data) {
    if (data.verification_url) {
    // 隐藏二维码区域
    document.getElementById('qrCodeContainer').style.display = 'none';
    document.getElementById('qrCodeImage').style.display = 'none';

    // 显示验证提示
    const verificationHtml = `
        <div class="text-center">
        <div class="mb-4">
            <i class="bi bi-shield-exclamation text-warning" style="font-size: 4rem;"></i>
        </div>
        <h5 class="text-warning mb-3">账号需要手机验证</h5>
        <div class="alert alert-warning border-0 mb-4">
            <i class="bi bi-info-circle me-2"></i>
            <strong>检测到账号存在风控，需要进行手机验证才能完成登录</strong>
        </div>
        <div class="mb-4">
            <p class="text-muted mb-3">请点击下方按钮，在新窗口中完成手机验证：</p>
            <a href="${data.verification_url}" target="_blank" class="btn btn-warning btn-lg">
            <i class="bi bi-phone me-2"></i>
            打开手机验证页面
            </a>
        </div>
        <div class="alert alert-info border-0">
            <i class="bi bi-lightbulb me-2"></i>
            <small>
            <strong>验证步骤：</strong><br>
            1. 点击上方按钮打开验证页面<br>
            2. 按照页面提示完成手机验证<br>
            3. 验证完成后，重新扫码登录
            </small>
        </div>
        </div>
    `;

    // 创建验证提示容器
    let verificationContainer = document.getElementById('verificationContainer');
    if (!verificationContainer) {
        verificationContainer = document.createElement('div');
        verificationContainer.id = 'verificationContainer';
        document.querySelector('#qrCodeLoginModal .modal-body').appendChild(verificationContainer);
    }

    verificationContainer.innerHTML = verificationHtml;
    verificationContainer.style.display = 'block';

    // 显示Toast提示
    showToast('账号需要手机验证，请按照提示完成验证', 'warning');
    }
}

// 处理扫码成功
function handleQRCodeSuccess(data) {
    if (data.account_info) {
    const { account_id, is_new_account } = data.account_info;

    if (is_new_account) {
        showToast(`新账号添加成功！账号ID: ${account_id}`, 'success');
    } else {
        showToast(`账号Cookie已更新！账号ID: ${account_id}`, 'success');
    }

    // 关闭模态框
    setTimeout(() => {
        const modal = bootstrap.Modal.getInstance(document.getElementById('qrCodeLoginModal'));
        modal.hide();

        // 刷新账号列表
        loadCookies();
    }, 2000);
    }
}

// 清理二维码检查
function clearQRCodeCheck() {
    if (qrCodeCheckInterval) {
    clearInterval(qrCodeCheckInterval);
    qrCodeCheckInterval = null;
    }
    qrCodeSessionId = null;
}

// 刷新二维码
function refreshQRCode() {
    clearQRCodeCheck();
    generateQRCode();
}

// ==================== 图片关键词管理功能 ====================

// 显示添加图片关键词模态框
function showAddImageKeywordModal() {
    if (!currentCookieId) {
        showToast('请先选择账号', 'warning');
        return;
    }

    // 加载商品列表到图片关键词模态框
    loadItemsListForImageKeyword();

    // 显示模态框
    const modal = new bootstrap.Modal(document.getElementById('addImageKeywordModal'));
    modal.show();

    // 清空表单
    document.getElementById('imageKeyword').value = '';
    document.getElementById('imageItemIdSelect').value = '';
    document.getElementById('imageFile').value = '';
    hideImagePreview();
}

// 为图片关键词模态框加载商品列表
async function loadItemsListForImageKeyword() {
    try {
        const response = await fetch(`${apiBase}/items/${currentCookieId}`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            const data = await response.json();
            const items = data.items || [];

            // 更新商品选择下拉框
            const selectElement = document.getElementById('imageItemIdSelect');
            if (selectElement) {
                // 清空现有选项（保留第一个默认选项）
                selectElement.innerHTML = '<option value="">选择商品或留空表示通用关键词</option>';

                // 添加商品选项
                items.forEach(item => {
                    const option = document.createElement('option');
                    option.value = item.item_id;
                    option.textContent = `${item.item_id} - ${item.item_title}`;
                    selectElement.appendChild(option);
                });
            }

            console.log(`为图片关键词加载了 ${items.length} 个商品到选择列表`);
        } else {
            console.warn('加载商品列表失败:', response.status);
        }
    } catch (error) {
        console.error('加载商品列表时发生错误:', error);
    }
}

// 处理图片文件选择事件监听器
function initImageKeywordEventListeners() {
    const imageFileInput = document.getElementById('imageFile');
    if (imageFileInput && !imageFileInput.hasEventListener) {
        imageFileInput.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                // 验证文件类型
                if (!file.type.startsWith('image/')) {
                    showToast('请选择图片文件', 'warning');
                    e.target.value = '';
                    hideImagePreview();
                    return;
                }

                // 验证文件大小（5MB）
                if (file.size > 5 * 1024 * 1024) {
                    showToast('❌ 图片文件大小不能超过 5MB，当前文件大小：' + (file.size / 1024 / 1024).toFixed(1) + 'MB', 'warning');
                    e.target.value = '';
                    hideImagePreview();
                    return;
                }

                // 验证图片尺寸
                validateImageDimensions(file, e.target);
            } else {
                hideImagePreview();
            }
        });
        imageFileInput.hasEventListener = true;
    }
}

// 验证图片尺寸
function validateImageDimensions(file, inputElement) {
    const img = new Image();
    const url = URL.createObjectURL(file);

    img.onload = function() {
        const width = this.naturalWidth;
        const height = this.naturalHeight;

        // 释放对象URL
        URL.revokeObjectURL(url);

        // 检查图片尺寸
        const maxDimension = 4096;
        const maxPixels = 8 * 1024 * 1024; // 8M像素
        const totalPixels = width * height;

        if (width > maxDimension || height > maxDimension) {
            showToast(`❌ 图片尺寸过大：${width}x${height}，最大允许：${maxDimension}x${maxDimension}像素`, 'warning');
            inputElement.value = '';
            hideImagePreview();
            return;
        }

        if (totalPixels > maxPixels) {
            showToast(`❌ 图片像素总数过大：${(totalPixels / 1024 / 1024).toFixed(1)}M像素，最大允许：8M像素`, 'warning');
            inputElement.value = '';
            hideImagePreview();
            return;
        }

        // 尺寸检查通过，显示预览和提示信息
        showImagePreview(file);

        // 如果图片较大，提示会被压缩
        if (width > 2048 || height > 2048) {
            showToast(`ℹ️ 图片尺寸较大（${width}x${height}），上传时将自动压缩以优化性能`, 'info');
        } else {
            showToast(`✅ 图片尺寸合适（${width}x${height}），可以上传`, 'success');
        }
    };

    img.onerror = function() {
        URL.revokeObjectURL(url);
        showToast('❌ 无法读取图片文件，请选择有效的图片', 'warning');
        inputElement.value = '';
        hideImagePreview();
    };

    img.src = url;
}

// 显示图片预览
function showImagePreview(file) {
    const reader = new FileReader();
    reader.onload = function(e) {
        const previewContainer = document.getElementById('imagePreview');
        const previewImg = document.getElementById('previewImg');

        previewImg.src = e.target.result;
        previewContainer.style.display = 'block';
    };
    reader.readAsDataURL(file);
}

// 隐藏图片预览
function hideImagePreview() {
    const previewContainer = document.getElementById('imagePreview');
    if (previewContainer) {
        previewContainer.style.display = 'none';
    }
}

// 添加图片关键词
async function addImageKeyword() {
    const keyword = document.getElementById('imageKeyword').value.trim();
    const itemId = document.getElementById('imageItemIdSelect').value.trim();
    const fileInput = document.getElementById('imageFile');
    const file = fileInput.files[0];

    if (!keyword) {
        showToast('请填写关键词', 'warning');
        return;
    }

    if (!file) {
        showToast('请选择图片文件', 'warning');
        return;
    }

    if (!currentCookieId) {
        showToast('请先选择账号', 'warning');
        return;
    }

    try {
        toggleLoading(true);

        // 创建FormData对象
        const formData = new FormData();
        formData.append('keyword', keyword);
        formData.append('item_id', itemId || '');
        formData.append('image', file);

        const response = await fetch(`${apiBase}/keywords/${currentCookieId}/image`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`
            },
            body: formData
        });

        if (response.ok) {
            showToast(`✨ 图片关键词 "${keyword}" 添加成功！`, 'success');

            // 关闭模态框
            const modal = bootstrap.Modal.getInstance(document.getElementById('addImageKeywordModal'));
            modal.hide();

            // 只刷新关键词列表，不重新加载整个界面
            await refreshKeywordsList();
        } else {
            try {
                const errorData = await response.json();
                let errorMessage = errorData.detail || '图片关键词添加失败';

                // 根据不同的错误类型提供更友好的提示
                if (errorMessage.includes('关键词') && (errorMessage.includes('已存在') || errorMessage.includes('重复'))) {
                    errorMessage = `❌ 关键词重复：${errorMessage}`;
                } else if (errorMessage.includes('图片尺寸过大')) {
                    errorMessage = '❌ 图片尺寸过大，请选择尺寸较小的图片（建议不超过4096x4096像素）';
                } else if (errorMessage.includes('图片像素总数过大')) {
                    errorMessage = '❌ 图片像素总数过大，请选择分辨率较低的图片';
                } else if (errorMessage.includes('图片数据验证失败')) {
                    errorMessage = '❌ 图片格式不支持或文件损坏，请选择JPG、PNG、GIF格式的图片';
                } else if (errorMessage.includes('图片保存失败')) {
                    errorMessage = '❌ 图片保存失败，请检查图片格式和大小后重试';
                } else if (errorMessage.includes('文件大小超过限制')) {
                    errorMessage = '❌ 图片文件过大，请选择小于5MB的图片';
                } else if (errorMessage.includes('不支持的图片格式')) {
                    errorMessage = '❌ 不支持的图片格式，请选择JPG、PNG、GIF格式的图片';
                } else if (response.status === 413) {
                    errorMessage = '❌ 图片文件过大，请选择小于5MB的图片';
                } else if (response.status === 400) {
                    errorMessage = `❌ 请求参数错误：${errorMessage}`;
                } else if (response.status === 500) {
                    errorMessage = '❌ 服务器内部错误，请稍后重试';
                }

                console.error('图片关键词添加失败:', errorMessage);
                showToast(errorMessage, 'danger');
            } catch (e) {
                // 如果不是JSON格式，使用文本
                const errorText = await response.text();
                console.error('图片关键词添加失败:', errorText);

                let friendlyMessage = '图片关键词添加失败';
                if (response.status === 413) {
                    friendlyMessage = '❌ 图片文件过大，请选择小于5MB的图片';
                } else if (response.status === 400) {
                    friendlyMessage = '❌ 图片格式不正确或参数错误，请检查后重试';
                } else if (response.status === 500) {
                    friendlyMessage = '❌ 服务器内部错误，请稍后重试';
                }

                showToast(friendlyMessage, 'danger');
            }
        }
    } catch (error) {
        console.error('添加图片关键词失败:', error);
        showToast('添加图片关键词失败', 'danger');
    } finally {
        toggleLoading(false);
    }
}

// 显示图片模态框
function showImageModal(imageUrl) {
    // 创建模态框HTML
    const modalHtml = `
        <div class="modal fade" id="imageViewModal" tabindex="-1">
            <div class="modal-dialog modal-lg modal-dialog-centered">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">图片预览</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body text-center">
                        <img src="${imageUrl}" alt="关键词图片" style="max-width: 100%; max-height: 70vh; border-radius: 8px;">
                    </div>
                </div>
            </div>
        </div>
    `;

    // 移除已存在的模态框
    const existingModal = document.getElementById('imageViewModal');
    if (existingModal) {
        existingModal.remove();
    }

    // 添加新模态框
    document.body.insertAdjacentHTML('beforeend', modalHtml);

    // 显示模态框
    const modal = new bootstrap.Modal(document.getElementById('imageViewModal'));
    modal.show();

    // 模态框关闭后移除DOM元素
    document.getElementById('imageViewModal').addEventListener('hidden.bs.modal', function() {
        this.remove();
    });
}

// 编辑图片关键词（不允许修改）
function editImageKeyword(index) {
    showToast('图片关键词不允许修改，请删除后重新添加', 'warning');
}

// 修改导出关键词函数，使用后端导出API
async function exportKeywords() {
    if (!currentCookieId) {
        showToast('请先选择账号', 'warning');
        return;
    }

    try {
        toggleLoading(true);

        // 使用后端导出API
        const response = await fetch(`${apiBase}/keywords-export/${currentCookieId}`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            // 获取文件blob
            const blob = await response.blob();

            // 从响应头获取文件名
            const contentDisposition = response.headers.get('Content-Disposition');
            let fileName = `关键词数据_${currentCookieId}_${new Date().toISOString().slice(0, 10)}.xlsx`;

            if (contentDisposition) {
                const fileNameMatch = contentDisposition.match(/filename\*=UTF-8''(.+)/);
                if (fileNameMatch) {
                    fileName = decodeURIComponent(fileNameMatch[1]);
                }
            }

            // 创建下载链接
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = fileName;
            document.body.appendChild(a);
            a.click();

            // 清理
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            showToast('✅ 关键词导出成功', 'success');
        } else {
            const errorText = await response.text();
            console.error('导出关键词失败:', errorText);
            showToast('导出关键词失败', 'danger');
        }
    } catch (error) {
        console.error('导出关键词失败:', error);
        showToast('导出关键词失败', 'danger');
    } finally {
        toggleLoading(false);
    }
}

// ==================== 备注管理功能 ====================

// 编辑备注
function editRemark(cookieId, currentRemark) {
    console.log('editRemark called:', cookieId, currentRemark); // 调试信息
    const remarkCell = document.querySelector(`[data-cookie-id="${cookieId}"] .remark-display`);
    if (!remarkCell) {
        console.log('remarkCell not found'); // 调试信息
        return;
    }

    // 创建输入框
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'form-control form-control-sm';
    input.value = currentRemark || '';
    input.placeholder = '请输入备注...';
    input.style.fontSize = '0.875rem';
    input.maxLength = 100; // 限制备注长度

    // 保存原始内容和原始值
    const originalContent = remarkCell.innerHTML;
    const originalValue = currentRemark || '';

    // 标记是否已经进行了编辑
    let hasChanged = false;
    let isProcessing = false; // 防止重复处理

    // 替换为输入框
    remarkCell.innerHTML = '';
    remarkCell.appendChild(input);

    // 监听输入变化
    input.addEventListener('input', () => {
        hasChanged = input.value.trim() !== originalValue;
    });

    // 保存函数
    const saveRemark = async () => {
        console.log('saveRemark called, isProcessing:', isProcessing, 'hasChanged:', hasChanged); // 调试信息
        if (isProcessing) return; // 防止重复调用

        const newRemark = input.value.trim();
        console.log('newRemark:', newRemark, 'originalValue:', originalValue); // 调试信息

        // 如果没有变化，直接恢复显示
        if (!hasChanged || newRemark === originalValue) {
            console.log('No changes detected, restoring original content'); // 调试信息
            remarkCell.innerHTML = originalContent;
            return;
        }

        isProcessing = true;

        try {
            const response = await fetch(`${apiBase}/cookies/${cookieId}/remark`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${authToken}`
                },
                body: JSON.stringify({ remark: newRemark })
            });

            if (response.ok) {
                // 更新显示
                remarkCell.innerHTML = `
                    <span class="remark-display" onclick="editRemark('${cookieId}', '${newRemark.replace(/'/g, '&#39;')}')" title="点击编辑备注" style="cursor: pointer; color: #6c757d; font-size: 0.875rem;">
                        ${newRemark || '<i class="bi bi-plus-circle text-muted"></i> 添加备注'}
                    </span>
                `;
                showToast('备注更新成功', 'success');
            } else {
                const errorData = await response.json();
                showToast(`备注更新失败: ${errorData.detail || '未知错误'}`, 'danger');
                // 恢复原始内容
                remarkCell.innerHTML = originalContent;
            }
        } catch (error) {
            console.error('更新备注失败:', error);
            showToast('备注更新失败', 'danger');
            // 恢复原始内容
            remarkCell.innerHTML = originalContent;
        } finally {
            isProcessing = false;
        }
    };

    // 取消函数
    const cancelEdit = () => {
        if (isProcessing) return;
        remarkCell.innerHTML = originalContent;
    };

    // 延迟绑定blur事件，避免立即触发
    setTimeout(() => {
        input.addEventListener('blur', saveRemark);
    }, 100);

    // 绑定键盘事件
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            saveRemark();
        } else if (e.key === 'Escape') {
            e.preventDefault();
            cancelEdit();
        }
    });

    // 聚焦并选中文本
    input.focus();
    input.select();
}

// 编辑暂停时间
function editPauseDuration(cookieId, currentDuration) {
    console.log('editPauseDuration called:', cookieId, currentDuration); // 调试信息
    const pauseCell = document.querySelector(`[data-cookie-id="${cookieId}"] .pause-duration-display`);
    if (!pauseCell) {
        console.log('pauseCell not found'); // 调试信息
        return;
    }

    // 创建输入框
    const input = document.createElement('input');
    input.type = 'number';
    input.className = 'form-control form-control-sm';
    input.value = currentDuration || 10;
    input.placeholder = '请输入暂停时间...';
    input.style.fontSize = '0.875rem';
    input.min = 1;
    input.max = 60;
    input.step = 1;

    // 保存原始内容和原始值
    const originalContent = pauseCell.innerHTML;
    const originalValue = currentDuration || 10;

    // 标记是否已经进行了编辑
    let hasChanged = false;
    let isProcessing = false; // 防止重复处理

    // 替换为输入框
    pauseCell.innerHTML = '';
    pauseCell.appendChild(input);

    // 监听输入变化
    input.addEventListener('input', () => {
        const newValue = parseInt(input.value) || 10;
        hasChanged = newValue !== originalValue;
    });

    // 保存函数
    const savePauseDuration = async () => {
        console.log('savePauseDuration called, isProcessing:', isProcessing, 'hasChanged:', hasChanged); // 调试信息
        if (isProcessing) return; // 防止重复调用

        const newDuration = parseInt(input.value) || 10;
        console.log('newDuration:', newDuration, 'originalValue:', originalValue); // 调试信息

        // 验证范围
        if (newDuration < 1 || newDuration > 60) {
            showToast('暂停时间必须在1-60分钟之间', 'warning');
            input.focus();
            return;
        }

        // 如果没有变化，直接恢复显示
        if (!hasChanged || newDuration === originalValue) {
            console.log('No changes detected, restoring original content'); // 调试信息
            pauseCell.innerHTML = originalContent;
            return;
        }

        isProcessing = true;

        try {
            const response = await fetch(`${apiBase}/cookies/${cookieId}/pause-duration`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${authToken}`
                },
                body: JSON.stringify({ pause_duration: newDuration })
            });

            if (response.ok) {
                // 更新显示
                pauseCell.innerHTML = `
                    <span class="pause-duration-display" onclick="editPauseDuration('${cookieId}', ${newDuration})" title="点击编辑暂停时间" style="cursor: pointer; color: #6c757d; font-size: 0.875rem;">
                        <i class="bi bi-clock me-1"></i>${newDuration}分钟
                    </span>
                `;
                showToast('暂停时间更新成功', 'success');
            } else {
                const errorData = await response.json();
                showToast(`暂停时间更新失败: ${errorData.detail || '未知错误'}`, 'danger');
                // 恢复原始内容
                pauseCell.innerHTML = originalContent;
            }
        } catch (error) {
            console.error('更新暂停时间失败:', error);
            showToast('暂停时间更新失败', 'danger');
            // 恢复原始内容
            pauseCell.innerHTML = originalContent;
        } finally {
            isProcessing = false;
        }
    };

    // 取消函数
    const cancelEdit = () => {
        if (isProcessing) return;
        pauseCell.innerHTML = originalContent;
    };

    // 延迟绑定blur事件，避免立即触发
    setTimeout(() => {
        input.addEventListener('blur', savePauseDuration);
    }, 100);

    // 绑定键盘事件
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            savePauseDuration();
        } else if (e.key === 'Escape') {
            e.preventDefault();
            cancelEdit();
        }
    });

    // 聚焦并选中文本
    input.focus();
    input.select();
}

// ==================== 工具提示初始化 ====================

// 初始化工具提示
function initTooltips() {
    // 初始化所有工具提示
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// ==================== 系统设置功能 ====================

// 加载系统设置
async function loadSystemSettings() {
    console.log('加载系统设置');

    // 通过验证接口获取用户信息（更可靠）
    try {
        const response = await fetch(`${apiBase}/verify`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            const result = await response.json();
            const isAdmin = result.is_admin === true;

            console.log('用户信息:', result, '是否管理员:', isAdmin);

            // 显示/隐藏注册设置和外发配置（仅管理员可见）
            const registrationSettings = document.getElementById('registration-settings');
            const outgoingConfigs = document.getElementById('outgoing-configs');
            if (registrationSettings) {
                registrationSettings.style.display = isAdmin ? 'block' : 'none';
            }
            if (outgoingConfigs) {
                outgoingConfigs.style.display = isAdmin ? 'block' : 'none';
            }

            // 如果是管理员，加载注册设置、登录信息设置和外发配置
            if (isAdmin) {
                await loadRegistrationSettings();
                await loadLoginInfoSettings();
                await loadOutgoingConfigs();
            }
        }
    } catch (error) {
        console.error('获取用户信息失败:', error);
        // 出错时隐藏管理员功能
        const registrationSettings = document.getElementById('registration-settings');
        if (registrationSettings) {
            registrationSettings.style.display = 'none';
        }
    }
}

// 加载外发配置
async function loadOutgoingConfigs() {
    try {
        const response = await fetch('/system-settings', {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        if (response.ok) {
            const settings = await response.json();
            
            // 渲染外发配置界面
            renderOutgoingConfigs(settings);
        }
    } catch (error) {
        console.error('加载外发配置失败:', error);
        showToast('加载外发配置失败', 'danger');
    }
}

// 渲染外发配置界面
function renderOutgoingConfigs(settings) {
    const container = document.getElementById('outgoing-configs');
    if (!container) return;
    
    let html = '<div class="row">';
    
    // 渲染SMTP配置
    const smtpConfig = outgoingConfigs.smtp;
    html += `
        <div class="col-12">
            <div class="card">
                <div class="card-header">
                    <h5 class="mb-0">
                        <i class="bi ${smtpConfig.icon} text-${smtpConfig.color} me-2"></i>
                        ${smtpConfig.title}
                    </h5>
                </div>
                <div class="card-body">
                    <p class="text-muted">${smtpConfig.description}</p>
                    <form id="smtp-config-form">
                        <div class="row">`;
    
    smtpConfig.fields.forEach(field => {
        const value = settings[field.id] || '';
        html += `
            <div class="col-md-6 mb-3">
                <label for="${field.id}" class="form-label">${field.label}</label>
                ${generateOutgoingFieldHtml(field, value)}
                <div class="form-text">${field.help}</div>
            </div>`;
    });
    
    html += `
                        </div>
                        <div class="text-end">
                            <button type="submit" class="btn btn-primary">
                                <i class="bi bi-save me-1"></i>保存SMTP配置
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>`;
    
    html += '</div>';
    container.innerHTML = html;
    
    // 绑定表单提交事件
    const form = document.getElementById('smtp-config-form');
    if (form) {
        form.addEventListener('submit', saveOutgoingConfigs);
    }
}

// 生成外发配置字段HTML
function generateOutgoingFieldHtml(field, value) {
    switch (field.type) {
        case 'select':
            let options = '';
            field.options.forEach(option => {
                const selected = value === option.value ? 'selected' : '';
                options += `<option value="${option.value}" ${selected}>${option.text}</option>`;
            });
            return `<select class="form-select" id="${field.id}" name="${field.id}" ${field.required ? 'required' : ''}>${options}</select>`;
        
        case 'password':
            return `<input type="password" class="form-control" id="${field.id}" name="${field.id}" value="${value}" placeholder="${field.placeholder}" ${field.required ? 'required' : ''}>`;
        
        case 'number':
            return `<input type="number" class="form-control" id="${field.id}" name="${field.id}" value="${value}" placeholder="${field.placeholder}" ${field.required ? 'required' : ''}>`;
        
        case 'email':
            return `<input type="email" class="form-control" id="${field.id}" name="${field.id}" value="${value}" placeholder="${field.placeholder}" ${field.required ? 'required' : ''}>`;
        
        default:
            return `<input type="text" class="form-control" id="${field.id}" name="${field.id}" value="${value}" placeholder="${field.placeholder}" ${field.required ? 'required' : ''}>`;
    }
}

// 保存外发配置
async function saveOutgoingConfigs(event) {
    event.preventDefault();
    
    const form = event.target;
    const formData = new FormData(form);
    const configs = {};
    
    // 收集表单数据
    for (let [key, value] of formData.entries()) {
        configs[key] = value;
    }
    
    try {
        // 逐个保存配置项
        for (const [key, value] of Object.entries(configs)) {
            const response = await fetch(`/system-settings/${key}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${authToken}`
                },
                body: JSON.stringify({
                    key: key,
                    value: value,
                    description: `SMTP配置 - ${key}`
                })
            });
            
            if (!response.ok) {
                throw new Error(`保存${key}失败`);
            }
        }
        
        showToast('外发配置保存成功', 'success');
        
        // 重新加载配置
        await loadOutgoingConfigs();
        
    } catch (error) {
        console.error('保存外发配置失败:', error);
        showToast('保存外发配置失败: ' + error.message, 'danger');
    }
}

// 加载注册设置
async function loadRegistrationSettings() {
    try {
        const response = await fetch('/registration-status');
        if (response.ok) {
            const data = await response.json();
            const checkbox = document.getElementById('registrationEnabled');
            if (checkbox) {
                checkbox.checked = data.enabled;
            }
        }
    } catch (error) {
        console.error('加载注册设置失败:', error);
        showToast('加载注册设置失败', 'danger');
    }
}

// 更新注册设置
async function updateRegistrationSettings() {
    const checkbox = document.getElementById('registrationEnabled');
    const statusDiv = document.getElementById('registrationStatus');
    const statusText = document.getElementById('registrationStatusText');

    if (!checkbox) return;

    const enabled = checkbox.checked;

    try {
        const response = await fetch('/registration-settings', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify({ enabled: enabled })
        });

        if (response.ok) {
            const data = await response.json();
            showToast(data.message, 'success');

            // 显示状态信息
            if (statusDiv && statusText) {
                statusText.textContent = data.message;
                statusDiv.style.display = 'block';

                // 3秒后隐藏状态信息
                setTimeout(() => {
                    statusDiv.style.display = 'none';
                }, 3000);
            }
        } else {
            const errorData = await response.json();
            showToast(`更新失败: ${errorData.detail || '未知错误'}`, 'danger');
        }
    } catch (error) {
        console.error('更新注册设置失败:', error);
        showToast('更新注册设置失败', 'danger');
    }
}

// 加载默认登录信息设置
async function loadLoginInfoSettings() {
    try {
        const response = await fetch('/system-settings', {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            const settings = await response.json();
            const checkbox = document.getElementById('showDefaultLoginInfo');

            if (checkbox && settings.show_default_login_info !== undefined) {
                checkbox.checked = settings.show_default_login_info === 'true';
            }
        }
    } catch (error) {
        console.error('加载登录信息设置失败:', error);
        showToast('加载登录信息设置失败', 'danger');
    }
}

// 更新默认登录信息设置
async function updateLoginInfoSettings() {
    const checkbox = document.getElementById('showDefaultLoginInfo');
    const statusDiv = document.getElementById('loginInfoStatus');
    const statusText = document.getElementById('loginInfoStatusText');

    if (!checkbox) return;

    const enabled = checkbox.checked;

    try {
        const response = await fetch('/login-info-settings', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify({
                enabled: enabled
            })
        });

        if (response.ok) {
            const data = await response.json();
            const message = enabled ? '默认登录信息显示已开启' : '默认登录信息显示已关闭';
            showToast(message, 'success');

            // 显示状态信息
            if (statusDiv && statusText) {
                statusText.textContent = message;
                statusDiv.style.display = 'block';

                // 3秒后隐藏状态信息
                setTimeout(() => {
                    statusDiv.style.display = 'none';
                }, 3000);
            }
        } else {
            const errorData = await response.json();
            showToast(`更新失败: ${errorData.detail || '未知错误'}`, 'danger');
        }
    } catch (error) {
        console.error('更新登录信息设置失败:', error);
        showToast('更新登录信息设置失败', 'danger');
    }
}

// ================================
// 订单管理功能
// ================================

// 加载订单列表
async function loadOrders() {
    try {
        // 先加载Cookie列表用于筛选
        await loadOrderCookieFilter();

        // 加载订单列表
        await refreshOrdersData();
    } catch (error) {
        console.error('加载订单列表失败:', error);
        showToast('加载订单列表失败', 'danger');
    }
}

// 只刷新订单数据，不重新加载筛选器
async function refreshOrdersData() {
    try {
        const selectedCookie = document.getElementById('orderCookieFilter').value;
        if (selectedCookie) {
            await loadOrdersByCookie();
        } else {
            await loadAllOrders();
        }
    } catch (error) {
        console.error('刷新订单数据失败:', error);
        showToast('刷新订单数据失败', 'danger');
    }
}

// 加载Cookie筛选选项
async function loadOrderCookieFilter() {
    try {
        const response = await fetch(`${apiBase}/admin/data/orders`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        const data = await response.json();
        if (data.success && data.data) {
            // 提取唯一的cookie_id
            const cookieIds = [...new Set(data.data.map(order => order.cookie_id).filter(id => id))];

            const select = document.getElementById('orderCookieFilter');
            if (select) {
                select.innerHTML = '<option value="">所有账号</option>';

                cookieIds.forEach(cookieId => {
                    const option = document.createElement('option');
                    option.value = cookieId;
                    option.textContent = cookieId;
                    select.appendChild(option);
                });
            }
        }
    } catch (error) {
        console.error('加载Cookie选项失败:', error);
    }
}

// 加载所有订单
async function loadAllOrders() {
    try {
        const response = await fetch(`${apiBase}/admin/data/orders`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        const data = await response.json();
        if (data.success) {
            allOrdersData = data.data || [];
            // 按创建时间倒序排列
            allOrdersData.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

            // 应用当前筛选条件
            filterOrders();
        } else {
            console.error('加载订单失败:', data.message);
            showToast('加载订单数据失败: ' + data.message, 'danger');
        }
    } catch (error) {
        console.error('加载订单失败:', error);
        showToast('加载订单数据失败，请检查网络连接', 'danger');
    }
}

// 根据Cookie加载订单
async function loadOrdersByCookie() {
    const selectedCookie = document.getElementById('orderCookieFilter').value;
    if (!selectedCookie) {
        await loadAllOrders();
        return;
    }

    try {
        const response = await fetch(`${apiBase}/admin/data/orders`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        const data = await response.json();
        if (data.success) {
            // 筛选指定Cookie的订单
            allOrdersData = (data.data || []).filter(order => order.cookie_id === selectedCookie);
            // 按创建时间倒序排列
            allOrdersData.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

            // 应用当前筛选条件
            filterOrders();
        } else {
            console.error('加载订单失败:', data.message);
            showToast('加载订单数据失败: ' + data.message, 'danger');
        }
    } catch (error) {
        console.error('加载订单失败:', error);
        showToast('加载订单数据失败，请检查网络连接', 'danger');
    }
}

// 筛选订单
function filterOrders() {
    const searchKeyword = document.getElementById('orderSearchInput')?.value.toLowerCase() || '';
    const statusFilter = document.getElementById('orderStatusFilter')?.value || '';

    filteredOrdersData = allOrdersData.filter(order => {
        // 搜索关键词筛选（订单ID或商品ID）
        const matchesSearch = !searchKeyword ||
            (order.order_id && order.order_id.toLowerCase().includes(searchKeyword)) ||
            (order.item_id && order.item_id.toLowerCase().includes(searchKeyword));

        // 状态筛选
        const matchesStatus = !statusFilter || order.order_status === statusFilter;

        return matchesSearch && matchesStatus;
    });

    currentOrderSearchKeyword = searchKeyword;
    currentOrdersPage = 1; // 重置到第一页

    updateOrdersDisplay();
}

// 更新订单显示
function updateOrdersDisplay() {
    displayOrders();
    updateOrdersPagination();
    updateOrdersSearchStats();
}

// 显示订单列表
function displayOrders() {
    const tbody = document.getElementById('ordersTableBody');
    if (!tbody) return;

    if (filteredOrdersData.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="10" class="text-center text-muted py-4">
                    <i class="bi bi-inbox display-6 d-block mb-2"></i>
                    ${currentOrderSearchKeyword ? '没有找到匹配的订单' : '暂无订单数据'}
                </td>
            </tr>
        `;
        return;
    }

    // 计算分页
    totalOrdersPages = Math.ceil(filteredOrdersData.length / ordersPerPage);
    const startIndex = (currentOrdersPage - 1) * ordersPerPage;
    const endIndex = startIndex + ordersPerPage;
    const pageOrders = filteredOrdersData.slice(startIndex, endIndex);

    // 生成表格行
    tbody.innerHTML = pageOrders.map(order => createOrderRow(order)).join('');
}

// 创建订单行HTML
function createOrderRow(order) {
    const statusClass = getOrderStatusClass(order.order_status);
    const statusText = getOrderStatusText(order.order_status);

    return `
        <tr>
            <td>
                <input type="checkbox" class="order-checkbox" value="${order.order_id}">
            </td>
            <td>
                <span class="text-truncate d-inline-block" style="max-width: 120px;" title="${order.order_id}">
                    ${order.order_id}
                </span>
            </td>
            <td>
                <span class="text-truncate d-inline-block" style="max-width: 100px;" title="${order.item_id || ''}">
                    ${order.item_id || '-'}
                </span>
            </td>
            <td>
                <span class="text-truncate d-inline-block" style="max-width: 80px;" title="${order.buyer_id || ''}">
                    ${order.buyer_id || '-'}
                </span>
            </td>
            <td>
                ${order.spec_name && order.spec_value ?
                    `<small class="text-muted">${order.spec_name}:</small><br>${order.spec_value}` :
                    '-'
                }
            </td>
            <td>${order.quantity || '-'}</td>
            <td>
                <span class="text-success fw-bold">¥${order.amount || '0.00'}</span>
            </td>
            <td>
                <span class="badge ${statusClass}">${statusText}</span>
            </td>
            <td>
                <span class="text-truncate d-inline-block" style="max-width: 80px;" title="${order.cookie_id || ''}">
                    ${order.cookie_id || '-'}
                </span>
            </td>
            <td>
                <div class="btn-group btn-group-sm" role="group">
                    <button class="btn btn-outline-primary btn-sm" onclick="showOrderDetail('${order.order_id}')" title="查看详情">
                        <i class="bi bi-eye"></i>
                    </button>
                    <button class="btn btn-outline-danger btn-sm" onclick="deleteOrder('${order.order_id}')" title="删除">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </td>
        </tr>
    `;
}

// 获取订单状态样式类
function getOrderStatusClass(status) {
    const statusMap = {
        'processing': 'bg-warning text-dark',
        'processed': 'bg-info text-white',
        'completed': 'bg-success text-white',
        'unknown': 'bg-secondary text-white'
    };
    return statusMap[status] || 'bg-secondary text-white';
}

// 获取订单状态文本
function getOrderStatusText(status) {
    const statusMap = {
        'processing': '处理中',
        'processed': '已处理',
        'completed': '已完成',
        'unknown': '未知'
    };
    return statusMap[status] || '未知';
}

// 更新订单分页
function updateOrdersPagination() {
    const pageInfo = document.getElementById('ordersPageInfo');
    const pageInput = document.getElementById('ordersPageInput');
    const totalPagesSpan = document.getElementById('ordersTotalPages');

    if (pageInfo) {
        const startIndex = (currentOrdersPage - 1) * ordersPerPage + 1;
        const endIndex = Math.min(currentOrdersPage * ordersPerPage, filteredOrdersData.length);
        pageInfo.textContent = `显示第 ${startIndex}-${endIndex} 条，共 ${filteredOrdersData.length} 条记录`;
    }

    if (pageInput) {
        pageInput.value = currentOrdersPage;
    }

    if (totalPagesSpan) {
        totalPagesSpan.textContent = totalOrdersPages;
    }

    // 更新分页按钮状态
    const firstPageBtn = document.getElementById('ordersFirstPage');
    const prevPageBtn = document.getElementById('ordersPrevPage');
    const nextPageBtn = document.getElementById('ordersNextPage');
    const lastPageBtn = document.getElementById('ordersLastPage');

    if (firstPageBtn) firstPageBtn.disabled = currentOrdersPage === 1;
    if (prevPageBtn) prevPageBtn.disabled = currentOrdersPage === 1;
    if (nextPageBtn) nextPageBtn.disabled = currentOrdersPage === totalOrdersPages || totalOrdersPages === 0;
    if (lastPageBtn) lastPageBtn.disabled = currentOrdersPage === totalOrdersPages || totalOrdersPages === 0;
}

// 更新搜索统计信息
function updateOrdersSearchStats() {
    const searchStats = document.getElementById('orderSearchStats');
    const searchStatsText = document.getElementById('orderSearchStatsText');

    if (searchStats && searchStatsText) {
        if (currentOrderSearchKeyword) {
            searchStatsText.textContent = `搜索 "${currentOrderSearchKeyword}" 找到 ${filteredOrdersData.length} 个结果`;
            searchStats.style.display = 'block';
        } else {
            searchStats.style.display = 'none';
        }
    }
}

// 跳转到指定页面
function goToOrdersPage(page) {
    if (page < 1 || page > totalOrdersPages) return;

    currentOrdersPage = page;
    updateOrdersDisplay();
}

// 初始化订单搜索功能
function initOrdersSearch() {
    // 初始化分页大小
    const pageSizeSelect = document.getElementById('ordersPageSize');
    if (pageSizeSelect) {
        ordersPerPage = parseInt(pageSizeSelect.value) || 20;
        pageSizeSelect.addEventListener('change', changeOrdersPageSize);
    }

    // 初始化搜索输入框事件监听器
    const searchInput = document.getElementById('orderSearchInput');
    if (searchInput) {
        // 使用防抖来避免频繁搜索
        let searchTimeout;
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                filterOrders();
            }, 300); // 300ms 防抖延迟
        });
    }

    // 初始化页面输入框事件监听器
    const pageInput = document.getElementById('ordersPageInput');
    if (pageInput) {
        pageInput.addEventListener('keydown', handleOrdersPageInput);
    }
}

// 处理分页大小变化
function changeOrdersPageSize() {
    const pageSizeSelect = document.getElementById('ordersPageSize');
    if (pageSizeSelect) {
        ordersPerPage = parseInt(pageSizeSelect.value) || 20;
        currentOrdersPage = 1; // 重置到第一页
        updateOrdersDisplay();
    }
}

// 处理页面输入
function handleOrdersPageInput(event) {
    if (event.key === 'Enter') {
        const pageInput = document.getElementById('ordersPageInput');
        if (pageInput) {
            const page = parseInt(pageInput.value);
            if (page >= 1 && page <= totalOrdersPages) {
                goToOrdersPage(page);
            } else {
                pageInput.value = currentOrdersPage; // 恢复当前页码
                showToast('页码超出范围', 'warning');
            }
        }
    }
}

// 刷新订单列表
async function refreshOrders() {
    await refreshOrdersData();
    showToast('订单列表已刷新', 'success');
}

// 清空订单筛选条件
function clearOrderFilters() {
    const searchInput = document.getElementById('orderSearchInput');
    const statusFilter = document.getElementById('orderStatusFilter');
    const cookieFilter = document.getElementById('orderCookieFilter');

    if (searchInput) searchInput.value = '';
    if (statusFilter) statusFilter.value = '';
    if (cookieFilter) cookieFilter.value = '';

    filterOrders();
    showToast('筛选条件已清空', 'info');
}

// 显示订单详情
async function showOrderDetail(orderId) {
    try {
        const order = allOrdersData.find(o => o.order_id === orderId);
        if (!order) {
            showToast('订单不存在', 'warning');
            return;
        }

        // 创建模态框内容
        const modalContent = `
            <div class="modal fade" id="orderDetailModal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">
                                <i class="bi bi-receipt-cutoff me-2"></i>
                                订单详情
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="row">
                                <div class="col-md-6">
                                    <h6>基本信息</h6>
                                    <table class="table table-sm">
                                        <tr><td>订单ID</td><td>${order.order_id}</td></tr>
                                        <tr><td>商品ID</td><td>${order.item_id || '未知'}</td></tr>
                                        <tr><td>买家ID</td><td>${order.buyer_id || '未知'}</td></tr>
                                        <tr><td>买家昵称</td><td>${order.buyer_nickName || '未知'}</td></tr>
                                        <tr><td>买家姓名</td><td>${order.buyer_name || '未知'}</td></tr>
                                        <tr><td>买家电话</td><td>${order.buyer_phone || '未知'}</td></tr>
                                        <tr><td>买家地址</td><td>${order.buyer_address || '未知'}</td></tr>
                                        <tr><td>Cookie账号</td><td>${order.cookie_id || '未知'}</td></tr>
                                        <tr><td>订单状态</td><td><span class="badge ${getOrderStatusClass(order.order_status)}">${getOrderStatusText(order.order_status)}</span></td></tr>
                                    </table>
                                </div>
                                <div class="col-md-6">
                                    <h6>商品信息</h6>
                                    <table class="table table-sm">
                                        <tr><td>规格名称</td><td>${order.spec_name || '无'}</td></tr>
                                        <tr><td>规格值</td><td>${order.spec_value || '无'}</td></tr>
                                        <tr><td>数量</td><td>${order.quantity || '1'}</td></tr>
                                        <tr><td>金额</td><td>¥${order.amount || '0.00'}</td></tr>
                                    </table>
                                </div>
                            </div>
                            <div class="row mt-3">
                                <div class="col-12">
                                    <h6>时间信息</h6>
                                    <table class="table table-sm">
                                        <tr><td>创建时间</td><td>${formatDateTime(order.created_at)}</td></tr>
                                        <tr><td>更新时间</td><td>${formatDateTime(order.updated_at)}</td></tr>
                                    </table>
                                </div>
                            </div>
                            <div class="row mt-3">
                                <div class="col-12">
                                    <h6>商品详情</h6>
                                    <div id="itemDetailContent">
                                        <div class="text-center">
                                            <div class="spinner-border spinner-border-sm" role="status">
                                                <span class="visually-hidden">加载中...</span>
                                            </div>
                                            <span class="ms-2">正在加载商品详情...</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // 移除已存在的模态框
        const existingModal = document.getElementById('orderDetailModal');
        if (existingModal) {
            existingModal.remove();
        }

        // 添加新模态框到页面
        document.body.insertAdjacentHTML('beforeend', modalContent);

        // 显示模态框
        const modal = new bootstrap.Modal(document.getElementById('orderDetailModal'));
        modal.show();

        // 异步加载商品详情
        if (order.item_id) {
            loadItemDetailForOrder(order.item_id, order.cookie_id);
        }

    } catch (error) {
        console.error('显示订单详情失败:', error);
        showToast('显示订单详情失败', 'danger');
    }
}

// 为订单加载商品详情
async function loadItemDetailForOrder(itemId, cookieId) {
    try {
        const token = localStorage.getItem('auth_token');

        // 尝试从数据库获取商品信息
        let response = await fetch(`${apiBase}/items/${cookieId}/${itemId}`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        const content = document.getElementById('itemDetailContent');
        if (!content) return;

        if (response.ok) {
            const data = await response.json();
            const item = data.item;

            content.innerHTML = `
                <div class="card">
                    <div class="card-body">
                        <h6 class="card-title">${item.item_title || '商品标题未知'}</h6>
                        <p class="card-text">${item.item_description || '暂无描述'}</p>
                        <div class="row">
                            <div class="col-md-6">
                                <small class="text-muted">分类：${item.item_category || '未知'}</small>
                            </div>
                            <div class="col-md-6">
                                <small class="text-muted">价格：${item.item_price || '未知'}</small>
                            </div>
                        </div>
                        ${item.item_detail ? `
                            <div class="mt-2">
                                <small class="text-muted">详情：</small>
                                <div class="border p-2 mt-1" style="max-height: 200px; overflow-y: auto;">
                                    <small>${item.item_detail}</small>
                                </div>
                            </div>
                        ` : ''}
                    </div>
                </div>
            `;
        } else {
            content.innerHTML = `
                <div class="alert alert-warning">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    无法获取商品详情信息
                </div>
            `;
        }
    } catch (error) {
        console.error('加载商品详情失败:', error);
        const content = document.getElementById('itemDetailContent');
        if (content) {
            content.innerHTML = `
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    加载商品详情失败：${error.message}
                </div>
            `;
        }
    }
}

// 删除订单
async function deleteOrder(orderId) {
    try {
        const confirmed = confirm(`确定要删除订单吗？\n\n订单ID: ${orderId}\n\n此操作不可撤销！`);
        if (!confirmed) {
            return;
        }

        const response = await fetch(`${apiBase}/admin/data/orders/delete`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify({ record_id: orderId })
        });

        if (response.ok) {
            showToast('订单删除成功', 'success');
            // 刷新列表
            await refreshOrdersData();
        } else {
            const error = await response.text();
            showToast(`删除失败: ${error}`, 'danger');
        }
    } catch (error) {
        console.error('删除订单失败:', error);
        showToast('删除订单失败', 'danger');
    }
}

// 批量删除订单
async function batchDeleteOrders() {
    const checkboxes = document.querySelectorAll('.order-checkbox:checked');
    if (checkboxes.length === 0) {
        showToast('请先选择要删除的订单', 'warning');
        return;
    }

    const orderIds = Array.from(checkboxes).map(cb => cb.value);
    const confirmed = confirm(`确定要删除选中的 ${orderIds.length} 个订单吗？\n\n此操作不可撤销！`);

    if (!confirmed) return;

    try {
        let successCount = 0;
        let failCount = 0;

        for (const orderId of orderIds) {
            try {
                const response = await fetch(`${apiBase}/admin/data/orders/delete`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${authToken}`
                    },
                    body: JSON.stringify({ record_id: orderId })
                });

                if (response.ok) {
                    successCount++;
                } else {
                    failCount++;
                }
            } catch (error) {
                failCount++;
            }
        }

        if (successCount > 0) {
            showToast(`成功删除 ${successCount} 个订单${failCount > 0 ? `，${failCount} 个失败` : ''}`,
                     failCount > 0 ? 'warning' : 'success');
            await refreshOrdersData();
        } else {
            showToast('批量删除失败', 'danger');
        }

    } catch (error) {
        console.error('批量删除订单失败:', error);
        showToast('批量删除订单失败', 'danger');
    }
}

// 切换全选订单
function toggleSelectAllOrders(checkbox) {
    const orderCheckboxes = document.querySelectorAll('.order-checkbox');
    orderCheckboxes.forEach(cb => {
        cb.checked = checkbox.checked;
    });

    updateBatchDeleteOrdersButton();
}

// 更新批量删除按钮状态
function updateBatchDeleteOrdersButton() {
    const checkboxes = document.querySelectorAll('.order-checkbox:checked');
    const batchDeleteBtn = document.getElementById('batchDeleteOrdersBtn');

    if (batchDeleteBtn) {
        batchDeleteBtn.disabled = checkboxes.length === 0;
    }
}

// 格式化日期时间
function formatDateTime(dateString) {
    if (!dateString) return '未知时间';

    try {
        const date = new Date(dateString);
        return date.toLocaleString('zh-CN', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch (error) {
        return dateString;
    }
}

// 页面加载完成后初始化订单搜索功能
document.addEventListener('DOMContentLoaded', function() {
    // 延迟初始化，确保DOM完全加载
    setTimeout(() => {
        initOrdersSearch();

        // 绑定复选框变化事件
        document.addEventListener('change', function(e) {
            if (e.target.classList.contains('order-checkbox')) {
                updateBatchDeleteOrdersButton();
            }
        });
    }, 100);
});

// ================================
// 用户管理功能
// ================================

// 加载用户管理页面
async function loadUserManagement() {
    console.log('加载用户管理页面');

    // 检查管理员权限
    try {
        const response = await fetch(`${apiBase}/verify`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            const result = await response.json();
            if (!result.is_admin) {
                showToast('您没有权限访问用户管理功能', 'danger');
                showSection('dashboard'); // 跳转回仪表盘
                return;
            }
        } else {
            showToast('权限验证失败', 'danger');
            return;
        }
    } catch (error) {
        console.error('权限验证失败:', error);
        showToast('权限验证失败', 'danger');
        return;
    }

    // 加载数据
    await loadUserSystemStats();
    await loadUsers();
}

// 加载用户系统统计信息
async function loadUserSystemStats() {
    try {
        const token = localStorage.getItem('auth_token');

        // 获取用户统计
        const usersResponse = await fetch('/admin/users', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (usersResponse.ok) {
            const usersData = await usersResponse.json();
            document.getElementById('totalUsers').textContent = usersData.users.length;
        }

        // 获取Cookie统计
        const cookiesResponse = await fetch(`${apiBase}/admin/data/cookies`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (cookiesResponse.ok) {
            const cookiesData = await cookiesResponse.json();
            document.getElementById('totalUserCookies').textContent = cookiesData.data ? cookiesData.data.length : 0;
        }

        // 获取卡券统计
        const cardsResponse = await fetch(`${apiBase}/admin/data/cards`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (cardsResponse.ok) {
            const cardsData = await cardsResponse.json();
            document.getElementById('totalUserCards').textContent = cardsData.data ? cardsData.data.length : 0;
        }

    } catch (error) {
        console.error('加载系统统计失败:', error);
    }
}

// 加载用户列表
async function loadUsers() {
    const loadingDiv = document.getElementById('loadingUsers');
    const usersListDiv = document.getElementById('usersList');
    const noUsersDiv = document.getElementById('noUsers');

    // 显示加载状态
    loadingDiv.style.display = 'block';
    usersListDiv.style.display = 'none';
    noUsersDiv.style.display = 'none';

    try {
        const token = localStorage.getItem('auth_token');
        const response = await fetch('/admin/users', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (response.ok) {
            const data = await response.json();
            loadingDiv.style.display = 'none';

            if (data.users && data.users.length > 0) {
                usersListDiv.style.display = 'block';
                displayUsers(data.users);
            } else {
                noUsersDiv.style.display = 'block';
            }
        } else {
            throw new Error('获取用户列表失败');
        }
    } catch (error) {
        console.error('加载用户列表失败:', error);
        loadingDiv.style.display = 'none';
        noUsersDiv.style.display = 'block';
        showToast('加载用户列表失败', 'danger');
    }
}

// 显示用户列表
function displayUsers(users) {
    const usersListDiv = document.getElementById('usersList');
    usersListDiv.innerHTML = '';

    users.forEach(user => {
        const userCard = createUserCard(user);
        usersListDiv.appendChild(userCard);
    });
}

// 创建用户卡片
function createUserCard(user) {
    const col = document.createElement('div');
    col.className = 'col-md-6 col-lg-4 mb-3';

    const isAdmin = user.username === 'admin';
    const badgeClass = isAdmin ? 'bg-danger' : 'bg-primary';
    const badgeText = isAdmin ? '管理员' : '普通用户';

    col.innerHTML = `
        <div class="card user-card h-100">
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <h6 class="card-title mb-0">${user.username}</h6>
                    <span class="badge ${badgeClass}">${badgeText}</span>
                </div>
                <p class="card-text text-muted small">
                    <i class="bi bi-envelope me-1"></i>${user.email || '未设置邮箱'}
                </p>
                <p class="card-text text-muted small">
                    <i class="bi bi-calendar me-1"></i>注册时间：${formatDateTime(user.created_at)}
                </p>
                <div class="d-flex justify-content-between align-items-center">
                    <small class="text-muted">
                        Cookie数: ${user.cookie_count || 0} |
                        卡券数: ${user.card_count || 0}
                    </small>
                    ${!isAdmin ? `
                        <button class="btn btn-outline-danger btn-sm" onclick="deleteUser('${user.id}', '${user.username}')">
                            <i class="bi bi-trash"></i>
                        </button>
                    ` : ''}
                </div>
            </div>
        </div>
    `;

    return col;
}

// 全局变量用于存储当前要删除的用户信息
let currentDeleteUserId = null;
let currentDeleteUserName = null;
let deleteUserModal = null;

// 删除用户
function deleteUser(userId, username) {
    if (username === 'admin') {
        showToast('不能删除管理员账号', 'warning');
        return;
    }

    // 存储要删除的用户信息
    currentDeleteUserId = userId;
    currentDeleteUserName = username;

    // 初始化模态框（如果还没有初始化）
    if (!deleteUserModal) {
        deleteUserModal = new bootstrap.Modal(document.getElementById('deleteUserModal'));
    }

    // 显示确认模态框
    deleteUserModal.show();
}

// 确认删除用户
async function confirmDeleteUser() {
    if (!currentDeleteUserId) return;

    try {
        const token = localStorage.getItem('auth_token');

        const response = await fetch(`/admin/users/${currentDeleteUserId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (response.ok) {
            const data = await response.json();
            deleteUserModal.hide();
            showToast(data.message || '用户删除成功', 'success');

            // 刷新页面数据
            await loadUserSystemStats();
            await loadUsers();
        } else {
            const errorData = await response.json();
            showToast(`删除失败: ${errorData.detail || '未知错误'}`, 'danger');
        }
    } catch (error) {
        console.error('删除用户失败:', error);
        showToast('删除用户失败', 'danger');
    } finally {
        // 清理状态
        currentDeleteUserId = null;
        currentDeleteUserName = null;
    }
}

// 刷新用户列表
async function refreshUsers() {
    await loadUserSystemStats();
    await loadUsers();
    showToast('用户列表已刷新', 'success');
}

// ================================
// 数据管理功能
// ================================

// 全局变量
let currentTable = '';
let currentData = [];

// 表的中文描述
const tableDescriptions = {
    'users': '用户表',
    'cookies': 'Cookie账号表',
    'cookie_status': 'Cookie状态表',
    'keywords': '关键字表',
    'item_replay': '指定商品回复表',
    'default_replies': '默认回复表',
    'default_reply_records': '默认回复记录表',
    'ai_reply_settings': 'AI回复设置表',
    'ai_conversations': 'AI对话历史表',
    'ai_item_cache': 'AI商品信息缓存表',
    'item_info': '商品信息表',
    'message_notifications': '消息通知表',
    'cards': '卡券表',
    'delivery_rules': '发货规则表',
    'notification_channels': '通知渠道表',
    'user_settings': '用户设置表',
    'system_settings': '系统设置表',
    'email_verifications': '邮箱验证表',
    'captcha_codes': '验证码表',
    'orders': '订单表'
};

// 加载数据管理页面
async function loadDataManagement() {
    console.log('加载数据管理页面');

    // 检查管理员权限
    try {
        const response = await fetch(`${apiBase}/verify`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            const result = await response.json();
            if (!result.is_admin) {
                showToast('您没有权限访问数据管理功能', 'danger');
                showSection('dashboard'); // 跳转回仪表盘
                return;
            }
        } else {
            showToast('权限验证失败', 'danger');
            return;
        }
    } catch (error) {
        console.error('权限验证失败:', error);
        showToast('权限验证失败', 'danger');
        return;
    }

    // 重置状态
    currentTable = '';
    currentData = [];

    // 重置界面
    showNoTableSelected();

    // 重置表格选择器
    const tableSelect = document.getElementById('tableSelect');
    if (tableSelect) {
        tableSelect.value = '';
    }
}

// 显示未选择表格状态
function showNoTableSelected() {
    document.getElementById('loadingTable').style.display = 'none';
    document.getElementById('noTableSelected').style.display = 'block';
    document.getElementById('noTableData').style.display = 'none';
    document.getElementById('tableContainer').style.display = 'none';

    // 重置统计信息
    document.getElementById('recordCount').textContent = '-';
    document.getElementById('tableTitle').innerHTML = '<i class="bi bi-table"></i> 数据表';

    // 禁用按钮
    document.getElementById('clearBtn').disabled = true;
}

// 显示加载状态
function showLoading() {
    document.getElementById('loadingTable').style.display = 'block';
    document.getElementById('noTableSelected').style.display = 'none';
    document.getElementById('noTableData').style.display = 'none';
    document.getElementById('tableContainer').style.display = 'none';
}

// 显示无数据状态
function showNoData() {
    document.getElementById('loadingTable').style.display = 'none';
    document.getElementById('noTableSelected').style.display = 'none';
    document.getElementById('noTableData').style.display = 'block';
    document.getElementById('tableContainer').style.display = 'none';
}

// 加载表数据
async function loadTableData() {
    const tableSelect = document.getElementById('tableSelect');
    const selectedTable = tableSelect.value;

    if (!selectedTable) {
        showNoTableSelected();
        return;
    }

    currentTable = selectedTable;
    showLoading();

    const token = localStorage.getItem('auth_token');

    try {
        const response = await fetch(`/admin/data/${selectedTable}`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        const data = await response.json();

        if (data.success) {
            currentData = data.data;
            displayTableData(data.data, data.columns);
            updateTableInfo(selectedTable, data.data.length);
        } else {
            showToast('加载数据失败: ' + data.message, 'danger');
            showNoData();
        }
    } catch (error) {
        console.error('加载数据失败:', error);
        showToast('加载数据失败', 'danger');
        showNoData();
    }
}

// 显示表格数据
function displayTableData(data, columns) {
    if (!data || data.length === 0) {
        showNoData();
        return;
    }

    // 显示表格容器
    document.getElementById('loadingTable').style.display = 'none';
    document.getElementById('noTableSelected').style.display = 'none';
    document.getElementById('noTableData').style.display = 'none';
    document.getElementById('tableContainer').style.display = 'block';

    // 生成表头（添加操作列）
    const tableHeaders = document.getElementById('tableHeaders');
    const headerHtml = columns.map(col => `<th>${col}</th>`).join('') + '<th width="100">操作</th>';
    tableHeaders.innerHTML = headerHtml;

    // 生成表格内容（添加删除按钮）
    const tableBody = document.getElementById('tableBody');
    tableBody.innerHTML = data.map((row, index) => {
        const dataCells = columns.map(col => {
            let value = row[col];
            if (value === null || value === undefined) {
                value = '<span class="text-muted">NULL</span>';
            } else if (typeof value === 'string' && value.length > 50) {
                value = `<span title="${escapeHtml(value)}">${escapeHtml(value.substring(0, 50))}...</span>`;
            } else {
                value = escapeHtml(String(value));
            }
            return `<td>${value}</td>`;
        }).join('');

        // 添加操作列（删除按钮）
        const recordId = row.id || row.user_id || index;
        const actionCell = `<td>
            <button class="btn btn-danger btn-sm" onclick="deleteRecordByIndex(${index})" title="删除记录">
                <i class="bi bi-trash"></i>
            </button>
        </td>`;

        return `<tr>${dataCells}${actionCell}</tr>`;
    }).join('');
}

// HTML转义函数
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 更新表格信息
function updateTableInfo(tableName, recordCount) {
    const description = tableDescriptions[tableName] || tableName;
    document.getElementById('tableTitle').innerHTML = `<i class="bi bi-table"></i> ${description}`;
    document.getElementById('recordCount').textContent = recordCount;

    // 启用清空按钮
    document.getElementById('clearBtn').disabled = false;
}

// 刷新表格数据
function refreshTableData() {
    if (currentTable) {
        loadTableData();
        showToast('数据已刷新', 'success');
    } else {
        showToast('请先选择数据表', 'warning');
    }
}

// 导出表格数据
async function exportTableData() {
    if (!currentTable || !currentData || currentData.length === 0) {
        showToast('没有可导出的数据', 'warning');
        return;
    }

    try {
        const token = localStorage.getItem('auth_token');
        const response = await fetch(`/admin/data/${currentTable}/export`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = `${currentTable}_${new Date().toISOString().slice(0, 10)}.xlsx`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            showToast('数据导出成功', 'success');
        } else {
            showToast('导出失败', 'danger');
        }
    } catch (error) {
        console.error('导出数据失败:', error);
        showToast('导出数据失败', 'danger');
    }
}

// 清空表格数据
async function clearTableData() {
    if (!currentTable) {
        showToast('请先选择数据表', 'warning');
        return;
    }

    const description = tableDescriptions[currentTable] || currentTable;
    const confirmed = confirm(`确定要清空 "${description}" 的所有数据吗？\n\n此操作不可撤销！`);

    if (!confirmed) return;

    try {
        const token = localStorage.getItem('auth_token');
        const response = await fetch(`/admin/data/${currentTable}/clear`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (response.ok) {
            const data = await response.json();
            showToast(data.message || '数据清空成功', 'success');
            // 重新加载数据
            loadTableData();
        } else {
            const errorData = await response.json();
            showToast(`清空失败: ${errorData.detail || '未知错误'}`, 'danger');
        }
    } catch (error) {
        console.error('清空数据失败:', error);
        showToast('清空数据失败', 'danger');
    }
}

// 删除记录相关变量
let currentDeleteId = null;
let deleteRecordModal = null;

// 初始化删除记录模态框
function initDeleteRecordModal() {
    if (!deleteRecordModal) {
        deleteRecordModal = new bootstrap.Modal(document.getElementById('deleteRecordModal'));
    }
}

// 通过索引删除记录
function deleteRecordByIndex(index) {
    console.log('deleteRecordByIndex被调用，index:', index);
    console.log('currentData:', currentData);
    console.log('当前currentTable:', currentTable);

    if (!currentData || index >= currentData.length) {
        console.error('无效的索引或数据不存在');
        showToast('删除失败：数据不存在', 'danger');
        return;
    }

    const record = currentData[index];
    console.log('获取到的record:', record);

    deleteRecord(record, index);
}

// 删除记录
function deleteRecord(record, index) {
    console.log('deleteRecord被调用');
    console.log('record:', record);
    console.log('index:', index);
    console.log('当前currentTable:', currentTable);

    initDeleteRecordModal();

    // 尝试多种方式获取记录ID
    currentDeleteId = record.id || record.order_id || record.keyword || record.key || record.user_id || record.cookie_id ||
                     record.card_id || record.item_id  || index;

    console.log('设置currentDeleteId为:', currentDeleteId);
    console.log('record的所有字段:', Object.keys(record));
    console.log('record的所有值:', record);

    // 显示记录信息
    const deleteRecordInfo = document.getElementById('deleteRecordInfo');
    deleteRecordInfo.innerHTML = '';

    Object.keys(record).forEach(key => {
        const div = document.createElement('div');
        div.innerHTML = `<strong>${key}:</strong> ${record[key] || '-'}`;
        deleteRecordInfo.appendChild(div);
    });

    deleteRecordModal.show();
}

// 确认删除记录
async function confirmDeleteRecord() {
    console.log('confirmDeleteRecord被调用');
    console.log('currentDeleteId:', currentDeleteId);
    console.log('currentTable:', currentTable);

    if (!currentDeleteId || !currentTable) {
        console.error('缺少必要参数:', { currentDeleteId, currentTable });
        showToast('删除失败：缺少必要参数', 'danger');
        return;
    }

    try {
        const token = localStorage.getItem('auth_token');
        const url = `/admin/data/${currentTable}/${currentDeleteId}`;
        console.log('发送删除请求到:', url);

        const response = await fetch(url, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        console.log('删除响应状态:', response.status);

        if (response.ok) {
            const data = await response.json();
            console.log('删除成功响应:', data);
            deleteRecordModal.hide();
            showToast(data.message || '删除成功', 'success');
            loadTableData(); // 重新加载数据
        } else {
            const errorData = await response.json();
            console.error('删除失败响应:', errorData);
            showToast(`删除失败: ${errorData.detail || '未知错误'}`, 'danger');
        }
    } catch (error) {
        console.error('删除记录失败:', error);
        showToast('删除记录失败: ' + error.message, 'danger');
    }
}

// ================================
// 系统日志管理功能
// ================================
let logAutoRefreshInterval = null;
let currentLogLevel = '';

// 加载系统日志
async function loadSystemLogs() {
    const token = localStorage.getItem('auth_token');
    const lines = document.getElementById('logLines').value;
    const level = currentLogLevel;

    const loadingDiv = document.getElementById('loadingSystemLogs');
    const logContainer = document.getElementById('systemLogContainer');
    const noLogsDiv = document.getElementById('noSystemLogs');

    loadingDiv.style.display = 'block';
    logContainer.style.display = 'none';
    noLogsDiv.style.display = 'none';

    let url = `/admin/logs?lines=${lines}`;
    if (level) {
        url += `&level=${level}`;
    }

    try {
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        const data = await response.json();
        loadingDiv.style.display = 'none';

        if (data.logs && data.logs.length > 0) {
            displaySystemLogs(data.logs);
            updateLogInfo(data);
            logContainer.style.display = 'block';
        } else {
            noLogsDiv.style.display = 'block';
        }

        // 更新最后更新时间
        document.getElementById('logLastUpdate').textContent =
            '最后更新: ' + new Date().toLocaleTimeString('zh-CN');
    } catch (error) {
        console.error('加载日志失败:', error);
        loadingDiv.style.display = 'none';
        noLogsDiv.style.display = 'block';
        showToast('加载日志失败', 'danger');
    }
}

// 显示系统日志
function displaySystemLogs(logs) {
    const logContainer = document.getElementById('systemLogContainer');
    logContainer.innerHTML = '';

    // 反转日志数组，让最新的日志显示在最上面
    const reversedLogs = [...logs].reverse();

    reversedLogs.forEach(log => {
        const logLine = document.createElement('div');
        logLine.className = 'log-entry';

        // 根据日志级别添加颜色类
        if (log.includes('| INFO |')) {
            logLine.classList.add('INFO');
        } else if (log.includes('| WARNING |')) {
            logLine.classList.add('WARNING');
        } else if (log.includes('| ERROR |')) {
            logLine.classList.add('ERROR');
        } else if (log.includes('| DEBUG |')) {
            logLine.classList.add('DEBUG');
        } else if (log.includes('| CRITICAL |')) {
            logLine.classList.add('CRITICAL');
        }

        logLine.textContent = log;
        logContainer.appendChild(logLine);
    });

    // 自动滚动到顶部（显示最新日志）
    scrollLogToTop();
}

// 更新日志信息
function updateLogInfo(data) {
    document.getElementById('logFileName').textContent = data.log_file || '-';
    document.getElementById('logDisplayLines').textContent = data.total_lines || '-';
}

// 按级别过滤日志
function filterLogsByLevel(level) {
    currentLogLevel = level;

    // 更新过滤按钮状态
    document.querySelectorAll('.filter-badge').forEach(badge => {
        badge.classList.remove('active');
    });
    document.querySelector(`[data-level="${level}"]`).classList.add('active');

    // 更新当前过滤显示
    const filterText = level ? level.toUpperCase() : '全部';
    document.getElementById('logCurrentFilter').textContent = filterText;

    // 重新加载日志
    loadSystemLogs();
}

// 切换日志自动刷新
function toggleLogAutoRefresh() {
    const autoRefresh = document.getElementById('autoRefreshLogs');
    const label = document.getElementById('autoRefreshLogLabel');
    const icon = document.getElementById('autoRefreshLogIcon');

    if (autoRefresh.checked) {
        // 开启自动刷新
        logAutoRefreshInterval = setInterval(loadSystemLogs, 5000); // 每5秒刷新
        label.textContent = '开启 (5s)';
        icon.style.display = 'inline';
        icon.classList.add('auto-refresh-indicator');
    } else {
        // 关闭自动刷新
        if (logAutoRefreshInterval) {
            clearInterval(logAutoRefreshInterval);
            logAutoRefreshInterval = null;
        }
        label.textContent = '关闭';
        icon.style.display = 'none';
        icon.classList.remove('auto-refresh-indicator');
    }
}

// 滚动到日志顶部
function scrollLogToTop() {
    const logContainer = document.getElementById('systemLogContainer');
    logContainer.scrollTop = 0;
}

// 滚动到日志底部
function scrollLogToBottom() {
    const logContainer = document.getElementById('systemLogContainer');
    logContainer.scrollTop = logContainer.scrollHeight;
}

// ================================
// 商品搜索功能
// ================================
let searchResultsData = [];
let currentSearchPage = 1;
let searchPageSize = 20;
let totalSearchPages = 0;

// 初始化商品搜索功能
function initItemSearch() {
    const searchForm = document.getElementById('itemSearchForm');
    if (searchForm) {
        searchForm.addEventListener('submit', handleItemSearch);
    }
}

// 处理商品搜索
async function handleItemSearch(event) {
    event.preventDefault();

    const keyword = document.getElementById('searchKeyword').value.trim();
    const totalPages = parseInt(document.getElementById('searchTotalPages').value) || 1;
    const pageSize = parseInt(document.getElementById('searchPageSize').value) || 20;

    if (!keyword) {
        showToast('请输入搜索关键词', 'warning');
        return;
    }

    // 显示搜索状态
    showSearchStatus(true);
    hideSearchResults();

    try {
        // 检查是否有有效的cookies账户
        const cookiesCheckResponse = await fetch('/cookies/check', {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('auth_token')}`
            }
        });

        if (cookiesCheckResponse.ok) {
            const cookiesData = await cookiesCheckResponse.json();
            if (!cookiesData.hasValidCookies) {
                showToast('搜索失败：系统中不存在有效的账户信息。请先在Cookie管理中添加有效的闲鱼账户。', 'warning');
                showSearchStatus(false);
                return;
            }
        }

        const token = localStorage.getItem('auth_token');
        const response = await fetch('/items/search_multiple', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                keyword: keyword,
                total_pages: totalPages
            })
        });

        console.log('API响应状态:', response.status);

        if (response.ok) {
            const data = await response.json();
            console.log('API返回的完整数据:', data);

            // 修复字段名：使用data.data而不是data.items
            searchResultsData = data.data || [];
            console.log('设置searchResultsData:', searchResultsData);
            console.log('searchResultsData长度:', searchResultsData.length);

            searchPageSize = pageSize;
            currentSearchPage = 1;
            totalSearchPages = Math.ceil(searchResultsData.length / searchPageSize);

            if (data.error) {
                showToast(`搜索完成，但遇到问题: ${data.error}`, 'warning');
            }

            showSearchStatus(false);
            displaySearchResults();
            updateSearchStats(data);
        } else {
            const errorData = await response.json();
            showSearchStatus(false);
            showToast(`搜索失败: ${errorData.detail || '未知错误'}`, 'danger');
            showNoSearchResults();
        }
    } catch (error) {
        console.error('搜索商品失败:', error);
        showSearchStatus(false);
        showToast('搜索商品失败', 'danger');
        showNoSearchResults();
    }
}

// 显示搜索状态
function showSearchStatus(isSearching) {
    const statusDiv = document.getElementById('searchStatus');
    const progressDiv = document.getElementById('searchProgress');

    if (isSearching) {
        statusDiv.style.display = 'block';
        progressDiv.textContent = '正在搜索商品数据...';
    } else {
        statusDiv.style.display = 'none';
    }
}

// 隐藏搜索结果
function hideSearchResults() {
    document.getElementById('searchResults').style.display = 'none';
    document.getElementById('searchResultStats').style.display = 'none';
    document.getElementById('noSearchResults').style.display = 'none';
}

// 显示搜索结果
function displaySearchResults() {
    if (searchResultsData.length === 0) {
        showNoSearchResults();
        return;
    }

    const startIndex = (currentSearchPage - 1) * searchPageSize;
    const endIndex = startIndex + searchPageSize;
    const pageItems = searchResultsData.slice(startIndex, endIndex);

    const container = document.getElementById('searchResultsContainer');
    container.innerHTML = '';

    pageItems.forEach(item => {
        const itemCard = createItemCard(item);
        container.appendChild(itemCard);
    });

    updateSearchPagination();
    document.getElementById('searchResults').style.display = 'block';
}

// 创建商品卡片
function createItemCard(item) {
    console.log('createItemCard被调用，item数据:', item);
    console.log('item的所有字段:', Object.keys(item));

    const col = document.createElement('div');
    col.className = 'col-md-6 col-lg-4 col-xl-3 mb-4';

    // 修复字段映射：使用main_image而不是image_url
    const imageUrl = item.main_image || item.image_url || 'https://via.placeholder.com/200x200?text=图片加载失败';
    const wantCount = item.want_count || 0;

    console.log('处理后的数据:', {
        title: item.title,
        price: item.price,
        seller_name: item.seller_name,
        imageUrl: imageUrl,
        wantCount: wantCount,
        url: item.item_url || item.url
    });

    col.innerHTML = `
        <div class="card item-card h-100">
            <img src="${escapeHtml(imageUrl)}" class="item-image" alt="${escapeHtml(item.title)}"
                 onerror="this.src='https://via.placeholder.com/200x200?text=图片加载失败'"
                 style="width: 100%; height: 200px; object-fit: cover; border-radius: 10px;">
            <div class="card-body d-flex flex-column">
                <h6 class="card-title" title="${escapeHtml(item.title)}">
                    ${escapeHtml(item.title.length > 50 ? item.title.substring(0, 50) + '...' : item.title)}
                </h6>
                <div class="price mb-2" style="color: #e74c3c; font-weight: bold; font-size: 1.2em;">
                    ${escapeHtml(item.price)}
                </div>
                <div class="seller-name mb-2" style="color: #6c757d; font-size: 0.9em;">
                    <i class="bi bi-person me-1"></i>
                    ${escapeHtml(item.seller_name)}
                </div>
                ${wantCount > 0 ? `<div class="want-count mb-2">
                    <i class="bi bi-heart-fill me-1" style="color: #ff6b6b;"></i>
                    <span class="badge bg-danger">${wantCount}人想要</span>
                </div>` : ''}
                <div class="mt-auto">
                    <a href="${escapeHtml(item.item_url || item.url)}" target="_blank" class="btn btn-primary btn-sm w-100">
                        <i class="bi bi-eye me-1"></i>查看详情
                    </a>
                </div>
            </div>
        </div>
    `;

    return col;
}

// 更新搜索统计
function updateSearchStats(data) {
    document.getElementById('totalItemsFound').textContent = searchResultsData.length;
    document.getElementById('totalPagesSearched').textContent = data.total_pages || 0;
    document.getElementById('currentDisplayPage').textContent = currentSearchPage;
    document.getElementById('totalDisplayPages').textContent = totalSearchPages;
    document.getElementById('searchResultStats').style.display = 'block';
}

// 更新搜索分页
function updateSearchPagination() {
    const paginationContainer = document.getElementById('searchPagination');
    paginationContainer.innerHTML = '';

    if (totalSearchPages <= 1) return;

    const pagination = document.createElement('nav');
    pagination.innerHTML = `
        <ul class="pagination">
            <li class="page-item ${currentSearchPage === 1 ? 'disabled' : ''}">
                <a class="page-link" href="#" onclick="changeSearchPage(${currentSearchPage - 1})">上一页</a>
            </li>
            ${generateSearchPageNumbers()}
            <li class="page-item ${currentSearchPage === totalSearchPages ? 'disabled' : ''}">
                <a class="page-link" href="#" onclick="changeSearchPage(${currentSearchPage + 1})">下一页</a>
            </li>
        </ul>
    `;

    paginationContainer.appendChild(pagination);
}

// 生成搜索分页页码
function generateSearchPageNumbers() {
    let pageNumbers = '';
    const maxVisiblePages = 5;
    let startPage = Math.max(1, currentSearchPage - Math.floor(maxVisiblePages / 2));
    let endPage = Math.min(totalSearchPages, startPage + maxVisiblePages - 1);

    if (endPage - startPage + 1 < maxVisiblePages) {
        startPage = Math.max(1, endPage - maxVisiblePages + 1);
    }

    for (let i = startPage; i <= endPage; i++) {
        pageNumbers += `
            <li class="page-item ${i === currentSearchPage ? 'active' : ''}">
                <a class="page-link" href="#" onclick="changeSearchPage(${i})">${i}</a>
            </li>
        `;
    }

    return pageNumbers;
}

// 切换搜索页面
function changeSearchPage(page) {
    if (page < 1 || page > totalSearchPages || page === currentSearchPage) return;

    currentSearchPage = page;
    displaySearchResults();
    updateSearchStats({ total_pages: document.getElementById('totalPagesSearched').textContent });
}

// 显示无搜索结果
function showNoSearchResults() {
    document.getElementById('noSearchResults').style.display = 'block';
    document.getElementById('searchResults').style.display = 'none';
    document.getElementById('searchResultStats').style.display = 'none';
}

// 导出搜索结果
function exportSearchResults() {
    if (searchResultsData.length === 0) {
        showToast('没有可导出的搜索结果', 'warning');
        return;
    }

    try {
        // 准备导出数据
        const exportData = searchResultsData.map(item => ({
            '商品标题': item.title,
            '价格': item.price,
            '卖家': item.seller_name,
            '想要人数': item.want_count || 0,
            '商品链接': item.url,
            '图片链接': item.image_url
        }));

        // 转换为CSV格式
        const headers = Object.keys(exportData[0]);
        const csvContent = [
            headers.join(','),
            ...exportData.map(row => headers.map(header => `"${row[header] || ''}"`).join(','))
        ].join('\n');

        // 创建下载链接
        const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);
        link.setAttribute('href', url);
        link.setAttribute('download', `商品搜索结果_${new Date().toISOString().slice(0, 10)}.csv`);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        showToast('搜索结果导出成功', 'success');
    } catch (error) {
        console.error('导出搜索结果失败:', error);
        showToast('导出搜索结果失败', 'danger');
    }
}
