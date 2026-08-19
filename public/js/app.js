document.addEventListener('DOMContentLoaded', () => {
    // --- ESTADO DA APLICAÇÃO ---
    let appState = {
        token: sessionStorage.getItem('samba_ad_token') || null,
        username: sessionStorage.getItem('samba_ad_user') || 'administrator',
        mockMode: true,
        domainDn: 'DC=empresa,DC=local',
        serverIp: '127.0.0.1',
        users: [],
        computers: [],
        ous: [],
        gpos: [],
        gposByOu: {},
        platformUsers: [],
        cmdHistory: [
            'sudo samba-tool user list',
            'sudo samba-tool computer list',
            'sudo samba-tool ou list',
            'sudo samba-tool gpo listall'
        ]
    };

    // --- TEMPORIZADOR DE INATIVIDADE (20 MINUTOS) ---
    const INACTIVITY_LIMIT = 20 * 60 * 1000; // 20 min em milissegundos
    let inactivityTimer = null;
    let lastReset = Date.now();

    function resetInactivityTimer() {
        if (inactivityTimer) {
            clearTimeout(inactivityTimer);
        }

        // Só ativa o temporizador se houver um usuário autenticado
        if (appState.token) {
            inactivityTimer = setTimeout(handleInactivityLogout, INACTIVITY_LIMIT);
        }
    }

    function handleInactivityLogout() {
        if (!appState.token) return;

        // Limpa estado da aplicação e armazenamento da sessão
        appState.token = null;
        sessionStorage.removeItem('samba_ad_token');
        sessionStorage.removeItem('samba_ad_user');

        // Limpa campos de senha do formulário
        const passInput = document.getElementById('login-password');
        if (passInput) passInput.value = '';

        // Atualiza a interface para a tela de bloqueio/login
        checkAuthUI();
        showToast('Sessão expirada por inatividade (20 minutos). Faça login novamente.', 'warning');
        console.warn('Sessão bloqueada por inatividade de 20 minutos.');
    }

    // Monitora interações do usuário para resetar o tempo
    const activityEvents = ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll', 'click'];
    activityEvents.forEach(eventType => {
        window.addEventListener(eventType, () => {
            const now = Date.now();
            // Limita a verificação no máximo uma vez por segundo para evitar sobrecarga
            if (now - lastReset > 1000) {
                lastReset = now;
                resetInactivityTimer();
            }
        }, { passive: true });
    });

    // --- HELPER DE NOTIFICAÇÃO (TOAST) ---
    function showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        if (!container) {
            console.log(`[${type}] ${message}`);
            return;
        }
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(() => {
            toast.remove();
        }, 4000);
    }

    // --- ELEMENTOS DO DOM ---
    const authOverlay = document.getElementById('auth-overlay');
    const formLogin = document.getElementById('form-login');
    
    const appContainer = document.getElementById('app-container');
    const logoutBtn = document.getElementById('logout-btn');
    const currentUserName = document.getElementById('current-user-name');

    const navItems = document.querySelectorAll('.nav-item');
    const tabPanes = document.querySelectorAll('.tab-pane');
    const modeSwitch = document.getElementById('mode-switch');
    const modeBadge = document.getElementById('mode-badge');
    const statModeText = document.getElementById('stat-mode-text');
    const refreshBtn = document.getElementById('refresh-btn');
    const domainDnDisplay = document.getElementById('domain-dn-display');
    const serverIpDisplay = document.getElementById('server-ip-display');

    // Botões de Energia do Servidor
    const btnServerReboot = document.getElementById('btn-server-reboot');
    const btnServerShutdown = document.getElementById('btn-server-shutdown');

    const statUserCount = document.getElementById('stat-user-count');
    const statCompCount = document.getElementById('stat-comp-count');
    const statOuCount = document.getElementById('stat-ou-count');
    const statGpoCount = document.getElementById('stat-gpo-count');
    const dashboardLastCmd = document.getElementById('dashboard-last-cmd');

    const usersTableBody = document.getElementById('users-table-body');
    const searchUsersInput = document.getElementById('search-users');

    const computersTableBody = document.getElementById('computers-table-body');
    const searchComputersInput = document.getElementById('search-computers');

    const ousCardGrid = document.getElementById('ous-card-grid');
    const searchOusInput = document.getElementById('search-ous');

    const gpoOuMatrix = document.getElementById('gpo-ou-matrix');
    const gposTableBody = document.getElementById('gpos-table-body');
    const searchGposInput = document.getElementById('search-gpos');

    const platformUsersTableBody = document.getElementById('platform-users-table-body');
    const searchPlatformUsersInput = document.getElementById('search-platform-users');

    const selectOuForObjects = document.getElementById('select-ou-for-objects');
    const btnFetchOuObjects = document.getElementById('btn-fetch-ou-objects');
    const ouObjectsTableBody = document.getElementById('ou-objects-table-body');
    const objectsOuTargetLabel = document.getElementById('objects-ou-target-label');

    const liveCommandLog = document.getElementById('live-command-log');
    const copyTerminalBtn = document.getElementById('copy-terminal-btn');

    // Modais
    const modalNewUser = document.getElementById('modal-new-user');
    const modalResetPassword = document.getElementById('modal-reset-password');
    const modalNewComp = document.getElementById('modal-new-comp');
    const modalNewOu = document.getElementById('modal-new-ou');
    const modalNewGpo = document.getElementById('modal-new-gpo');
    const modalLinkGpo = document.getElementById('modal-link-gpo');
    const modalNewPlatformUser = document.getElementById('modal-new-platform-user');
    
    const openNewUserModalBtn = document.getElementById('open-new-user-modal');
    const openNewCompModalBtn = document.getElementById('open-new-comp-modal');
    const openNewOuModalBtn = document.getElementById('open-new-ou-modal');
    const openNewGpoModalBtn = document.getElementById('open-new-gpo-modal');
    const openLinkGpoModalBtn = document.getElementById('open-link-gpo-modal');
    const openNewPlatformUserModalBtn = document.getElementById('open-new-platform-user-modal');
    const closeModals = document.querySelectorAll('.close-modal');

    // Forms
    const formNewUser = document.getElementById('form-new-user');
    const formResetPassword = document.getElementById('form-reset-password');
    const formNewComp = document.getElementById('form-new-comp');
    const formNewOu = document.getElementById('form-new-ou');
    const formNewGpo = document.getElementById('form-new-gpo');
    const formLinkGpo = document.getElementById('form-link-gpo');
    const formNewPlatformUser = document.getElementById('form-new-platform-user');

    const inputUserOu = document.getElementById('input-user-ou');
    const inputCompOu = document.getElementById('input-comp-ou');
    const inputParentOu = document.getElementById('input-parent-ou');
    const selectLinkGpo = document.getElementById('select-link-gpo');
    const selectLinkOu = document.getElementById('select-link-ou');
    
    const userCmdPreview = document.getElementById('user-cmd-preview');
    const resetPassCmdPreview = document.getElementById('reset-pass-cmd-preview');
    const compCmdPreview = document.getElementById('comp-cmd-preview');
    const ouCmdPreview = document.getElementById('ou-cmd-preview');
    const gpoCmdPreview = document.getElementById('gpo-cmd-preview');
    const gpoLinkCmdPreview = document.getElementById('gpo-link-cmd-preview');

    // --- AUTENTICAÇÃO E SESSÃO ---

    function checkAuthUI() {
        if (appState.token) {
            if (authOverlay) authOverlay.style.display = 'none';
            if (appContainer) appContainer.style.display = 'flex';
            if (currentUserName) currentUserName.textContent = appState.username;
            resetInactivityTimer();
            refreshAll();
        } else {
            if (authOverlay) authOverlay.style.display = 'flex';
            if (appContainer) appContainer.style.display = 'none';
            if (inactivityTimer) clearTimeout(inactivityTimer);
        }
    }

    formLogin?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('login-username')?.value;
        const password = document.getElementById('login-password')?.value;

        try {
            const res = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            const data = await res.json();
            if (data.success && data.token) {
                appState.token = data.token;
                appState.username = username;
                sessionStorage.setItem('samba_ad_token', data.token);
                sessionStorage.setItem('samba_ad_user', username);
                checkAuthUI();
                showToast(data.message || 'Login efetuado com sucesso!', 'success');
            } else {
                showToast(data.error || 'Credenciais inválidas.', 'error');
            }
        } catch (err) {
            showToast('Erro ao tentar realizar login.', 'error');
        }
    });

    logoutBtn?.addEventListener('click', async () => {
        try {
            await authenticatedFetch('/api/logout', { method: 'POST' });
        } catch (err) {}
        appState.token = null;
        sessionStorage.removeItem('samba_ad_token');
        sessionStorage.removeItem('samba_ad_user');
        checkAuthUI();
        showToast('Sessão encerrada com sucesso.', 'info');
    });

    async function authenticatedFetch(url, options = {}) {
        options.headers = options.headers || {};
        if (appState.token) {
            options.headers['Authorization'] = `Bearer ${appState.token}`;
        }
        const res = await fetch(url, options);
        if (res.status === 401) {
            appState.token = null;
            sessionStorage.removeItem('samba_ad_token');
            sessionStorage.removeItem('samba_ad_user');
            checkAuthUI();
            throw new Error('Não autorizado. Efetue login.');
        }
        return res;
    }

    // --- CONTROLE DE ENERGIA DO SERVIDOR (REBOOT / SHUTDOWN) ---

    async function handleServerPower(action) {
        const actionText = action === 'reboot' ? 'REINICIAR' : 'DESLIGAR';
        
        const confirmed = confirm(
            `⚠️ ATENÇÃO: Tem certeza que deseja ${actionText} o servidor Linux?\n\n` +
            `Todos os serviços do Samba AD e sessões ativas dos usuários serão interrompidos.`
        );

        if (!confirmed) return;

        try {
            const res = await authenticatedFetch('/api/system/power', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action })
            });

            const data = await res.json();

            if (data.success) {
                showToast(data.message, 'warning');
                if (data.cmd_preview) addCommandToLog(data.cmd_preview);

                if (!appState.mockMode) {
                    setTimeout(() => {
                        alert(`O servidor está ${action === 'reboot' ? 'reiniciando' : 'desligando'}. A conexão com o painel será perdida.`);
                        window.location.reload();
                    }, 2000);
                }
            } else {
                showToast(data.error || 'Erro ao processar o comando de energia.', 'error');
            }
        } catch (err) {
            showToast('Erro de comunicação com o servidor ao tentar alterar o estado de energia.', 'error');
        }
    }

    btnServerReboot?.addEventListener('click', () => handleServerPower('reboot'));
    btnServerShutdown?.addEventListener('click', () => handleServerPower('shutdown'));

    // --- NAVEGAÇÃO POR ABAS ---
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const targetTab = item.getAttribute('data-tab');
            navItems.forEach(n => n.classList.remove('active'));
            tabPanes.forEach(p => p.classList.remove('active'));

            item.classList.add('active');
            const targetPane = document.getElementById(`tab-${targetTab}`);
            if (targetPane) targetPane.classList.add('active');
        });
    });

    // Ações Rápidas
    document.getElementById('btn-quick-new-user')?.addEventListener('click', () => openModal(modalNewUser));
    document.getElementById('btn-quick-new-comp')?.addEventListener('click', () => openModal(modalNewComp));
    document.getElementById('btn-quick-new-gpo')?.addEventListener('click', () => openModal(modalNewGpo));
    document.getElementById('btn-quick-new-ou')?.addEventListener('click', () => openModal(modalNewOu));
    document.getElementById('btn-quick-new-platform-user')?.addEventListener('click', () => openModal(modalNewPlatformUser));

    // --- CARREGAMENTO DE DADOS ---

    async function fetchStatus() {
        try {
            const res = await fetch('/api/status');
            const data = await res.json();
            
            appState.mockMode = typeof data.mock_mode === 'boolean' ? data.mock_mode : true;
            appState.domainDn = data.domain_dn || 'DC=empresa,DC=local';
            appState.serverIp = data.server_ip || '127.0.0.1';

            const domainNameParts = appState.domainDn.split(',').map(part => part.replace(/DC=/gi, '')).filter(Boolean);
            const domainName = domainNameParts.length > 0 ? domainNameParts.join('.') : 'empresa.local';

            if (domainDnDisplay) domainDnDisplay.textContent = appState.domainDn;
            if (serverIpDisplay) serverIpDisplay.textContent = `IP: ${appState.serverIp}`;

            const authServerIpElem = document.getElementById('auth-server-ip');
            const authDomainNameElem = document.getElementById('auth-domain-name');
            const sidebarDomainNameElem = document.getElementById('sidebar-domain-name');

            if (authServerIpElem) authServerIpElem.textContent = appState.serverIp;
            if (authDomainNameElem) authDomainNameElem.textContent = domainName;
            if (sidebarDomainNameElem) sidebarDomainNameElem.textContent = domainName;

            if (modeSwitch) modeSwitch.checked = appState.mockMode;
            updateModeUI(appState.mockMode);

            if (data.system_info) {
                renderSystemInfo(data.system_info);
            }
        } catch (err) {
            showToast('Erro ao conectar com o servidor AD.', 'error');
        }
    }

    async function fetchPlatformUsers() {
        try {
            const res = await authenticatedFetch('/api/platform-users');
            const data = await res.json();
            if (data.success) {
                appState.platformUsers = data.operators || [];
                renderPlatformUsers(appState.platformUsers);
            }
        } catch (err) {}
    }

    async function fetchUsers() {
        try {
            const res = await authenticatedFetch('/api/users');
            const data = await res.json();
            if (data.success) {
                appState.users = data.users || [];
                renderUsers(appState.users);
                if (statUserCount) statUserCount.textContent = appState.users.length;
                if (data.cmd_preview) addCommandToLog(data.cmd_preview);
            }
        } catch (err) {}
    }

    async function fetchComputers() {
        try {
            const res = await authenticatedFetch('/api/computers');
            const data = await res.json();
            if (data.success) {
                appState.computers = data.computers || [];
                renderComputers(appState.computers);
                if (statCompCount) statCompCount.textContent = appState.computers.length;
                if (data.cmd_preview) addCommandToLog(data.cmd_preview);
            }
        } catch (err) {}
    }

    async function fetchOus() {
        try {
            const res = await authenticatedFetch('/api/ous');
            const data = await res.json();
            if (data.success) {
                appState.ous = data.ous || [];
                renderOus(appState.ous);
                populateOuSelects(appState.ous);
                if (statOuCount) statOuCount.textContent = appState.ous.length;
                if (data.cmd_preview) addCommandToLog(data.cmd_preview);
            }
        } catch (err) {}
    }

    async function fetchGpos() {
        try {
            const res = await authenticatedFetch('/api/gpos');
            const data = await res.json();
            if (data.success) {
                appState.gpos = data.gpos || [];
                appState.gposByOu = data.gpos_by_ou || {};
                renderGpoMatrix(appState.gposByOu);
                renderGposTable(appState.gpos);
                populateGpoSelects(appState.gpos);
                if (statGpoCount) statGpoCount.textContent = appState.gpos.length;
                if (data.cmd_preview) addCommandToLog(data.cmd_preview);
            }
        } catch (err) {}
    }

    async function toggleMockMode(enabled) {
        try {
            const res = await authenticatedFetch('/api/status/mode', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mock_mode: enabled })
            });
            const data = await res.json();
            if (data.success) {
                appState.mockMode = enabled;
                updateModeUI(enabled);
                showToast(data.message, 'success');
                refreshAll();
            }
        } catch (err) {}
    }

    function updateModeUI(isMock) {
        if (modeBadge) {
            if (isMock) {
                modeBadge.className = 'badge mock';
                modeBadge.textContent = 'Modo Simulação';
            } else {
                modeBadge.className = 'badge real';
                modeBadge.textContent = 'Modo Real (samba-tool)';
            }
        }
        if (statModeText) {
            statModeText.textContent = isMock ? 'Mock / Simulação' : 'Samba AD Real';
        }
    }

    // --- RENDERIZAÇÃO ---

    function renderPlatformUsers(operatorsList) {
        if (!platformUsersTableBody) return;
        platformUsersTableBody.innerHTML = '';
        if (operatorsList.length === 0) {
            platformUsersTableBody.innerHTML = `<tr><td colspan="4" class="text-center text-muted">Nenhum operador do sistema cadastrado.</td></tr>`;
            return;
        }

        operatorsList.forEach(op => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong style="color: var(--text-primary); font-family: var(--font-mono);">🔑 ${op.username}</strong></td>
                <td>${op.full_name}</td>
                <td>${op.system ? '<span class="badge system">Administrador Padrão</span>' : '<span class="badge user-type">Operador Cadastrado</span>'}</td>
                <td>
                    ${op.system ? '<span class="text-muted" style="font-size: 0.8rem;">Protegido</span>' : 
                    `<button class="btn btn-sm btn-danger btn-delete-platform-user" data-username="${op.username}">Remover Acesso</button>`}
                </td>
            `;
            platformUsersTableBody.appendChild(tr);
        });

        document.querySelectorAll('.btn-delete-platform-user').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const username = e.target.getAttribute('data-username');
                deletePlatformUser(username);
            });
        });
    }

    function renderUsers(usersList) {
        if (!usersTableBody) return;
        usersTableBody.innerHTML = '';
        if (usersList.length === 0) {
            usersTableBody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">Nenhum usuário encontrado.</td></tr>`;
            return;
        }

        usersList.forEach(u => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong style="color: var(--text-primary); font-family: var(--font-mono);">${u.username}</strong></td>
                <td>${u.cn || u.username}</td>
                <td><span style="color: var(--text-secondary);">${u.email || '-'}</span></td>
                <td><span class="badge ${u.system ? 'system' : 'user-type'}">${u.ou}</span></td>
                <td>${u.system ? '<span class="badge system">Sistema</span>' : '<span class="badge user-type">Usuário AD</span>'}</td>
                <td>
                    <div class="table-actions">
                        <button class="btn btn-sm btn-secondary btn-reset-pass" data-username="${u.username}">🔑 Alterar Senha</button>
                        ${u.system ? '<span class="text-muted" style="font-size: 0.8rem; margin-left: 0.25rem;">Protegido</span>' : 
                        `<button class="btn btn-sm btn-danger btn-delete-user" data-username="${u.username}">Excluir</button>`}
                    </div>
                </td>
            `;
            usersTableBody.appendChild(tr);
        });

        document.querySelectorAll('.btn-reset-pass').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const username = e.target.getAttribute('data-username');
                const resetUserInput = document.getElementById('input-reset-username');
                const resetPassInput = document.getElementById('input-reset-new-password');
                if (resetUserInput) resetUserInput.value = username;
                if (resetPassInput) resetPassInput.value = '';
                openModal(modalResetPassword);
            });
        });

        document.querySelectorAll('.btn-delete-user').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const username = e.target.getAttribute('data-username');
                deleteUser(username);
            });
        });
    }

    function renderComputers(computersList) {
        if (!computersTableBody) return;
        computersTableBody.innerHTML = '';
        if (computersList.length === 0) {
            computersTableBody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">Nenhum desktop ou computador cadastrado no domínio.</td></tr>`;
            return;
        }

        computersList.forEach(c => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong style="color: #c084fc; font-family: var(--font-mono);">🖥️ ${c.name}</strong></td>
                <td><span style="font-family: var(--font-mono); font-size: 0.85rem; color: var(--text-secondary);">${c.cn || c.name + '$'}</span></td>
                <td><span class="badge computer">${c.ou}</span></td>
                <td>${c.os || 'Windows 11 Pro'}</td>
                <td><span style="font-family: var(--font-mono); color: var(--success);">${c.ip || 'DHCP'}</span></td>
                <td>
                    <button class="btn btn-sm btn-danger btn-delete-comp" data-name="${c.name}">
                        Excluir Desktop
                    </button>
                </td>
            `;
            computersTableBody.appendChild(tr);
        });

        document.querySelectorAll('.btn-delete-comp').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const name = e.target.getAttribute('data-name');
                deleteComputer(name);
            });
        });
    }

    function renderOus(ousList) {
        if (!ousCardGrid) return;
        ousCardGrid.innerHTML = '';
        if (ousList.length === 0) {
            ousCardGrid.innerHTML = `<p class="text-muted">Nenhuma Unidade Organizacional cadastrada.</p>`;
            return;
        }

        ousList.forEach(o => {
            const card = document.createElement('div');
            card.className = 'ou-card';
            card.innerHTML = `
                <div>
                    <div class="ou-card-header">
                        <div class="ou-icon-box">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
                        </div>
                        <div class="ou-card-title">
                            <h4>${o.name}</h4>
                        </div>
                    </div>
                    <div class="ou-dn-code">${o.dn}</div>
                </div>
                <div class="ou-card-actions">
                    <button class="btn btn-sm btn-secondary btn-inspect-ou" data-dn="${o.dn}">Explorar Objeto</button>
                    <button class="btn btn-sm btn-danger btn-delete-ou" data-dn="${o.dn}">Excluir</button>
                </div>
            `;
            ousCardGrid.appendChild(card);
        });

        document.querySelectorAll('.btn-inspect-ou').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const dn = e.target.getAttribute('data-dn');
                if (selectOuForObjects) selectOuForObjects.value = dn;
                document.querySelector('[data-tab="objects"]')?.click();
                loadOuObjects(dn);
            });
        });

        document.querySelectorAll('.btn-delete-ou').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const dn = e.target.getAttribute('data-dn');
                deleteOu(dn);
            });
        });
    }

    function renderGpoMatrix(gposByOuMap) {
        if (!gpoOuMatrix) return;
        gpoOuMatrix.innerHTML = '';
        const ouKeys = Object.keys(gposByOuMap);

        if (ouKeys.length === 0) {
            gpoOuMatrix.innerHTML = `<p class="text-muted">Nenhuma GPO vinculada a Unidades Organizacionais no momento.</p>`;
            return;
        }

        ouKeys.forEach(ouDn => {
            const gpoList = gposByOuMap[ouDn] || [];
            const card = document.createElement('div');
            card.className = 'gpo-ou-card';
            
            let listHtml = '';
            gpoList.forEach(g => {
                listHtml += `
                    <div class="gpo-list-item">
                        <div class="gpo-info-text">
                            <strong style="color: var(--accent);">${g.name}</strong>
                            <div class="gpo-guid-code">${g.guid}</div>
                        </div>
                        <button class="btn btn-sm btn-danger btn-unlink-gpo" data-ou="${ouDn}" data-guid="${g.guid}">Desvincular</button>
                    </div>
                `;
            });

            card.innerHTML = `
                <div class="gpo-ou-header">
                    <span>🏢 ${ouDn}</span>
                </div>
                ${listHtml}
            `;
            gpoOuMatrix.appendChild(card);
        });

        document.querySelectorAll('.btn-unlink-gpo').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const ou = e.target.getAttribute('data-ou');
                const guid = e.target.getAttribute('data-guid');
                unlinkGpo(ou, guid);
            });
        });
    }

    function renderGposTable(gpoList) {
        if (!gposTableBody) return;
        gposTableBody.innerHTML = '';
        if (gpoList.length === 0) {
            gposTableBody.innerHTML = `<tr><td colspan="5" class="text-center text-muted">Nenhuma GPO encontrada.</td></tr>`;
            return;
        }

        gpoList.forEach(g => {
            const linksHtml = g.links && g.links.length > 0 ? 
                g.links.map(l => `<span class="badge gpo-badge">${l}</span>`).join(' ') : 
                '<span class="text-muted">Sem vínculos</span>';

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong style="color: var(--accent); font-family: var(--font-heading);">${g.name}</strong></td>
                <td><span style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-muted);">${g.guid}</span></td>
                <td><span class="badge ${g.status === 'Enabled' ? 'real' : 'system'}">${g.status || 'Ativa'}</span></td>
                <td>${linksHtml}</td>
                <td>
                    <button class="btn btn-sm btn-secondary btn-quick-link-gpo" data-guid="${g.guid}">
                        🔗 Vincular a OU
                    </button>
                </td>
            `;
            gposTableBody.appendChild(tr);
        });

        document.querySelectorAll('.btn-quick-link-gpo').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const guid = e.target.getAttribute('data-guid');
                if (selectLinkGpo) selectLinkGpo.value = guid;
                openModal(modalLinkGpo);
            });
        });
    }

    function populateOuSelects(ousList) {
        if (inputUserOu) inputUserOu.innerHTML = `<option value="">(Raiz do Domínio / Default)</option>`;
        if (inputCompOu) inputCompOu.innerHTML = `<option value="">(Raiz do Domínio / Default)</option>`;
        if (inputParentOu) inputParentOu.innerHTML = `<option value="">(Nenhuma / Raiz do Domínio)</option>`;
        if (selectOuForObjects) selectOuForObjects.innerHTML = `<option value="">Selecione uma OU...</option>`;
        if (selectLinkOu) selectLinkOu.innerHTML = `<option value="">Selecione a OU Destino...</option>`;

        ousList.forEach(o => {
            if (inputUserOu) inputUserOu.innerHTML += `<option value="${o.dn}">${o.name} (${o.dn})</option>`;
            if (inputCompOu) inputCompOu.innerHTML += `<option value="${o.dn}">${o.name} (${o.dn})</option>`;
            if (inputParentOu) inputParentOu.innerHTML += `<option value="${o.dn}">${o.name} (${o.dn})</option>`;
            if (selectOuForObjects) selectOuForObjects.innerHTML += `<option value="${o.dn}">${o.name} (${o.dn})</option>`;
            if (selectLinkOu) selectLinkOu.innerHTML += `<option value="${o.dn}">${o.name} (${o.dn})</option>`;
        });
    }

    function populateGpoSelects(gposList) {
        if (!selectLinkGpo) return;
        selectLinkGpo.innerHTML = `<option value="">Selecione a GPO...</option>`;
        gposList.forEach(g => {
            selectLinkGpo.innerHTML += `<option value="${g.guid}">${g.name} (${g.guid})</option>`;
        });
    }

    // --- CARREGAR OBJETOS DA OU ---
    async function loadOuObjects(ouDn) {
        if (!ouDn) return;
        if (objectsOuTargetLabel) objectsOuTargetLabel.textContent = ouDn;
        if (ouObjectsTableBody) ouObjectsTableBody.innerHTML = `<tr><td colspan="4" class="text-center text-muted">Carregando objetos via samba-tool...</td></tr>`;

        try {
            const res = await authenticatedFetch(`/api/ous/objects?dn=${encodeURIComponent(ouDn)}`);
            const data = await res.json();
            if (data.success) {
                renderOuObjects(data.objects || []);
                if (data.cmd_preview) addCommandToLog(data.cmd_preview);
            } else {
                if (ouObjectsTableBody) ouObjectsTableBody.innerHTML = `<tr><td colspan="4" class="text-center text-danger">${data.error || 'Erro ao buscar objetos'}</td></tr>`;
            }
        } catch (err) {}
    }

    function renderOuObjects(objects) {
        if (!ouObjectsTableBody) return;
        ouObjectsTableBody.innerHTML = '';
        if (objects.length === 0) {
            ouObjectsTableBody.innerHTML = `<tr><td colspan="4" class="text-center text-muted">Esta OU está vazia (nenhum objeto encontrado).</td></tr>`;
            return;
        }

        objects.forEach(obj => {
            let badgeClass = 'user-type';
            let icon = '👤';
            if (obj.type === 'computer') {
                badgeClass = 'computer';
                icon = '🖥️';
            } else if (obj.type === 'organizationalUnit') {
                badgeClass = 'mock';
                icon = '🏢';
            }

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong style="font-family: var(--font-mono);">${icon} ${obj.name}</strong></td>
                <td><span class="badge ${badgeClass}">${obj.type}</span></td>
                <td><span style="font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-muted);">${obj.dn}</span></td>
                <td>
                    <button class="btn btn-sm btn-danger btn-delete-object" data-dn="${obj.dn}" data-type="${obj.type}">
                        Excluir Objeto
                    </button>
                </td>
            `;
            ouObjectsTableBody.appendChild(tr);
        });

        document.querySelectorAll('.btn-delete-object').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const dn = e.target.getAttribute('data-dn');
                const type = e.target.getAttribute('data-type');
                deleteObject(dn, type);
            });
        });
    }

    // --- OPERAÇÕES DE EXCLUSÃO E VÍNCULO ---

    async function deletePlatformUser(username) {
        if (!confirm(`Remover o acesso do operador '${username}' à plataforma Web?`)) return;

        try {
            const res = await authenticatedFetch('/api/platform-users', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username })
            });
            const data = await res.json();
            if (data.success) {
                showToast(data.message, 'success');
                fetchPlatformUsers();
            } else {
                showToast(data.error || 'Erro ao remover operador.', 'error');
            }
        } catch (err) {}
    }

    async function unlinkGpo(ouDn, gpoGuid) {
        if (!confirm(`Remover vínculo da GPO '${gpoGuid}' com a OU '${ouDn}'?`)) return;

        try {
            const res = await authenticatedFetch('/api/gpos/link', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ container_dn: ouDn, gpo_guid: gpoGuid })
            });
            const data = await res.json();
            if (data.success) {
                showToast(data.message, 'success');
                if (data.cmd_preview) addCommandToLog(data.cmd_preview);
                fetchGpos();
            } else {
                showToast(data.error || 'Erro ao desvincular GPO.', 'error');
            }
        } catch (err) {}
    }

    async function deleteUser(username) {
        if (!confirm(`Tem certeza que deseja excluir o usuário '${username}' do Active Directory?\nComando CLI: samba-tool user delete ${username}`)) return;

        try {
            const res = await authenticatedFetch('/api/users', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username })
            });
            const data = await res.json();
            if (data.success) {
                showToast(data.message, 'success');
                if (data.cmd_preview) addCommandToLog(data.cmd_preview);
                refreshAll();
            } else {
                showToast(data.error || 'Erro ao excluir usuário.', 'error');
            }
        } catch (err) {}
    }

    async function deleteComputer(name) {
        if (!confirm(`Tem certeza que deseja excluir o desktop/computador '${name}' do Active Directory?\nComando CLI: samba-tool computer delete ${name}`)) return;

        try {
            const res = await authenticatedFetch('/api/computers', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name })
            });
            const data = await res.json();
            if (data.success) {
                showToast(data.message, 'success');
                if (data.cmd_preview) addCommandToLog(data.cmd_preview);
                refreshAll();
            } else {
                showToast(data.error || 'Erro ao excluir computador.', 'error');
            }
        } catch (err) {}
    }

    async function deleteOu(ouDn) {
        if (!confirm(`Atenção: Excluir a OU '${ouDn}' removerá a estrutura e seus objetos associados.\nComando CLI: samba-tool ou delete "${ouDn}"`)) return;

        try {
            const res = await authenticatedFetch('/api/ous', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ dn: ouDn })
            });
            const data = await res.json();
            if (data.success) {
                showToast(data.message, 'success');
                if (data.cmd_preview) addCommandToLog(data.cmd_preview);
                refreshAll();
            } else {
                showToast(data.error || 'Erro ao excluir OU.', 'error');
            }
        } catch (err) {}
    }

    async function deleteObject(dn, type) {
        if (!confirm(`Deseja excluir o objeto '${dn}' do Active Directory?`)) return;

        try {
            const res = await authenticatedFetch('/api/objects', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ dn, type })
            });
            const data = await res.json();
            if (data.success) {
                showToast(data.message, 'success');
                if (data.cmd_preview) addCommandToLog(data.cmd_preview);
                loadOuObjects(selectOuForObjects ? selectOuForObjects.value : '');
                refreshAll();
            } else {
                showToast(data.error || 'Erro ao excluir objeto.', 'error');
            }
        } catch (err) {}
    }

    // --- FORMULÁRIOS DE CRIAÇÃO E TROCA DE SENHA ---

    formResetPassword?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('input-reset-username')?.value;
        const new_password = document.getElementById('input-reset-new-password')?.value;

        try {
            const res = await authenticatedFetch('/api/users/setpassword', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, new_password })
            });
            const data = await res.json();
            if (data.success) {
                showToast(data.message, 'success');
                if (data.cmd_preview) addCommandToLog(data.cmd_preview);
                closeModal(modalResetPassword);
                formResetPassword.reset();
            } else {
                showToast(data.error || 'Erro ao alterar senha do usuário.', 'error');
            }
        } catch (err) {}
    });

    formNewPlatformUser?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('input-plat-username')?.value;
        const password = document.getElementById('input-plat-password')?.value;
        const full_name = document.getElementById('input-plat-fullname')?.value;

        try {
            const res = await authenticatedFetch('/api/platform-users', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password, full_name })
            });
            const data = await res.json();
            if (data.success) {
                showToast(data.message, 'success');
                closeModal(modalNewPlatformUser);
                formNewPlatformUser.reset();
                fetchPlatformUsers();
            } else {
                showToast(data.error || 'Erro ao criar operador.', 'error');
            }
        } catch (err) {}
    });

    formNewUser?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('input-username')?.value;
        const password = document.getElementById('input-password')?.value;
        const given_name = document.getElementById('input-given-name')?.value;
        const surname = document.getElementById('input-surname')?.value;
        const mail = document.getElementById('input-email')?.value;
        const ou = inputUserOu ? inputUserOu.value : '';

        try {
            const res = await authenticatedFetch('/api/users', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password, given_name, surname, mail, ou })
            });
            const data = await res.json();
            if (data.success) {
                showToast(data.message, 'success');
                if (data.cmd_preview) addCommandToLog(data.cmd_preview);
                closeModal(modalNewUser);
                formNewUser.reset();
                refreshAll();
            } else {
                showToast(data.error || 'Erro ao criar usuário.', 'error');
            }
        } catch (err) {}
    });

    formNewComp?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const name = document.getElementById('input-comp-name')?.value;
        const os = document.getElementById('input-comp-os')?.value;
        const ip = document.getElementById('input-comp-ip')?.value;
        const ou = inputCompOu ? inputCompOu.value : '';

        try {
            const res = await authenticatedFetch('/api/computers', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, os, ip, ou })
            });
            const data = await res.json();
            if (data.success) {
                showToast(data.message, 'success');
                if (data.cmd_preview) addCommandToLog(data.cmd_preview);
                closeModal(modalNewComp);
                formNewComp.reset();
                refreshAll();
            } else {
                showToast(data.error || 'Erro ao adicionar computador.', 'error');
            }
        } catch (err) {}
    });

    formNewGpo?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const display_name = document.getElementById('input-gpo-name')?.value;
        const admin_user = document.getElementById('input-gpo-admin-user')?.value || '';
        const admin_pass = document.getElementById('input-gpo-admin-pass')?.value || '';

        try {
            const res = await authenticatedFetch('/api/gpos', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    display_name,
                    admin_user,
                    admin_pass
                })
            });
            const data = await res.json();
            if (data.success) {
                showToast(data.message, 'success');
                if (data.cmd_preview) addCommandToLog(data.cmd_preview);
                closeModal(modalNewGpo);
                formNewGpo.reset();
                fetchGpos();
            } else {
                showToast(data.error || 'Erro ao criar GPO.', 'error');
            }
        } catch (err) {}
    });

    formLinkGpo?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const gpo_guid = selectLinkGpo ? selectLinkGpo.value : '';
        const container_dn = selectLinkOu ? selectLinkOu.value : '';

        try {
            const res = await authenticatedFetch('/api/gpos/link', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ gpo_guid, container_dn })
            });
            const data = await res.json();
            if (data.success) {
                showToast(data.message, 'success');
                if (data.cmd_preview) addCommandToLog(data.cmd_preview);
                closeModal(modalLinkGpo);
                fetchGpos();
            } else {
                showToast(data.error || 'Erro ao vincular GPO.', 'error');
            }
        } catch (err) {}
    });

    formNewOu?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const name = document.getElementById('input-ou-name')?.value;
        const parent_dn = inputParentOu ? inputParentOu.value : '';

        try {
            const res = await authenticatedFetch('/api/ous', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, parent_dn })
            });
            const data = await res.json();
            if (data.success) {
                showToast(data.message, 'success');
                if (data.cmd_preview) addCommandToLog(data.cmd_preview);
                closeModal(modalNewOu);
                formNewOu.reset();
                refreshAll();
            } else {
                showToast(data.error || 'Erro ao criar OU.', 'error');
            }
        } catch (err) {}
    });

    // Live Command Preview - Registros seguros
    document.getElementById('input-username')?.addEventListener('input', updateCmdPreviews);
    document.getElementById('input-user-ou')?.addEventListener('change', updateCmdPreviews);
    document.getElementById('input-reset-new-password')?.addEventListener('input', updateCmdPreviews);
    document.getElementById('input-comp-name')?.addEventListener('input', updateCmdPreviews);
    document.getElementById('input-comp-ou')?.addEventListener('change', updateCmdPreviews);
    
    document.getElementById('input-gpo-name')?.addEventListener('input', updateCmdPreviews);
    document.getElementById('input-gpo-admin-user')?.addEventListener('input', updateCmdPreviews);
    document.getElementById('input-gpo-admin-pass')?.addEventListener('input', updateCmdPreviews);

    selectLinkGpo?.addEventListener('change', updateCmdPreviews);
    selectLinkOu?.addEventListener('change', updateCmdPreviews);
    document.getElementById('input-ou-name')?.addEventListener('input', updateCmdPreviews);
    document.getElementById('input-parent-ou')?.addEventListener('change', updateCmdPreviews);

    function updateCmdPreviews() {
        if (userCmdPreview) {
            const uName = document.getElementById('input-username')?.value || 'username';
            const uOu = (inputUserOu && inputUserOu.value) ? ` --userou="${inputUserOu.value}"` : '';
            userCmdPreview.textContent = `sudo samba-tool user create ${uName} '*****'${uOu}`;
        }

        if (resetPassCmdPreview) {
            const rUser = document.getElementById('input-reset-username')?.value || 'username';
            resetPassCmdPreview.textContent = `sudo samba-tool user setpassword ${rUser} --newpassword='*****'`;
        }

        if (compCmdPreview) {
            const cName = document.getElementById('input-comp-name')?.value || 'DESKTOP-01';
            const cOu = (inputCompOu && inputCompOu.value) ? ` --computerou="${inputCompOu.value}"` : '';
            compCmdPreview.textContent = `sudo samba-tool computer create ${cName}${cOu}`;
        }

        if (gpoCmdPreview) {
            const gName = document.getElementById('input-gpo-name')?.value.trim() || 'Nome_GPO';
            const gUserEl = document.getElementById('input-gpo-admin-user');
            const gPassEl = document.getElementById('input-gpo-admin-pass');

            const gUser = gUserEl ? gUserEl.value.trim() : '';
            const gPass = gPassEl ? gPassEl.value : '';

            let cmd = `sudo samba-tool gpo create "${gName}"`;

            if (gUser) {
                cmd += ` -U "${gUser}"`;
            }
            if (gPass) {
                cmd += ` --password="*****"`;
            }

            gpoCmdPreview.textContent = cmd;
        }

        if (gpoLinkCmdPreview) {
            const lGpo = (selectLinkGpo && selectLinkGpo.value) ? selectLinkGpo.value : '{GUID}';
            const lOu = (selectLinkOu && selectLinkOu.value) ? selectLinkOu.value : 'OU=Financeiro,DC=empresa,DC=local';
            gpoLinkCmdPreview.textContent = `sudo samba-tool gpo setlink "${lOu}" "${lGpo}"`;
        }

        if (ouCmdPreview) {
            const ouName = document.getElementById('input-ou-name')?.value || 'NomeOU';
            const pOu = (inputParentOu && inputParentOu.value) ? `,${inputParentOu.value}` : `,${appState.domainDn}`;
            ouCmdPreview.textContent = `sudo samba-tool ou create "OU=${ouName}${pOu}"`;
        }
    }

    // --- TERMINAL LOG & HELPERS ---

    function addCommandToLog(cmdStr) {
        if (!appState.cmdHistory.includes(cmdStr)) {
            appState.cmdHistory.push(cmdStr);
        }
        if (dashboardLastCmd) dashboardLastCmd.textContent = cmdStr;
        if (liveCommandLog) liveCommandLog.textContent = `# Log de comandos executados nesta sessão:\n` + appState.cmdHistory.join('\n');
    }

    copyTerminalBtn?.addEventListener('click', () => {
        navigator.clipboard.writeText(appState.cmdHistory.join('\n'));
        showToast('Comandos copiados para a área de transferência!', 'success');
    });

    // Modais Event Listeners
    openNewUserModalBtn?.addEventListener('click', () => openModal(modalNewUser));
    openNewCompModalBtn?.addEventListener('click', () => openModal(modalNewComp));
    openNewOuModalBtn?.addEventListener('click', () => openModal(modalNewOu));
    openNewGpoModalBtn?.addEventListener('click', () => openModal(modalNewGpo));
    openLinkGpoModalBtn?.addEventListener('click', () => openModal(modalLinkGpo));
    openNewPlatformUserModalBtn?.addEventListener('click', () => openModal(modalNewPlatformUser));
    
    closeModals.forEach(b => b.addEventListener('click', () => {
        closeModal(modalNewUser);
        closeModal(modalResetPassword);
        closeModal(modalNewComp);
        closeModal(modalNewOu);
        closeModal(modalNewGpo);
        closeModal(modalLinkGpo);
        closeModal(modalNewPlatformUser);
    }));

    function openModal(modal) {
        if (modal) {
            modal.classList.add('active');
            updateCmdPreviews();
        }
    }
    function closeModal(modal) {
        if (modal) modal.classList.remove('active');
    }

    // Filtros de busca
    searchUsersInput?.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase();
        const filtered = appState.users.filter(u => 
            u.username.toLowerCase().includes(query) || 
            (u.email && u.email.toLowerCase().includes(query)) ||
            u.ou.toLowerCase().includes(query)
        );
        renderUsers(filtered);
    });

    searchComputersInput?.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase();
        const filtered = appState.computers.filter(c => 
            c.name.toLowerCase().includes(query) || 
            (c.os && c.os.toLowerCase().includes(query)) ||
            (c.ip && c.ip.toLowerCase().includes(query)) ||
            c.ou.toLowerCase().includes(query)
        );
        renderComputers(filtered);
    });

    searchPlatformUsersInput?.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase();
        const filtered = appState.platformUsers.filter(op => 
            op.username.toLowerCase().includes(query) || 
            (op.full_name && op.full_name.toLowerCase().includes(query))
        );
        renderPlatformUsers(filtered);
    });

    searchGposInput?.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase();
        const filtered = appState.gpos.filter(g => 
            g.name.toLowerCase().includes(query) || 
            g.guid.toLowerCase().includes(query)
        );
        renderGposTable(filtered);
    });

    searchOusInput?.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase();
        const filtered = appState.ous.filter(o => 
            o.name.toLowerCase().includes(query) || 
            o.dn.toLowerCase().includes(query)
        );
        renderOus(filtered);
    });

    btnFetchOuObjects?.addEventListener('click', () => {
        if (selectOuForObjects) loadOuObjects(selectOuForObjects.value);
    });

    modeSwitch?.addEventListener('change', (e) => {
        toggleMockMode(e.target.checked);
    });

    async function fetchSystemInfo() {
        try {
            const res = await fetch('/api/system-info');
            const data = await res.json();
            if (data.success && data.system_info) {
                renderSystemInfo(data.system_info);
            }
        } catch (err) {
            console.error('Erro ao buscar métricas do sistema:', err);
        }
    }

    function renderSystemInfo(info) {
        if (!info) return;

        // 1. CPU
        if (info.cpu) {
            const cpuUsage = Math.round(info.cpu.usage_percent || 0);
            const cpuPercentElem = document.getElementById('sys-cpu-percent');
            const cpuPercentBadge = document.getElementById('sys-cpu-percent-badge');
            const cpuCoresElem = document.getElementById('sys-cpu-cores');
            const cpuBarElem = document.getElementById('sys-cpu-bar');
            const cpuModelElem = document.getElementById('sys-cpu-model');

            if (cpuPercentElem) cpuPercentElem.textContent = `${cpuUsage}% em uso`;
            if (cpuPercentBadge) {
                cpuPercentBadge.textContent = `${cpuUsage}%`;
                cpuPercentBadge.className = `sys-metric-badge ${cpuUsage > 80 ? 'danger' : cpuUsage > 60 ? 'warning' : ''}`;
            }
            if (cpuCoresElem) cpuCoresElem.textContent = `${info.cpu.cores || 1} Núcleos`;
            if (cpuBarElem) cpuBarElem.style.width = `${Math.min(cpuUsage, 100)}%`;
            if (cpuModelElem) cpuModelElem.textContent = info.cpu.model || 'Processador Genérico';
        }

        // 2. RAM
        if (info.ram) {
            const ramUsage = Math.round(info.ram.usage_percent || 0);
            const ramBadge = document.getElementById('sys-ram-percent-badge');
            const ramBar = document.getElementById('sys-ram-bar');
            const ramDetails = document.getElementById('sys-ram-details');
            const ramFree = document.getElementById('sys-ram-free');

            if (ramBadge) {
                ramBadge.textContent = `${ramUsage}%`;
                ramBadge.className = `sys-metric-badge ${ramUsage > 85 ? 'danger' : ramUsage > 70 ? 'warning' : ''}`;
            }
            if (ramBar) ramBar.style.width = `${Math.min(ramUsage, 100)}%`;
            if (ramDetails) ramDetails.textContent = `${info.ram.used_gb || 0} GB / ${info.ram.total_gb || 0} GB`;
            if (ramFree) ramFree.textContent = `Livre: ${info.ram.free_gb || 0} GB`;
        }

        // 3. DISCO
        if (info.disk) {
            const diskUsage = Math.round(info.disk.usage_percent || 0);
            const diskBadge = document.getElementById('sys-disk-percent-badge');
            const diskBar = document.getElementById('sys-disk-bar');
            const diskDetails = document.getElementById('sys-disk-details');
            const diskFree = document.getElementById('sys-disk-free');

            if (diskBadge) {
                diskBadge.textContent = `${diskUsage}%`;
                diskBadge.className = `sys-metric-badge ${diskUsage > 90 ? 'danger' : diskUsage > 75 ? 'warning' : ''}`;
            }
            if (diskBar) diskBar.style.width = `${Math.min(diskUsage, 100)}%`;
            if (diskDetails) diskDetails.textContent = `${info.disk.used_gb || 0} GB / ${info.disk.total_gb || 0} GB`;
            if (diskFree) diskFree.textContent = `Livre: ${info.disk.free_gb || 0} GB`;
        }

        // 4. SISTEMA OPERACIONAL
        if (info.os) {
            const osNameElem = document.getElementById('sys-os-name');
            const osKernelElem = document.getElementById('sys-os-kernel');
            const osBadgeElem = document.getElementById('sys-os-badge');
            const cpuArchElem = document.getElementById('sys-cpu-arch');

            if (osNameElem) osNameElem.textContent = info.os.name || 'Linux Server';
            if (osKernelElem) osKernelElem.textContent = `Kernel: ${info.os.kernel || '--'}`;
            if (osBadgeElem) {
                const name = info.os.name || '';
                osBadgeElem.textContent = name.includes('Ubuntu') ? 'Ubuntu' : name.includes('Debian') ? 'Debian' : name.includes('Pop') ? 'Pop!_OS' : 'Linux';
            }
            if (cpuArchElem) cpuArchElem.textContent = info.os.architecture || 'x86_64';
        }

        // 5. VELOCIDADE DA INTERNET & REDE
        if (info.network) {
            const netDown = document.getElementById('sys-net-download');
            const netUp = document.getElementById('sys-net-upload');
            const netInterface = document.getElementById('sys-net-interface');
            const netLatency = document.getElementById('sys-net-latency');
            const netBadge = document.getElementById('sys-net-status-badge');

            if (netDown) netDown.textContent = info.network.download_speed || '0.0 Mbps';
            if (netUp) netUp.textContent = info.network.upload_speed || '0.0 Mbps';
            if (netInterface) netInterface.textContent = info.network.interface_status || 'Online (1 Gbps)';
            if (netLatency) netLatency.textContent = `Ping: ${info.network.latency || '12 ms'}`;
            if (netBadge) netBadge.textContent = info.network.status || 'Conectado';
        }
    }

    refreshBtn?.addEventListener('click', refreshAll);

    function refreshAll() {
        fetchStatus();
        fetchSystemInfo();
        fetchPlatformUsers();
        fetchUsers();
        fetchComputers();
        fetchOus();
        fetchGpos();
    }

    // --- INTEGRAÇÃO DA ANÁLISE DE SEGURANÇA VIA IA ---

    const btnRunAI = document.getElementById("btn-run-ai-analysis");
    const threatBadge = document.getElementById("ai-threat-level");
    const riskScoreDisplay = document.getElementById("ai-risk-score");
    const insightsContainer = document.getElementById("ai-insights-container");

    async function fetchAISecurityAnalysis() {
        if (!btnRunAI) return;

        btnRunAI.disabled = true;
        btnRunAI.innerHTML = "Analisando...";

        try {
            const response = await authenticatedFetch("/api/ai/security-analysis");
            const data = await response.json();

            if (data.success) {
                const analysis = data.analysis;
                const level = (analysis.threat_level || "low").toLowerCase();

                if (threatBadge) {
                    threatBadge.innerText = level.toUpperCase();
                    threatBadge.className = `ai-threat-badge ${level}`;
                }

                if (riskScoreDisplay) {
                    riskScoreDisplay.innerHTML = `Pontuação de Risco: <strong>${analysis.risk_score || 0} / 100</strong>`;
                }

                if (insightsContainer) {
                    insightsContainer.innerHTML = "";
                    if (analysis.insights && analysis.insights.length > 0) {
                        analysis.insights.forEach(insight => {
                            const li = document.createElement("li");
                            li.innerText = insight;
                            insightsContainer.appendChild(li);
                        });
                    } else {
                        insightsContainer.innerHTML = "<li>Nenhuma anomalia detectada no momento.</li>";
                    }
                }
                
                showToast("Varredura de IA concluída com sucesso!", "success");
            } else {
                showToast(data.error || "Erro ao processar análise da IA.", "error");
            }
        } catch (err) {
            console.error("Falha ao se comunicar com a API de IA:", err);
            showToast("Erro de conexão ao executar a varredura.", "error");
        } finally {
            btnRunAI.disabled = false;
            btnRunAI.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg> <span>Executar Varredura</span>`;
        }
    }

    btnRunAI?.addEventListener("click", fetchAISecurityAnalysis);

    // Atualização em tempo real das métricas do sistema a cada 5 segundos
    setInterval(() => {
        if (appState.token) {
            fetchSystemInfo();
        }
    }, 5000);

    // Inicialização da Tela de Autenticação
    checkAuthUI();
});