// 模拟服务器数据：可像 Java 对象一样理解每个对象的字段。
// 所有操作仅在浏览器内执行，不发送网络请求。
const servers = [
  { name: "Web-Server-01", ip: "192.168.1.101", online: true, role: "应用服务 / WEB", cpu: 36, memory: 58, disk: 42 },
  { name: "Database-02", ip: "192.168.1.102", online: true, role: "数据库节点 / DATABASE", cpu: 64, memory: 82, disk: 67 },
  { name: "Backup-Server-03", ip: "192.168.1.103", online: false, role: "备份节点 / BACKUP", cpu: null, memory: null, disk: null }
];

const serverList = document.querySelector("#server-list");
const serverIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 6.5h.01M7 17.5h.01M12 6.5h5M12 17.5h5" stroke-linecap="round"/></svg>';

// 离线节点没有实时读数，显示“暂无数据”，避免把未知误认为 0%。
function renderResource(label, value, online) {
  const available = online && value !== null;
  return `<div class="resource">
    <div class="resource-label"><span>${label}</span><span class="resource-value">${available ? value + "%" : "暂无数据"}</span></div>
    ${available ? `<progress class="${value >= 80 ? "high" : ""}" value="${value}" max="100" aria-label="${label}使用率">${value}%</progress>` : '<div class="unavailable" aria-hidden="true"></div>'}
  </div>`;
}

function needsAttention(server) {
  return !server.online || [server.cpu, server.memory, server.disk].some(value => value >= 80);
}

function renderDashboard() {
  // HTML 来自上面的固定本地数据；如接入外部输入，应改用 textContent 安全写入。
  serverList.innerHTML = servers.map(server => `<article class="server-card">
    <div class="server-main">
      <div class="server-top"><div class="server-icon">${serverIcon}</div><span class="status ${server.online ? "" : "offline"}"><span class="dot"></span>${server.online ? "在线" : "离线"}</span></div>
      <h3 class="server-name">${server.name}</h3><p class="server-ip">${server.ip}</p><p class="server-role">${server.role}</p>
      ${renderResource("CPU", server.cpu, server.online)}
      ${renderResource("内存", server.memory, server.online)}
      ${renderResource("磁盘", server.disk, server.online)}
    </div>
    <div class="server-footer"><span>模拟节点</span><span class="${needsAttention(server) ? "alert" : ""}">${!server.online ? "节点离线 · 等待恢复" : needsAttention(server) ? "资源使用率偏高" : "运行状态正常"}</span></div>
  </article>`).join("");

  const onlineServers = servers.filter(server => server.online);
  const averageCpu = onlineServers.length ? Math.round(onlineServers.reduce((total, server) => total + server.cpu, 0) / onlineServers.length) : null;
  document.querySelector("#online-count").innerHTML = `${String(onlineServers.length).padStart(2, "0")}<small>台</small>`;
  document.querySelector("#availability").textContent = `可用率 ${(onlineServers.length / servers.length * 100).toFixed(1)}%`;
  document.querySelector("#average-cpu").innerHTML = averageCpu === null ? "—" : `${averageCpu}<small>%</small>`;
  document.querySelector("#attention-count").innerHTML = `${String(servers.filter(needsAttention).length).padStart(2, "0")}<small>台</small>`;
  document.querySelector("#updated-at").textContent = `最近更新：${new Date().toLocaleTimeString("zh-CN", { hour12: false })}`;
}

// 点击刷新时小幅改变在线节点的模拟值，限制在 0～100 之间。
document.querySelector("#refresh-button").addEventListener("click", () => {
  servers.filter(server => server.online).forEach(server => {
    ["cpu", "memory", "disk"].forEach(resource => {
      server[resource] = Math.max(0, Math.min(100, server[resource] + Math.floor(Math.random() * 15) - 7));
    });
  });
  renderDashboard();
});

renderDashboard();
