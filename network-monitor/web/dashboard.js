// NetPulse Dashboard JavaScript
const API_URL = 'http://localhost:8000/api';

// Global variables
let token = null;
let user = null;
let editingDeviceId = null;
let refreshInterval = null;
let currentStatusFilter = 'all';

// ==================== Helper Functions ====================

function escapeHtml(str) { 
    if (!str) return '';
    return str.replace(/[&<>]/g, function(m) { 
        const escapes = {'&':'&amp;','<':'&lt;','>':'&gt;'};
        return escapes[m];
    }); 
}

// ==================== Authentication ====================

function checkAuth() {
    token = localStorage.getItem('netpulse_token');
    const userStr = localStorage.getItem('netpulse_user');
    
    if (!token || !userStr) {
        window.location.href = 'login.html';
        return false;
    }
    
    try {
        user = JSON.parse(userStr);
        const usernameSpan = document.getElementById('username-display');
        if (usernameSpan && user.username) {
            usernameSpan.textContent = user.username;
        }
    } catch (e) {
        console.error('Error parsing user data:', e);
        window.location.href = 'login.html';
        return false;
    }
    return true;
}

async function logout() {
    try {
        await fetch(`${API_URL}/auth/logout?token=${token}`, { method: 'POST' });
    } catch(e) {
        console.error('Logout error:', e);
    }
    localStorage.removeItem('netpulse_token');
    localStorage.removeItem('netpulse_user');
    window.location.href = 'login.html';
}

// ==================== Alert Email Management ====================

async function loadAlertEmail() {
    if (!token) return;
    
    try {
        const response = await fetch(`${API_URL}/user/alert-emails?token=${token}`);
        const data = await response.json();
        
        if (data.alert_emails && data.alert_emails.length > 0) {
            const savedEmail = data.alert_emails[0];
            document.getElementById('alert-email').value = savedEmail;
            document.getElementById('current-alert-email').textContent = savedEmail;
            document.getElementById('current-email-display').style.display = 'block';
            
            user.alert_email = savedEmail;
            localStorage.setItem('netpulse_user', JSON.stringify(user));
        } else {
            document.getElementById('alert-email').value = '';
            document.getElementById('current-email-display').style.display = 'none';
        }
    } catch (error) {
        console.error('Error loading alert email:', error);
        if (user && user.alert_email) {
            document.getElementById('alert-email').value = user.alert_email;
            document.getElementById('current-alert-email').textContent = user.alert_email;
            document.getElementById('current-email-display').style.display = 'block';
        }
    }
}

async function saveAlertEmail() {
    const alertEmail = document.getElementById('alert-email').value.trim();
    if (!alertEmail) {
        alert('Please enter an email address');
        return;
    }
    
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(alertEmail)) {
        alert('Please enter a valid email address');
        return;
    }
    
    if (!token) {
        alert('Please login again');
        window.location.href = 'login.html';
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/user/alert-email?token=${token}&alert_email=${encodeURIComponent(alertEmail)}`, {
            method: 'POST'
        });
        const data = await response.json();
        
        if (data.success) {
            user.alert_email = alertEmail;
            localStorage.setItem('netpulse_user', JSON.stringify(user));
            document.getElementById('current-alert-email').textContent = alertEmail;
            document.getElementById('current-email-display').style.display = 'block';
            alert('Alert email saved successfully');
        } else {
            alert('Failed to save alert email');
        }
    } catch (error) {
        console.error('Error saving alert email:', error);
        alert('Error saving alert email');
    }
}

async function removeAlertEmail() {
    const currentEmail = document.getElementById('alert-email').value.trim();
    if (!currentEmail) {
        alert('No email to remove');
        return;
    }
    
    if (!confirm(`Remove ${currentEmail} from alert notifications?`)) return;
    
    if (!token) {
        alert('Please login again');
        window.location.href = 'login.html';
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/user/alert-email?token=${token}&alert_email=${encodeURIComponent(currentEmail)}`, {
            method: 'DELETE'
        });
        const data = await response.json();
        
        if (data.success) {
            user.alert_email = null;
            localStorage.setItem('netpulse_user', JSON.stringify(user));
            document.getElementById('alert-email').value = '';
            document.getElementById('current-email-display').style.display = 'none';
            alert('Alert email removed successfully');
        } else {
            alert('Failed to remove alert email');
        }
    } catch (error) {
        console.error('Error removing alert email:', error);
        alert('Error removing alert email');
    }
}

async function testAlertEmails() {
    if (!token) {
        alert('Please login again');
        window.location.href = 'login.html';
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/user/alert-emails/test?token=${token}`, {
            method: 'POST'
        });
        const data = await response.json();
        
        if (data.success) {
            alert('Test alert sent successfully');
        } else {
            alert('Failed to send test alert');
        }
    } catch (error) {
        console.error('Error sending test alert:', error);
        alert('Error sending test alert');
    }
}

// ==================== Monitoring Control ====================

async function startMonitoring() {
    const intervalInput = document.getElementById('interval-input');
    const interval = intervalInput ? intervalInput.value : '30';
    
    if (!token) {
        alert('Please login again');
        window.location.href = 'login.html';
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/monitoring/start?token=${token}&interval=${interval}`, { 
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (response.ok) {
            alert('Monitoring started successfully');
            updateMonitoringStatus();
        } else {
            alert('Failed to start monitoring');
        }
    } catch (error) {
        console.error('Start monitoring error:', error);
        alert('Error starting monitoring');
    }
}

async function stopMonitoring() {
    if (!token) {
        alert('Please login again');
        window.location.href = 'login.html';
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/monitoring/stop?token=${token}`, { 
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (response.ok) {
            alert('Monitoring stopped');
            updateMonitoringStatus();
        } else {
            alert('Failed to stop monitoring');
        }
    } catch (error) {
        console.error('Stop monitoring error:', error);
        alert('Error stopping monitoring');
    }
}

async function updateMonitoringStatus() {
    if (!token) return;
    
    try {
        const response = await fetch(`${API_URL}/monitoring/status?token=${token}`);
        if (!response.ok) return;
        
        const status = await response.json();
        const statusPill = document.getElementById('monitor-status-pill');
        if (statusPill) {
            if (status.running) {
                statusPill.textContent = 'RUNNING';
                statusPill.className = 'status-pill status-active';
            } else {
                statusPill.textContent = 'STOPPED';
                statusPill.className = 'status-pill status-inactive';
            }
        }
    } catch (error) {
        console.error('Error fetching monitoring status:', error);
    }
}

// ==================== Device Management ====================

async function loadDevices() {
    if (!token) {
        window.location.href = 'login.html';
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/user/devices?token=${token}`);
        if (!response.ok) {
            throw new Error('Failed to load devices');
        }
        
        const devices = await response.json();
        
        // Apply status filter if active
        let filteredDevices = devices;
        if (currentStatusFilter && currentStatusFilter !== 'all') {
            filteredDevices = devices.filter(d => {
                const status = (d.status || 'UNKNOWN').toUpperCase();
                return status === currentStatusFilter.toUpperCase();
            });
        }
        
        displayDevices(filteredDevices);
        updateStats(devices);
    } catch (error) {
        console.error('Error loading devices:', error);
        const tableDiv = document.getElementById('devices-table');
        if (tableDiv) {
            tableDiv.innerHTML = '<div class="error-state">Failed to load devices: ' + escapeHtml(error.message) + '</div>';
        }
    }
}

function updateStats(devices) {
    let up = 0, degraded = 0, down = 0;
    for (const d of devices) {
        const status = (d.status || 'UNKNOWN').toUpperCase();
        if (status === 'UP') up++;
        else if (status === 'DEGRADED') degraded++;
        else if (status === 'DOWN') down++;
    }
    
    document.getElementById('total-devices').textContent = devices.length;
    document.getElementById('up-count').textContent = up;
    document.getElementById('degraded-count').textContent = degraded;
    document.getElementById('down-count').textContent = down;
}

function displayDevices(devices) {
    const searchInput = document.getElementById('device-search');
    const query = searchInput ? searchInput.value.trim().toLowerCase() : '';
    
    let filtered = devices;
    
    // Apply search filter
    if (query) {
        filtered = filtered.filter(d => {
            const name = (d.name || '').toLowerCase();
            const ip = (d.ip_address || d.ip || '').toLowerCase();
            const group = (d.device_group || 'Default').toLowerCase();
            return name.includes(query) || ip.includes(query) || group.includes(query);
        });
    }
    
    const deviceCountSpan = document.getElementById('device-count');
    if (deviceCountSpan) deviceCountSpan.textContent = filtered.length;
    
    if (filtered.length === 0) {
        document.getElementById('devices-table').innerHTML = '<div class="empty-state">No devices found. Click "Add Device" to get started.</div>';
        return;
    }
    
    let html = `<table class="device-table">
        <thead>
            <tr>
                <th>Group</th>
                <th>Device</th>
                <th>Status</th>
                <th>Latency</th>
                <th>Last Check</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>`;
    
    for (const d of filtered) {
        const group = d.device_group || 'Default';
        const ip = d.ip_address || d.ip || 'N/A';
        const statusText = d.status || 'UNKNOWN';
        
        let statusClass = 'status-unknown';
        if (statusText === 'UP') statusClass = 'status-up';
        else if (statusText === 'DEGRADED') statusClass = 'status-degraded';
        else if (statusText === 'DOWN') statusClass = 'status-down';
        
        const latency = d.latency_ms ? `${d.latency_ms.toFixed(1)}ms` : '—';
        const lastCheck = d.last_check ? new Date(d.last_check).toLocaleString() : 'Never';
        
        html += `<tr>
            <td data-label="Group"><span class="group-badge">${escapeHtml(group)}</span></td>
            <td data-label="Device">
                <div class="device-name">${escapeHtml(d.name)}</div>
                <div class="device-ip">${escapeHtml(ip)}</div>
            </td>
            <td data-label="Status"><span class="status-badge ${statusClass}">${escapeHtml(statusText)}</span></td>
            <td data-label="Latency" class="latency-value">${latency}</td>
            <td data-label="Last Check" class="last-check">${escapeHtml(lastCheck)}</div></td>
            <td data-label="Actions">
                <button class="action-btn edit" onclick="openEditModal('${d.device_id}', '${escapeHtml(d.name)}', '${escapeHtml(ip)}', '${escapeHtml(group)}')">Edit</button>
                <button class="action-btn delete" onclick="deleteDevice('${d.device_id}')">Delete</button>
            </td>
        </tr>`;
    }
    html += `</tbody></table>`;
    
    document.getElementById('devices-table').innerHTML = html;
}

// ==================== Modal Operations ====================

function openAddModal() {
    editingDeviceId = null;
    document.getElementById('modal-title').textContent = 'Add Device';
    document.getElementById('device-name').value = '';
    document.getElementById('device-ip').value = '';
    document.getElementById('device-group').value = '';
    document.getElementById('modal').style.display = 'flex';
}

function openEditModal(id, name, ip, group) {
    editingDeviceId = id;
    document.getElementById('modal-title').textContent = 'Edit Device';
    document.getElementById('device-name').value = name;
    document.getElementById('device-ip').value = ip;
    document.getElementById('device-group').value = group;
    document.getElementById('modal').style.display = 'flex';
}

function closeModal() {
    document.getElementById('modal').style.display = 'none';
    editingDeviceId = null;
}

async function saveDevice() {
    const name = document.getElementById('device-name').value.trim();
    const ip = document.getElementById('device-ip').value.trim();
    const group = document.getElementById('device-group').value.trim() || 'Default';
    
    if (!name || !ip) { 
        alert('Please enter name and IP'); 
        return; 
    }
    
    if (!token) {
        alert('Please login again');
        window.location.href = 'login.html';
        return;
    }
    
    try {
        let response;
        
        if (editingDeviceId) {
            response = await fetch(`${API_URL}/user/devices/${editingDeviceId}?token=${token}&name=${encodeURIComponent(name)}&ip=${encodeURIComponent(ip)}&group=${encodeURIComponent(group)}`, { 
                method: 'PUT' 
            });
        } else {
            response = await fetch(`${API_URL}/user/devices?token=${token}&name=${encodeURIComponent(name)}&ip=${encodeURIComponent(ip)}&group=${encodeURIComponent(group)}`, { 
                method: 'POST' 
            });
        }
        
        const data = await response.json();
        
        if (response.ok && data.success !== false) {
            alert(editingDeviceId ? 'Device updated successfully' : 'Device added successfully');
            closeModal();
            await loadDevices();
            updateMonitoringStatus();
        } else {
            alert(editingDeviceId ? 'Failed to update device' : 'Failed to add device');
        }
    } catch (error) {
        console.error('Error saving device:', error);
        alert('Error saving device');
    }
}

async function deleteDevice(id) {
    if (!confirm('Delete this device?')) return;
    
    if (!token) {
        alert('Please login again');
        window.location.href = 'login.html';
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/user/devices/${id}?token=${token}`, { method: 'DELETE' });
        const data = await response.json();
        
        if (response.ok && data.success !== false) {
            alert('Device deleted successfully');
            await loadDevices();
            updateMonitoringStatus();
        } else {
            alert('Failed to delete device');
        }
    } catch (error) {
        console.error('Error deleting device:', error);
        alert('Error deleting device');
    }
}

// ==================== Clickable Stats Cards ====================

function setupClickableCards() {
    const cards = document.querySelectorAll('.clickable-card');
    
    cards.forEach(card => {
        card.addEventListener('click', function() {
            const filter = this.getAttribute('data-filter');
            
            // Remove active class from all cards
            cards.forEach(c => c.classList.remove('active-filter'));
            
            // Add active class to clicked card
            this.classList.add('active-filter');
            
            // Update global filter
            currentStatusFilter = filter;
            
            // Reload devices with filter
            loadDevices();
        });
    });
}

// ==================== Interval Presets ====================

function setupIntervalPresets() {
    const presetBtns = document.querySelectorAll('.preset-btn');
    const intervalInput = document.getElementById('interval-input');
    
    presetBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const interval = this.dataset.interval;
            if (intervalInput) intervalInput.value = interval;
            presetBtns.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
        });
    });
}

// ==================== Search ====================

function setupSearch() {
    const searchInput = document.getElementById('device-search');
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            loadDevices();
        });
    }
}

// ==================== Auto Refresh ====================

function startAutoRefresh() {
    if (refreshInterval) clearInterval(refreshInterval);
    refreshInterval = setInterval(() => { 
        loadDevices(); 
        updateMonitoringStatus(); 
    }, 5000);
}

// ==================== Initialization ====================

function init() {
    if (checkAuth()) {
        loadAlertEmail();
        loadDevices();
        updateMonitoringStatus();
        startAutoRefresh();
        setupClickableCards();
        setupIntervalPresets();
        setupSearch();
    }
}

// Close modal when clicking outside
window.onclick = function(e) { 
    const modal = document.getElementById('modal');
    if (e.target === modal) {
        closeModal();
    }
};

// Start everything when page loads
document.addEventListener('DOMContentLoaded', init);
// Global filter variable
let currentStatusFilter = 'all';

// ==================== Clickable Stats Cards ====================

function setupClickableCards() {
    const cards = document.querySelectorAll('.clickable-card');
    
    // Set active class on the currently active filter
    cards.forEach(card => {
        const filter = card.getAttribute('data-filter');
        if (filter === currentStatusFilter) {
            card.classList.add('active');
        } else {
            card.classList.remove('active');
        }
    });
    
    // Add click event listeners
    cards.forEach(card => {
        card.addEventListener('click', function(e) {
            const filter = this.getAttribute('data-filter');
            
            // Update global filter
            currentStatusFilter = filter;
            
            // Save to sessionStorage to persist across page refreshes
            sessionStorage.setItem('statusFilter', filter);
            
            // Update active class on all cards
            cards.forEach(c => c.classList.remove('active'));
            this.classList.add('active');
            
            // Reload devices with new filter
            loadDevices();
        });
    });
}

// ==================== Load Devices with Filter ====================

async function loadDevices() {
    if (!token) {
        window.location.href = 'login.html';
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/user/devices?token=${token}`);
        if (!response.ok) {
            throw new Error('Failed to load devices');
        }
        
        const devices = await response.json();
        
        // Apply status filter
        let filteredDevices = devices;
        if (currentStatusFilter && currentStatusFilter !== 'all') {
            filteredDevices = devices.filter(device => {
                const status = (device.status || 'UNKNOWN').toUpperCase();
                return status === currentStatusFilter.toUpperCase();
            });
        }
        
        // Display filtered devices
        displayDevices(filteredDevices);
        
        // Always show actual stats (not filtered)
        updateStats(devices);
        
    } catch (error) {
        console.error('Error loading devices:', error);
        const tableDiv = document.getElementById('devices-table');
        if (tableDiv) {
            tableDiv.innerHTML = '<div class="error-state">Failed to load devices: ' + escapeHtml(error.message) + '</div>';
        }
    }
}

// ==================== Display Devices ====================

function displayDevices(devices) {
    const searchInput = document.getElementById('device-search');
    const query = searchInput ? searchInput.value.trim().toLowerCase() : '';
    
    let filtered = devices;
    
    // Apply search filter
    if (query) {
        filtered = filtered.filter(device => {
            const name = (device.name || '').toLowerCase();
            const ip = (device.ip_address || device.ip || '').toLowerCase();
            const group = (device.device_group || 'Default').toLowerCase();
            return name.includes(query) || ip.includes(query) || group.includes(query);
        });
    }
    
    const deviceCountSpan = document.getElementById('device-count');
    if (deviceCountSpan) deviceCountSpan.textContent = filtered.length;
    
    if (filtered.length === 0) {
        document.getElementById('devices-table').innerHTML = '<div class="empty-state">No devices found. Click "Add Device" to get started.</div>';
        return;
    }
    
    let html = `<table class="device-table">
        <thead>
            <tr>
                <th>Group</th>
                <th>Device</th>
                <th>Status</th>
                <th>Latency</th>
                <th>Last Check</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>`;
    
    for (const device of filtered) {
        const group = device.device_group || 'Default';
        const ip = device.ip_address || device.ip || 'N/A';
        const statusText = device.status || 'UNKNOWN';
        
        let statusClass = 'status-unknown';
        if (statusText === 'UP') statusClass = 'status-up';
        else if (statusText === 'DEGRADED') statusClass = 'status-degraded';
        else if (statusText === 'DOWN') statusClass = 'status-down';
        
        const latency = device.latency_ms ? `${device.latency_ms.toFixed(1)}ms` : '—';
        const lastCheck = device.last_check ? new Date(device.last_check).toLocaleString() : 'Never';
        
        html += `<tr>
            <td data-label="Group"><span class="group-badge">${escapeHtml(group)}</span></td>
            <td data-label="Device">
                <div class="device-name">${escapeHtml(device.name)}</div>
                <div class="device-ip">${escapeHtml(ip)}</div>
            </td>
            <td data-label="Status"><span class="status-badge ${statusClass}">${escapeHtml(statusText)}</span></td>
            <td data-label="Latency" class="latency-value">${latency}</td>
            <td data-label="Last Check" class="last-check">${escapeHtml(lastCheck)}</div></td>
            <td data-label="Actions">
                <button class="action-btn edit" onclick="openEditModal('${device.device_id}', '${escapeHtml(device.name)}', '${escapeHtml(ip)}', '${escapeHtml(group)}')">Edit</button>
                <button class="action-btn delete" onclick="deleteDevice('${device.device_id}')">Delete</button>
            </td>
        </tr>`;
    }
    html += `</tbody></table>`;
    
    document.getElementById('devices-table').innerHTML = html;
}

// ==================== Update Statistics ====================

function updateStats(devices) {
    let up = 0, degraded = 0, down = 0;
    for (const device of devices) {
        const status = (device.status || 'UNKNOWN').toUpperCase();
        if (status === 'UP') up++;
        else if (status === 'DEGRADED') degraded++;
        else if (status === 'DOWN') down++;
    }
    
    document.getElementById('total-devices').textContent = devices.length;
    document.getElementById('up-count').textContent = up;
    document.getElementById('degraded-count').textContent = degraded;
    document.getElementById('down-count').textContent = down;
}

// ==================== Initialize Filter on Page Load ====================

function initFilters() {
    // Load saved filter from sessionStorage
    const savedFilter = sessionStorage.getItem('statusFilter');
    if (savedFilter && ['all', 'UP', 'DEGRADED', 'DOWN'].includes(savedFilter)) {
        currentStatusFilter = savedFilter;
    } else {
        currentStatusFilter = 'all';
    }
    
    // Setup clickable cards
    setupClickableCards();
}

// ==================== Modified Init Function ====================

function init() {
    if (checkAuth()) {
        initFilters(); // Initialize filters first
        loadAlertEmail();
        loadDevices();
        updateMonitoringStatus();
        startAutoRefresh();
        setupIntervalPresets();
        setupSearch();
    }
}