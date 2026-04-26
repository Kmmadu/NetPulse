// NetPulse Dashboard JavaScript
const API_URL = 'http://localhost:8000/api';

// Global variables
let token = null;
let user = null;
let editingDeviceId = null;
let refreshInterval = null;

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
        // Load and display the saved alert email
        loadAndDisplayAlertEmail();
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

async function loadAndDisplayAlertEmail() {
    if (!token) return;
    
    try {
        const response = await fetch(`${API_URL}/user/alert-email?token=${token}&alert_email=test`, {
            method: 'GET'
        });
        // Since GET might not work, let's use the stored user data
        if (user && user.alert_email) {
            document.getElementById('alert-email').value = user.alert_email;
            document.getElementById('current-alert-email').textContent = user.alert_email;
            document.getElementById('current-email-display').style.display = 'block';
        } else {
            // Try to get from database directly via the alert-emails endpoint
            const emailsResp = await fetch(`${API_URL}/user/alert-emails?token=${token}`);
            const emailsData = await emailsResp.json();
            if (emailsData.alert_emails && emailsData.alert_emails.length > 0) {
                const savedEmail = emailsData.alert_emails[0];
                document.getElementById('alert-email').value = savedEmail;
                document.getElementById('current-alert-email').textContent = savedEmail;
                document.getElementById('current-email-display').style.display = 'block';
                // Update user object
                user.alert_email = savedEmail;
                localStorage.setItem('netpulse_user', JSON.stringify(user));
            }
        }
    } catch (error) {
        console.error('Error loading alert email:', error);
    }
}

async function saveAlertEmail() {
    const alertEmail = document.getElementById('alert-email').value.trim();
    if (!alertEmail) {
        alert('Please enter an email address');
        return;
    }
    
    // Basic email validation
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
            alert('Failed to save alert email: ' + (data.message || data.error || 'Unknown error'));
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
            alert('Failed to remove alert email: ' + (data.message || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error removing alert email:', error);
        alert('Error removing alert email');
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
            const error = await response.json();
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
    
    try {
        const response = await fetch(`${API_URL}/monitoring/stop?token=${token}`, { 
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (response.ok) {
            alert('Monitoring stopped');
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
    
    let html = `<table><thead><tr>
        <th>Group</th>
        <th>Name</th>
        <th>IP</th>
        <th>Status</th>
        <th>Latency</th>
        <th>Last Check</th>
        <th>Actions</th>
    </tr></thead><tbody>`;
    
    for (const d of filtered) {
        const group = d.group || 'Default';
        const ip = d.ip || 'N/A';
        const statusText = d.status || 'UNKNOWN';
        const statusClass = `status-${statusText.toLowerCase()}`;
        const latency = d.latency_ms ? `${d.latency_ms.toFixed(1)}ms` : 'N/A';
        const lastCheck = d.last_check ? new Date(d.last_check).toLocaleTimeString() : 'Never';
        const deviceId = d.id;
        
        html += `<tr>
            <td><span class="group-badge">${escapeHtml(group)}</span></td>
            <td><strong>${escapeHtml(d.name)}</strong></td>
            <td>${escapeHtml(ip)}</td>
            <td><span class="status-badge-sm ${statusClass}">${escapeHtml(statusText)}</span></td>
            <td>${latency}</td>
            <td>${lastCheck}</td>
            <td>
                <button class="action-btn edit-btn" onclick="openEditModal('${deviceId}', '${escapeHtml(d.name)}', '${escapeHtml(ip)}', '${escapeHtml(group)}')">Edit</button>
                <button class="action-btn delete-btn" onclick="deleteDevice('${deviceId}')">Delete</button>
            </td>
        </tr>`;
    }
    html += `</tbody></table>`;
    
    const tableDiv = document.getElementById('devices-table');
    if (tableDiv) tableDiv.innerHTML = html;
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
        
        if (response.ok) {
            alert(editingDeviceId ? 'Device updated successfully' : 'Device added successfully');
            closeModal();
            loadDevices();
        } else {
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
        const response = await fetch(`${API_URL}/user/devices/${id}?token=${token}`, { method: 'DELETE' });
        
        if (response.ok) {
            alert('Device deleted successfully');
            loadDevices();
        } else {
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
    loadAndDisplayAlertEmail();
    if (checkAuth()) {
        loadDevices();
        updateMonitoringStatus();
        startAutoRefresh();
        setupIntervalPresets();
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

// Function to load and display the saved alert email from database
async function loadAndDisplayAlertEmail() {
    if (!token) return;
    
    try {
        // First try to get from the alert-emails endpoint
        const response = await fetch(`${API_URL}/user/alert-emails?token=${token}`);
        const data = await response.json();
        
        console.log('Alert emails response:', data);
        
        if (data.alert_emails && data.alert_emails.length > 0) {
            const savedEmail = data.alert_emails[0];
            document.getElementById('alert-email').value = savedEmail;
            document.getElementById('current-alert-email').textContent = savedEmail;
            document.getElementById('current-email-display').style.display = 'block';
            
            // Update user object
            user.alert_email = savedEmail;
            localStorage.setItem('netpulse_user', JSON.stringify(user));
        } else {
            // No email saved
            document.getElementById('alert-email').value = '';
            document.getElementById('current-email-display').style.display = 'none';
        }
    } catch (error) {
        console.error('Error loading alert email:', error);
        // Fallback: try to get from user object
        if (user && user.alert_email) {
            document.getElementById('alert-email').value = user.alert_email;
            document.getElementById('current-alert-email').textContent = user.alert_email;
            document.getElementById('current-email-display').style.display = 'block';
        }
    }
}

// Override the saveAlertEmail function to reload the display
const originalSaveAlertEmail = saveAlertEmail;
saveAlertEmail = async function() {
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
            alert('Alert email saved successfully');
            // Reload the display
            await loadAndDisplayAlertEmail();
        } else {
            alert('Failed to save alert email: ' + (data.message || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error saving alert email:', error);
        alert('Error saving alert email');
    }
};

// Override the removeAlertEmail function
const originalRemoveAlertEmail = removeAlertEmail;
removeAlertEmail = async function() {
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
            alert('Alert email removed successfully');
            // Reload the display
            await loadAndDisplayAlertEmail();
        } else {
            alert('Failed to remove alert email: ' + (data.message || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error removing alert email:', error);
        alert('Error removing alert email');
    }
};
