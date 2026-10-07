// API 地址集中在 config.js；网络请求失败时清除读数，避免旧值被误认为实时数据。
const config = window.DASHBOARD_CONFIG || { apiBaseUrl: '', timeoutMs: 10000 };
const serverList = document.querySelector('#server-list');
const refreshButton = document.querySelector('#refresh-button');
let busy = false;

// API 的主机名、接口名和错误信息均按文本转义，不能直接当作 HTML 执行。
function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
}
function percent(value) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 100 ? value : null;
}
function quantity(value, rate = false) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return '暂无数据';
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit++; }
  return `${value.toFixed(unit ? 1 : 0)} ${units[unit]}${rate ? '/s' : ''}`;
}
function resource(label, value) {
  value = percent(value);
  return `<div class="resource"><div class="resource-label"><span>${label}</span><span class="resource-value">${value === null ? '暂无数据' : value + '%'}</span></div>${value === null ? '<div class="unavailable"></div>' : `<progress class="${value >= 80 ? 'high' : ''}" value="${value}" max="100" aria-label="${label}使用率">${value}%</progress>`}</div>`;
}
function render(data, connected = false) {
  const cpu = percent(data?.cpu?.usage_percent);
  const memory = percent(data?.memory?.usage_percent);
  const disk = percent(data?.disk?.usage_percent);
  const errors = Object.entries(data?.errors || {});
  const attention = !connected || errors.length > 0 || [cpu, memory, disk].some(value => value !== null && value >= 80);
  document.querySelector('#online-count').innerHTML = `${connected ? '01' : '00'}<small>台</small>`;
  document.querySelector('#availability').textContent = connected ? 'Agent API 可达' : '等待 Agent 响应';
  document.querySelector('#average-cpu').innerHTML = cpu === null ? '—' : `${cpu}<small>%</small>`;
  document.querySelector('#attention-count').innerHTML = `${attention ? '01' : '00'}<small>台</small>`;
  const interfaces = Object.entries(data?.network?.interfaces || {});
  serverList.innerHTML = `<article class="server-card"><div class="server-main">
    <div class="server-top"><div class="server-icon" aria-hidden="true">▤</div><span class="status ${connected ? '' : 'offline'}"><span class="dot"></span>${connected ? '在线' : '未连接'}</span></div>
    <h3 class="server-name">${escapeHtml(data?.system?.hostname || 'Agent 主机')}</h3>
    <p class="server-ip">${escapeHtml(config.apiBaseUrl || '同源 API')}</p>
    <p class="server-role">${escapeHtml(data?.system?.os_version || '等待系统信息')}</p>
    ${resource('CPU', cpu)}${resource('内存', memory)}${resource('磁盘', disk)}
    <p class="server-role">逻辑核心：${escapeHtml(data?.cpu?.logical_cores ?? '—')}</p>
    <p class="server-role">内存：${quantity(data?.memory?.used_bytes)} / ${quantity(data?.memory?.total_bytes)}</p>
    <p class="server-role">磁盘 ${escapeHtml(data?.disk?.path || '')}：${quantity(data?.disk?.used_bytes)} / ${quantity(data?.disk?.total_bytes)}</p>
    <div class="resource-label"><span>网络接口 · 上传 / 下载</span></div>
    ${interfaces.length ? interfaces.map(([name, net]) => `<div class="resource"><div class="resource-label"><span>${escapeHtml(name)}</span></div><p class="server-ip">↑ ${quantity(net.upload_bytes_per_second, true)} · ↓ ${quantity(net.download_bytes_per_second, true)}</p><p class="server-role">累计发送 ${quantity(net.bytes_sent)} · 接收 ${quantity(net.bytes_received)}</p></div>`).join('') : '<p class="server-role">暂无网络数据</p>'}
    </div><div class="server-footer"><span>真实 Agent 数据</span><span class="${attention ? 'alert' : ''}">${!connected ? '等待连接' : errors.length ? '部分采集失败' : attention ? '资源使用率偏高' : '运行状态正常'}</span></div></article>`;
  document.querySelector('#api-message').textContent = errors.length ? `部分指标采集失败：${errors.map(([name, error]) => `${name}: ${error}`).join('；')}` : connected ? '已连接 Agent。点击刷新获取最新读数；网络速率为两次采集之间的平均值。' : '正在连接 Agent API…';
  if (connected) {
    const date = new Date(data.timestamp);
    document.querySelector('#updated-at').textContent = `最近更新：${Number.isNaN(date.getTime()) ? '未知时间' : date.toLocaleString('zh-CN', { hour12: false })}`;
  }
}
async function refreshStatus() {
  if (busy) return;
  busy = true;
  refreshButton.disabled = true;
  refreshButton.textContent = '正在刷新…';
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), config.timeoutMs || 10000);
  try {
    const response = await fetch(`${config.apiBaseUrl.replace(/\/$/, '')}/api/status`, { signal: controller.signal, cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!data || typeof data !== 'object' || !('cpu' in data) || !('memory' in data) || !('disk' in data) || !('network' in data) || !('errors' in data)) throw new Error('API 返回的数据结构不正确');
    render(data, true);
  } catch (error) {
    render(null);
    document.querySelector('#api-message').textContent = `API 访问失败：${error.name === 'AbortError' ? '请求超时' : error.message}。请检查 Agent 是否启动、config.js 地址及 API 跨域配置。`;
    document.querySelector('#updated-at').textContent = '更新失败 · 当前读数不可用';
  } finally {
    clearTimeout(timer);
    busy = false;
    refreshButton.disabled = false;
    refreshButton.innerHTML = '<span aria-hidden="true">↻</span> 刷新监控数据';
  }
}
refreshButton.addEventListener('click', refreshStatus);
render(null);
refreshStatus();
