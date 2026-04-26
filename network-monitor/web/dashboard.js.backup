// NetPulse Dashboard JavaScript
const API_URL = 'http://localhost:8000/api';

// Global variables
let token = null;
let user = null;
let editingDeviceId = null;
let refreshInterval = null;
let currentFilter = 'all';

// ==================== Helper Functions ====================

// Helper for authenticated requests (token in URL)
async function authFetch(endpoint, options = {}) {
    if (!token) {
        window.location.href = 'login.html';
        throw new Error('No token');
    }
    
    // Ensure endpoint starts correctly
    let urlEndpoint = endpoint;
    if (!endpoint.startsWith('/api/') && !endpoint.startsWith('api/')) {
        urlEndpoint = `/api/${endpoint}`;
    }
    
    const separator = urlEndpoint.includes('?') ? '&' : '?';
    const url = `${API_URL}${urlEndpoint}${separator}token=${token}`;
    
    console.log('Fetching URL:', url);
    
    const response = await fetch(url, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...options.headers
        }
    });
    
    if (response.status === 401) {
        localStorage.removeItem('netpulse_token');
        localStorage.removeItem('netpulse_user');
        window.location.href = 'login.html';
        throw new Error('Token expired');
    }
    
    return response;
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
        const alertEmailInput = document.getElementById('alert-email');
        if (alertEmailInput && user.alert_email) {
            alertEmailInput.value = user.alert_email;
        }
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

async function loadAlertEmails() {
    if (!token) return;
    
    try {
        const response = await fetch(`${API_URL}/user/alert-emails?token=${token}`);
        const data = await response.json();
        displayAlertEmails(data.alert_emails);
    } catch (error) {
        console.error('Error loading alert emails:', error);
        const container = document.getElementById('alert-emails-list');
        if (container) {
            container.innerHTML = '<div class="error-msg">Failed to load alert emails</div>';
        }
    }
}

function displayAlertEmails(emails) {
    const container = document.getElementById('alert-emails-list');
    if (!container) return;
    
    if (!emails || emails.length === 0) {
        container.innerHTML = '<div style="color: #6b7280; padding: 10px;">No alert emails configured. Add one above to receive notifications.</div>';
        return;
    }
    
    let html = '<div style="display: flex; flex-wrap: wrap; gap: 10px;">';
    for (const email of emails) {
        html += `
            <div style="display: inline-flex; align-items: center; gap: 8px; background: #f3f4f6; padding: 6px 12px; border-radius: 20px;">
                <span style="color: #1f2937;">${escapeHtml(email)}</span>
                <button onclick="removeAlertEmail('${escapeHtml(email)}')" style="background: none; border: none; cursor: pointer; color: #ef4444; font-size: 16px; padding: 0 4px;" title="Remove">×</button>
            </div>
        `;
    }
    html += '</div>';
    container.innerHTML = html;
}

async function addAlertEmail() {
    const emailInput = document.getElementById('new-alert-email');
    const email = emailInput ? emailInput.value.trim() : '';
    
    if (!email) {
        alert('Please enter an email address');
        return;
    }
    
    if (!token) {
        alert('Please login again');
        window.location.href = 'login.html';
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/user/alert-emails?token=${token}&email=${encodeURIComponent(email)}`, {
            method: 'POST'
        });
        const data = await response.json();
        
        if (data.success) {
            alert(`✅ ${data.message}`);
            if (emailInput) emailInput.value = '';
            loadAlertEmails();
        } else {
            alert(`❌ ${data.message}`);
        }
    } catch (error) {
        console.error('Error adding alert email:', error);
        alert('Error adding alert email');
    }
}

async function removeAlertEmail(email) {
    if (!confirm(`Remove ${email} from alert notifications?`)) return;
    
    if (!token) {
        alert('Please login again');
        window.location.href = 'login.html';
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/user/alert-emails?token=${token}&email=${encodeURIComponent(email)}`, {
            method: 'DELETE'
        });
        const data = await response.json();
        
        if (data.success) {
            alert(`✅ ${data.message}`);
            loadAlertEmails();
        } else {
            alert(`❌ ${data.message}`);
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
            alert(`✅ ${data.message}`);
        } else {
            alert(`❌ Failed to send test alert`);
        }
    } catch (error) {
        console.error('Error sending test alert:', error);
        alert('Error sending test alert. Check SMTP configuration.');
    }
}

// ==================== Alert Email (Legacy) ====================

async function saveAlertEmail() {
    const alertEmail = document.getElementById('alert-email').value;
    if (!alertEmail) {
        alert('Please enter an email address');
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
            alert('✅ Alert email saved!');
            // Reload the alert emails list
            loadAlertEmails();
        } else {
            alert('Failed to save alert email');
        }
    } catch (error) {
        console.error('Error saving alert email:', error);
        alert('Error saving alert email');
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
    
    console.log('Starting monitoring with interval:', interval);
    
    try {
        const response = await fetch(`${API_URL}/monitoring/start?token=${token}&interval=${interval}`, { 
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        console.log('Start response status:', response.status);
        
        if (response.ok) {
            const data = await response.json();
            console.log('Start response:', data);
            alert('✅ Monitoring started!');
            updateMonitoringStatus();
            if (refreshInterval) clearInterval(refreshInterval);
            refreshInterval = setInterval(() => { loadDevices(); }, 3000);
        } else {
            const error = await response.json();
            console.error('Start failed:', error);
            alert('Failed to start monitoring: ' + (error.detail || 'Unknown error'));
        }
    } catch (error) {
        console.error('Start monitoring error:', error);
        alert('Error starting monitoring: ' + error.message);
    }
}

async function stopMonitoring() {
    if (!token) {
        alert('Please login again');
        window.location.href = 'login.html';
        return;
    }
    
    console.log('Stopping monitoring...');
    
    try {
        const response = await fetch(`${API_URL}/monitoring/stop?token=${token}`, { 
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        console.log('Stop response status:', response.status);
        
        if (response.ok) {
            alert('⏹️ Monitoring stopped!');
            updateMonitoringStatus();
        } else {
            const error = await response.json();
            alert('Failed to stop monitoring: ' + (error.detail || 'Unknown error'));
        }
    } catch (error) {
        console.error('Stop monitoring error:', error);
        alert('Error stopping monitoring: ' + error.message);
    }
}

async function updateMonitoringStatus() {
    if (!token) return;
    
    try {
        const response = await fetch(`${API_URL}/monitoring/status?token=${token}`);
        if (!response.ok) {
            console.error('Status response not OK:', response.status);
            return;
        }
        const status = await response.json();
        console.log('Monitoring status:', status);
        
        const statusPill = document.getElementById('monitor-status-pill');
        if (statusPill) {
            if (status.running) {
                statusPill.textContent = 'RUNNING';
                statusPill.className = 'status-pill status-running';
            } else {
                statusPill.textContent = 'STOPPED';
                statusPill.className = 'status-pill status-stopped';
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
        console.log('Loaded devices:', devices);
        displayDevices(devices);
        updateStats(devices);
    } catch (error) {
        console.error('Error loading devices:', error);
        const tableDiv = document.getElementById('devices-table');
        if (tableDiv) {
            tableDiv.innerHTML = '<div class="error-msg">Failed to load devices: ' + escapeHtml(error.message) + '</div>';
        }
    }
}

function updateStats(devices) {
    let up = 0, degraded = 0, down = 0, unknown = 0;
    for (const d of devices) {
        const status = (d.status || 'UNKNOWN').toUpperCase();
        if (status === 'UP') up++;
        else if (status === 'DEGRADED') degraded++;
        else if (status === 'DOWN') down++;
        else unknown++;
    }
    
    const total = devices.length;
    document.getElementById('total-devices').textContent = total;
    document.getElementById('up-count').textContent = up;
    document.getElementById('degraded-count').textContent = degraded;
    document.getElementById('down-count').textContent = down;
}

function filterDevices() {
    loadDevices();
}

function displayDevices(devices) {
    const searchInput = document.getElementById('device-search');
    const query = searchInput ? searchInput.value.trim().toLowerCase() : '';
    
    let filtered = devices;
    if (query) {
        filtered = devices.filter(d => {
            const name = (d.name || '').toLowerCase();
            const ip = (d.ip || '').toLowerCase();
            const group = (d.group || 'Default').toLowerCase();
            return name.includes(query) || ip.includes(query) || group.includes(query);
        });
    }
    
    const deviceCountSpan = document.getElementById('device-count');
    if (deviceCountSpan) deviceCountSpan.textContent = filtered.length;
    
    if (filtered.length === 0) {
        const tableDiv = document.getElementById('devices-table');
        if (tableDiv) {
            tableDiv.innerHTML = '<div class="loading">No devices found. Click "Add Device" to add one.</div>';
        }
        return;
    }
    
    const groupColors = { 
        MTN: '#ff9800', 
        Airtel: '#e91e63', 
        Glo: '#4caf50', 
        '9mobile': '#2196f3', 
        Gateway: '#9c27b0', 
        DNS: '#00bcd4',
        Default: '#6b7280'
    };
    
    let html = `<table><thead><tr>
        <th>Group</th>
        <th>Name</th>
        <th>IP</th>
        <th>Status</th>
        <th>Quality</th>
        <th>Latency</th>
        <th>Jitter</th>
        <th>Last Check</th>
        <th>Downtime</th>
        <th>Actions</th>
    </tr></thead><tbody>`;
    
    for (const d of filtered) {
        const group = d.group || 'Default';
        const ip = d.ip || 'N/A';
        const groupColor = groupColors[group] || '#6b7280';
        const statusText = d.status || 'UNKNOWN';
        const statusClass = `status-${statusText.toLowerCase()}`;
        const latency = d.latency_ms ? `${d.latency_ms.toFixed(1)}ms` : 'N/A';
        const jitter = d.jitter_ms ? `${d.jitter_ms.toFixed(1)}ms` : 'N/A';
        const lastCheck = d.last_check ? new Date(d.last_check).toLocaleTimeString() : 'Never';
        const downtime = d.downtime_display || '-';
        
        let qualityHtml = '';
        if (d.quality_score) {
            const score = d.quality_score;
            let qualityColor = '#10b981';
            let qualityBg = '#d1fae5';
            if (score < 70) {
                qualityColor = '#f59e0b';
                qualityBg = '#fed7aa';
            }
            if (score < 40) {
                qualityColor = '#ef4444';
                qualityBg = '#fee2e2';
            }
            qualityHtml = `<span style="display: inline-block; padding: 4px 8px; border-radius: 20px; background: ${qualityBg}; color: ${qualityColor}; font-weight: bold; font-size: 12px;">${score}%</span>`;
        } else {
            qualityHtml = '<span style="color: #6b7280; font-size: 12px;">N/A</span>';
        }
        
        html += `<tr>
            <td><span class="group-badge" style="background: ${groupColor}; color: white;">${escapeHtml(group)}</span></td>
            <td><strong>${escapeHtml(d.name)}</strong></td>
            <td>${escapeHtml(ip)}</div></td>
            <td><span class="status-badge-sm ${statusClass}">${escapeHtml(statusText)}</span></div></td>
            <td>${qualityHtml}</div></td>
            <td>${latency}</div></td>
            <td>${jitter}</div></td>
            <td>${lastCheck}</div></td>
            <td>${downtime}</div></td>
            <td>
                <button class="action-btn edit-btn" onclick="openEditModal('${d.id}', '${escapeHtml(d.name)}', '${escapeHtml(ip)}', '${escapeHtml(group)}')">Edit</button>
                <button class="action-btn delete-btn" onclick="deleteDevice('${d.id}')">Delete</button>
            </div>
        </tr>`;
    }
    html += `</tbody></table>`;
    
    const tableDiv = document.getElementById('devices-table');
    if (tableDiv) tableDiv.innerHTML = html;
}

function escapeHtml(str) { 
    if (!str) return '';
    return str.replace(/[&<>]/g, function(m) { 
        const escapes = {'&':'&amp;','<':'&lt;','>':'&gt;'};
        return escapes[m];
    }); 
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
        let url;
        
        if (editingDeviceId) {
            url = `${API_URL}/user/devices/${editingDeviceId}?token=${token}&name=${encodeURIComponent(name)}&ip=${encodeURIComponent(ip)}&group=${encodeURIComponent(group)}`;
            console.log('PUT Request URL:', url);
            response = await fetch(url, { method: 'PUT' });
        } else {
            url = `${API_URL}/user/devices?token=${token}&name=${encodeURIComponent(name)}&ip=${encodeURIComponent(ip)}&group=${encodeURIComponent(group)}`;
            console.log('POST Request URL:', url);
            response = await fetch(url, { method: 'POST' });
        }
        
        console.log('Response status:', response.status);
        
        if (response.ok) {
            const data = await response.json();
            console.log('Response data:', data);
            alert(editingDeviceId ? '✅ Device updated!' : '✅ Device added!');
            closeModal();
            loadDevices();
        } else {
            const error = await response.json();
            console.error('API error:', error);
            alert(editingDeviceId ? 'Failed to update device' : 'Failed to add device');
        }
    } catch (error) {
        console.error('Error saving device:', error);
        alert('Error saving device: ' + error.message);
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
        const url = `${API_URL}/user/devices/${id}?token=${token}`;
        console.log('DELETE Request URL:', url);
        const response = await fetch(url, { method: 'DELETE' });
        
        console.log('Response status:', response.status);
        
        if (response.ok) {
            const data = await response.json();
            console.log('Response data:', data);
            alert('✅ Device deleted!');
            loadDevices();
        } else {
            const error = await response.json();
            console.error('API error:', error);
            alert('Failed to delete device');
        }
    } catch (error) {
        console.error('Error deleting device:', error);
        alert('Error deleting device: ' + error.message);
    }
}

// ==================== Interval Presets ====================

function setupIntervalPresets() {
    const presetBtns = document.querySelectorAll('.preset-btn');
    if (presetBtns.length > 0) {
        presetBtns.forEach(btn => {
            btn.addEventListener('click', function() {
                const interval = this.dataset.interval;
                const intervalInput = document.getElementById('interval-input');
                if (intervalInput) intervalInput.value = interval;
                presetBtns.forEach(b => b.classList.remove('active'));
                this.classList.add('active');
            });
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
        loadDevices();
        updateMonitoringStatus();
        startAutoRefresh();
        setupIntervalPresets();
        loadAlertEmails();  // Load alert emails on init
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